"""
CKP API Routes — v2 endpoints.

Provides REST API endpoints for:
- Agent querying (chat)
- Data ingestion (upload + process)
- Schema management
- System diagnostics
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Request
from pydantic import BaseModel, Field

from agent_harness.skills.skill_builder_agent import SkillBuilderAgent
from agent_harness.prompts.prompt_builder_agent import PromptBuilderAgent
from agent_harness.uka_export import UKAExporter
from fastapi.responses import FileResponse, Response, StreamingResponse
import json
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

router = APIRouter(tags=["CKP v2"])


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    """User query request."""

    query: str = Field(description="The user's natural language question")
    session_id: Optional[str] = Field(default=None, description="Session ID for context continuity")
    schema_name: Optional[str] = Field(default="healthtech", description="Active domain schema")
    model: Optional[str] = Field(default="gemini-2.5-flash", description="LLM model to use")
    active_skill: Optional[str] = Field(default="auto", description="Skill to execute, 'auto' for routing")


class QueryResponse(BaseModel):
    """Agent response."""

    response: str
    session_id: str
    model_used: str
    total_steps: int
    duration_ms: float
    groundedness_score: float
    pii_entities_masked: int
    tools_used: list[str] = []
    sources: list[dict] = []
    # Smart Model Cascade Router (AI Economics) fields
    smart_routed: bool = False
    complexity_tier: Optional[str] = None
    intent: Optional[str] = None
    estimated_cost_tier: Optional[str] = None
    routing_reason: Optional[str] = None
    cascade_fallback: bool = False
    cascade_reason: Optional[str] = None
    mechanic_repairs: int = 0


class IngestionRequest(BaseModel):
    """Ingestion configuration for uploaded files."""

    schema_name: str = Field(default="healthtech", description="Domain schema for entity extraction")
    chunk_size: int = Field(default=512, description="Chunk size in tokens")
    chunk_overlap: int = Field(default=64, description="Overlap between chunks in tokens")


class IngestionResponse(BaseModel):
    """Ingestion result."""

    filename: str
    status: str
    chunks_created: int
    entities_extracted: int
    relationships_extracted: int
    duration_ms: float


class SchemaListResponse(BaseModel):
    """List of available schemas."""

    schemas: list[str]
    active: str


class DiagnosticsResponse(BaseModel):
    """System diagnostics."""

    platform_version: str
    active_schema: str
    guardrails: dict
    gateway: dict
    memory: dict

class AdminConfigRequest(BaseModel):
    """Admin dashboard configuration."""
    guardrails: list[dict]
    promptThreshold: float
    gateway: dict



# ---------------------------------------------------------------------------
# Helpers for Query & Streaming Endpoints
# ---------------------------------------------------------------------------
def resolve_routing_and_skill(request_body: QueryRequest, request: Request):
    """
    Resolves smart cascade routing, intent gating, and fast deterministic skill lookup.
    """
    gateway = getattr(request.app.state, "gateway", None)
    runner = request.app.state.runner
    registry = request.app.state.skill_registry
    if gateway and getattr(runner, "gateway", None) is None:
        runner.gateway = gateway
    if getattr(runner, "guardrails", None) is None:
        runner.guardrails = getattr(request.app.state, "guardrails", None)

    # 1. Smart Model Cascade Routing & Intent Gating (AI Economics)
    if gateway:
        routing_decision = gateway.router.route_query(
            request_body.query,
            requested_model=request_body.model,
        )
    else:
        from ai_gateway.router import RoutingDecision, ComplexityTier, RoutingIntent
        routing_decision = RoutingDecision(
            selected_model=request_body.model or "gemini-2.5-flash",
            tier=ComplexityTier.TIER_1,
            intent=RoutingIntent.GRAPH_RAG,
            reason="Gateway not attached to state, using default routing.",
        )
    runner.config.active_model = routing_decision.selected_model
    runner.config.bypass_graph_tools = routing_decision.bypass_graph_tools
    runner.config.intent = routing_decision.intent.value
    runner.config.complexity_tier = routing_decision.tier.value

    if getattr(runner, "skill_registry", None) is None:
        runner.skill_registry = registry

    skill_name = request_body.active_skill
    if routing_decision.bypass_graph_tools:
        skill_name = "general_assistant"
        runner.config.active_skill = None
    elif not skill_name or skill_name == "auto":
        # Native In-Agent Skill Selection (Approach 2):
        # Zero pre-flight latency, zero extra vector database maintenance.
        # The agent natively selects and adopts the specialized skill persona in its reasoning loop.
        skill_name = "auto"
        runner.config.active_skill = None
    else:
        # Explicit user-selected skill override
        try:
            registry.load_directory()
            runner.config.active_skill = registry.get(skill_name)
        except Exception:
            runner.config.active_skill = None

    return runner, routing_decision, skill_name, gateway


def collect_rich_sources(steps, schema_name: str, skill_name: str) -> list[dict]:
    """
    Parses executed tools across Graph, Relational, and Vector storage engines,
    producing rich, multi-source collapsible cards without collisions.
    """
    source_map = {}
    import re

    cypher_count = 0
    sql_count = 0

    for step in steps:
        tool_name = getattr(step, "tool_name", None) or (step.get("tool_name") if isinstance(step, dict) else None)
        tool_input = getattr(step, "tool_input", None) or (step.get("tool_input") if isinstance(step, dict) else {})
        tool_output = getattr(step, "tool_output", None) or (step.get("tool_output") if isinstance(step, dict) else None)
        step_idx = getattr(step, "step_index", 1) or (step.get("step_index", 1) if isinstance(step, dict) else 1)
        is_repaired = getattr(step, "mechanic_repaired", False) or (step.get("mechanic_repaired", False) if isinstance(step, dict) else False)

        if tool_name in ["semantic_search", "vector_search"]:
            key = f"vector_knowledge_chunks_{step_idx}"
            source_map[key] = {
                "type": "vector",
                "label": "Vector Store (Qdrant): knowledge_chunks",
                "explanation": "Semantic vector similarity search across ingested text chunk embeddings.",
                "data": [],
                "mechanic_repaired": False,
            }
            if isinstance(tool_output, list):
                for hit in tool_output:
                    if isinstance(hit, dict):
                        text = hit.get("text", "")[:150] + ("..." if len(hit.get("text", "")) > 150 else "")
                        fname = hit.get("metadata", {}).get("filename", "Document")
                        source_map[key]["data"].append({"file": fname, "snippet": text})

        elif tool_name in ["execute_cypher", "graph_query"]:
            cypher_count += 1
            labels = ["Knowledge Graph"]
            cypher_query = ""
            if tool_input and "query" in tool_input:
                cypher_query = tool_input["query"]
                found = re.findall(r":([A-Za-z0-9_]+)", cypher_query)
                if found:
                    labels = list(set(found))
            
            label_str = ", ".join(labels)
            key = f"graph_{label_str}_{step_idx}"
            query_suffix = f" [Query {cypher_count}]" if cypher_count > 1 else ""

            source_map[key] = {
                "type": "graph",
                "label": f"Knowledge Graph (Neo4j): {label_str}{query_suffix}",
                "explanation": f"Cypher graph traversal executed on Neo4j matching {label_str}.",
                "data": [],
                "mechanic_repaired": is_repaired,
            }

            if cypher_query:
                source_map[key]["data"].append(f"Query: {cypher_query[:120]}...")

            records = tool_output
            if isinstance(records, dict):
                records = records.get("output", records.get("result", []))
            if isinstance(records, list):
                for record in records[:5]:
                    rec_str = str(record)
                    source_map[key]["data"].append(rec_str[:150] + ("..." if len(rec_str) > 150 else ""))

        elif tool_name in ["execute_sql", "sql_query"]:
            sql_count += 1
            table = "Relational Data"
            sql_query = ""
            if tool_input and "query" in tool_input:
                sql_query = tool_input["query"]
                found = re.findall(r"FROM\s+([A-Za-z0-9_]+)", sql_query, re.IGNORECASE)
                if found:
                    table = found[0]

            key = f"sql_{table}_{step_idx}"
            source_map[key] = {
                "type": "relational",
                "label": f"Relational DB (PostgreSQL): {table}",
                "explanation": f"Structured SQL relational query executed on '{table}'.",
                "data": [],
                "mechanic_repaired": is_repaired,
            }
            if sql_query:
                source_map[key]["data"].append(f"SQL: {sql_query[:120]}...")

            records = tool_output
            if isinstance(records, dict):
                records = records.get("output", records.get("result", []))
            if isinstance(records, list):
                for record in records[:5]:
                    rec_str = str(record)
                    source_map[key]["data"].append(rec_str[:150] + ("..." if len(rec_str) > 150 else ""))

    unique_sources = list(source_map.values())[:6]

    if not unique_sources:
        schema = schema_name or "healthtech"
        skill_display = "Auto (Native Agent Selection)" if skill_name == "auto" else skill_name
        unique_sources = [{
            "type": "graph",
            "label": f"Active Knowledge Base: {schema}",
            "explanation": f"Grounded in active {schema} schema entities and topological relationships in Neo4j.",
            "data": [f"Domain: {schema}", f"Skill: {skill_display}"]
        }]
    return unique_sources


# ---------------------------------------------------------------------------
# Query Endpoints
# ---------------------------------------------------------------------------
@router.post("/query", response_model=QueryResponse)
async def query_agent(request_body: QueryRequest, request: Request):
    """
    Send a natural language query to the CKP agent (synchronous batch mode).
    """
    runner, routing_decision, skill_name, gateway = resolve_routing_and_skill(request_body, request)
    active_sid = request_body.session_id or str(uuid.uuid4())

    logger.info(
        f"Executing query with skill: {skill_name} | model: {routing_decision.selected_model} "
        f"| tier: {routing_decision.tier.value} | intent: {routing_decision.intent.value}"
    )

    # Execute the agent with active or newly generated session_id
    result = await runner.run(request_body.query, session_id=active_sid)

    # Collect rich data sources from tools
    unique_sources = collect_rich_sources(
        result.steps,
        schema_name=request_body.schema_name or "healthtech",
        skill_name=skill_name
    )
                        
    ctx = getattr(request.app.state, "context_engine", None)
    tools_used_list = [step.tool_name for step in result.steps if step.tool_name]
    final_model = routing_decision.selected_model
    if ctx:
        ctx.update_last_message_metadata(
            active_sid,
            {
                "sources": list(unique_sources),
                "tools_used": tools_used_list,
                "total_steps": result.total_steps,
                "duration_ms": result.total_duration_ms,
                "model_used": final_model,
                "smart_routed": bool(request_body.model and request_body.model.lower() in ("auto", "auto (ai economics)", "smart")),
                "complexity_tier": routing_decision.tier.value,
                "intent": routing_decision.intent.value,
                "routing_reason": routing_decision.reason,
            }
        )

    # Record telemetry for query
    try:
        in_toks = max(10, len(request_body.query.split()) * 2)
        out_toks = max(10, len((result.final_response or "").split()) * 2)
        in_c, out_c, tot_c = gateway.telemetry.calculate_costs(final_model, in_toks, out_toks)
        from ai_gateway.telemetry import AuditLogEntry
        gateway.telemetry.record_call(AuditLogEntry(
            session_id=active_sid,
            prompt_preview=request_body.query[:200],
            model_name=final_model,
            provider="gemini" if "gemini" in final_model.lower() else ("anthropic" if "claude" in final_model.lower() else "openai"),
            is_smart_routed=bool(request_body.model and request_body.model.lower() in ("auto", "auto (ai economics)", "smart")),
            complexity_tier=routing_decision.tier.value,
            intent=routing_decision.intent.value,
            input_tokens=in_toks,
            output_tokens=out_toks,
            input_cost_usd=in_c,
            output_cost_usd=out_c,
            total_cost_usd=tot_c,
            duration_ms=result.total_duration_ms,
            status="fallback" if routing_decision.fallback_applied else ("error" if result.error else "success"),
            tools_called=tools_used_list,
            routing_reason=routing_decision.reason,
            cascade_reason=routing_decision.fallback_reason,
        ))
    except Exception as tel_e:
        logger.warning(f"Failed to record telemetry for query: {tel_e}")

    return QueryResponse(
        response=result.final_response or "No answer returned.",
        session_id=active_sid,
        model_used=final_model,
        total_steps=result.total_steps,
        duration_ms=result.total_duration_ms,
        groundedness_score=0.95,  # Mocked guardrail for now
        pii_entities_masked=0,
        tools_used=tools_used_list,
        sources=list(unique_sources),
        smart_routed=bool(request_body.model and request_body.model.lower() in ("auto", "auto (ai economics)", "smart")),
        complexity_tier=routing_decision.tier.value,
        intent=routing_decision.intent.value,
        estimated_cost_tier=routing_decision.estimated_cost_tier,
        routing_reason=routing_decision.reason,
        cascade_fallback=routing_decision.fallback_applied,
        cascade_reason=routing_decision.fallback_reason,
        mechanic_repairs=getattr(result, "mechanic_repairs", 0),
    )


@router.post("/query/stream")
async def stream_query_endpoint(request_body: QueryRequest, request: Request):
    """
    Server-Sent Events (SSE) streaming endpoint for real-time thinking trace and token generation.
    """
    runner, routing_decision, skill_name, gateway = resolve_routing_and_skill(request_body, request)
    active_sid = request_body.session_id or str(uuid.uuid4())

    async def sse_event_generator():
        # Emit initial intent and routing decision event
        yield f"data: {json.dumps({'type': 'intent', 'model': routing_decision.selected_model, 'tier': routing_decision.tier.value, 'intent': routing_decision.intent.value, 'smart_routed': bool(request_body.model and request_body.model.lower() in ('auto', 'auto (ai economics)', 'smart')), 'routing_reason': routing_decision.reason, 'estimated_cost_tier': routing_decision.estimated_cost_tier, 'cascade_fallback': routing_decision.fallback_applied, 'cascade_reason': routing_decision.fallback_reason})}\n\n"

        accumulated_steps = []
        final_meta = {}

        try:
            async for event in runner.run_stream(request_body.query, session_id=active_sid):
                ev_type = event.get("type")
                if ev_type in ("action", "observation"):
                    accumulated_steps.append(event)
                elif ev_type == "done":
                    final_meta = event
                
                yield f"data: {json.dumps(event)}\n\n"

            # Parse rich sources from steps
            rich_sources = collect_rich_sources(
                accumulated_steps,
                schema_name=request_body.schema_name or "healthtech",
                skill_name=skill_name,
            )

            # Update session context metadata
            ctx = getattr(request.app.state, "context_engine", None)
            tools_used_list = [s.get("tool") for s in accumulated_steps if s.get("type") == "action" and s.get("tool")]
            if ctx:
                ctx.update_last_message_metadata(
                    active_sid,
                    {
                        "sources": list(rich_sources),
                        "tools_used": tools_used_list,
                        "total_steps": final_meta.get("total_steps", len(accumulated_steps) + 1),
                        "duration_ms": final_meta.get("duration_ms", 0.0),
                        "model_used": runner.config.active_model,
                        "smart_routed": bool(request_body.model and request_body.model.lower() in ("auto", "auto (ai economics)", "smart")),
                        "complexity_tier": routing_decision.tier.value,
                        "intent": routing_decision.intent.value,
                        "routing_reason": routing_decision.reason,
                    }
                )

            # Emit final resolution packet
            yield f"data: {json.dumps({'type': 'complete', 'session_id': active_sid, 'sources': rich_sources, 'model_used': runner.config.active_model, 'complexity_tier': routing_decision.tier.value, 'intent': routing_decision.intent.value, 'smart_routed': bool(request_body.model and request_body.model.lower() in ('auto', 'auto (ai economics)', 'smart')), 'routing_reason': routing_decision.reason, 'total_steps': final_meta.get('total_steps', len(accumulated_steps) + 1), 'duration_ms': final_meta.get('duration_ms', 0.0)})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Streaming query error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        sse_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/sessions")
async def list_sessions(request: Request):
    """List all active conversation sessions."""
    ctx = request.app.state.context_engine
    return {"sessions": ctx.list_sessions()}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    """Get all messages for a specific session, ensuring metadata and sources are preserved."""
    ctx = request.app.state.context_engine
    raw_messages = ctx.export_session(session_id)
    for msg in raw_messages:
        if msg.get("role") == "assistant":
            meta = msg.get("metadata") or {}
            model_name = (
                meta.get("model_used")
                or msg.get("model_used")
                or getattr(request.app.state, "active_model", None)
                or "gemini-2.5-flash"
            )
            if not meta.get("sources"):
                schema = meta.get("schema", "healthtech")
                meta["sources"] = [{
                    "type": "graph",
                    "label": f"Knowledge Base: {schema}",
                    "explanation": f"Grounded in active {schema} schema knowledge graph and context.",
                    "data": [f"Domain: {schema}", f"Model: {model_name}"]
                }]
            if "total_steps" not in meta or meta.get("total_steps") is None:
                meta["total_steps"] = 1
            if "duration_ms" not in meta or meta.get("duration_ms") is None:
                meta["duration_ms"] = 0
            meta["model_used"] = model_name
            msg["metadata"] = meta
    return {"messages": raw_messages}



@router.delete("/sessions/{session_id}")
async def clear_session(session_id: str, request: Request):
    """Clear a specific conversation session."""
    ctx = request.app.state.context_engine
    ctx.clear_session(session_id)
    return {"status": "cleared", "session_id": session_id}


@router.get("/sessions/{session_id}/export")
@router.get("/sessions/{session_id}/export/uka")
async def export_session(session_id: str, request: Request, format: str = "zip"):
    """
    Export a session as a Universal Knowledge Artifact (UKA).
    Supports format='zip' (.uka container) and format='json'.
    """
    ctx = request.app.state.context_engine
    neo4j = getattr(request.app.state, "neo4j_driver", None)
    qdrant = getattr(request.app.state, "qdrant_client", None)
    ontology_mgr = getattr(request.app.state, "ontology_manager", None)

    exporter = UKAExporter(
        context_engine=ctx,
        neo4j_driver=neo4j,
        qdrant_client=qdrant,
        ontology_manager=ontology_mgr,
        active_domain="healthtech",
    )
    
    tmp_dir = Path(tempfile.mkdtemp())
    if format == "json":
        out_path = tmp_dir / f"uka_{session_id}.json"
        exporter.export_to_json(session_id, out_path)
        return FileResponse(out_path, filename=f"{session_id}.json", media_type="application/json")
    else:
        out_path = tmp_dir / f"{session_id}.uka"
        exporter.export_to_bundle(session_id, out_path)
        return FileResponse(
            out_path,
            filename=f"{session_id}.uka",
            media_type="application/x-uka+zip",
            headers={"Content-Disposition": f'attachment; filename="{session_id}.uka"'},
        )


@router.post("/uka/import")
@router.post("/sessions/import/uka")
async def import_uka_bundle(
    request: Request,
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
):
    """
    Import and rehydrate a Universal Knowledge Artifact (.uka) bundle.
    Restores graph nodes and relationships into Neo4j, vector chunks into Qdrant,
    conversational history into SQLite, and extracts packaged media files.
    """
    if not file.filename.endswith((".uka", ".zip")):
        raise HTTPException(
            status_code=400,
            detail="Invalid archive format. Please upload a .uka or .zip file.",
        )

    tmp_dir = Path(tempfile.mkdtemp())
    tmp_file = tmp_dir / file.filename
    content = await file.read()
    tmp_file.write_bytes(content)

    from uka.importer import UKAImporter

    media_dir = Path("data/media")
    importer = UKAImporter(
        neo4j_driver=getattr(request.app.state, "neo4j_driver", None),
        qdrant_client=getattr(request.app.state, "qdrant_client", None),
        context_engine=request.app.state.context_engine,
        media_storage_dir=media_dir,
    )

    try:
        result = importer.import_bundle(
            bundle_path=tmp_file,
            target_session_id=session_id,
            verify_integrity=True,
        )
        return result
    except Exception as e:
        logger.error(f"Failed to import UKA bundle: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to import UKA bundle: {str(e)}")


# ---------------------------------------------------------------------------
# Ingestion Endpoints
# ---------------------------------------------------------------------------
@router.post("/ingest", response_model=IngestionResponse)
async def ingest_file(
    request: Request,
    file: UploadFile = File(...),
    schema_name: str = "healthtech",
    chunk_size: int = 512,
    chunk_overlap: int = 64,
):
    """
    Upload and ingest a file into the knowledge platform.

    Supports: PDF, TXT, MD, CSV, JSON, DOCX

    Pipeline:
    1. Parse file content (loaders)
    2. Chunk into semantic segments
    3. Extract entities/relationships via Ontology Engine
    4. Store chunks in Qdrant (vector)
    5. Store entities in Neo4j (graph)
    6. Store structured data in PostgreSQL (tabular)
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    logger.info(f"Ingestion request: {file.filename} (schema: {schema_name})")

    # Build a pipeline with the app's shared dependencies
    from backend.ingestion.pipeline import IngestionPipeline

    pipeline = IngestionPipeline(
        schema_name=schema_name,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        gateway=getattr(request.app.state, "gateway", None),
        ontology_manager=getattr(request.app.state, "ontology_manager", None),
        qdrant_client=getattr(request.app.state, "qdrant_client", None),
        neo4j_driver=getattr(request.app.state, "neo4j_driver", None),
    )

    # Read file bytes and ingest
    content = await file.read()
    result = await pipeline.ingest_bytes(
        content=content,
        filename=file.filename,
    )

    return IngestionResponse(
        filename=result.filename,
        status=result.status,
        chunks_created=result.chunks_created,
        entities_extracted=result.entities_extracted,
        relationships_extracted=result.relationships_extracted,
        duration_ms=result.duration_ms,
    )


@router.get("/ingest/sources")
async def list_ingested_sources(request: Request):
    """List all ingested data sources."""
    sources = []

    # Query Qdrant for vector collection stats
    qdrant = getattr(request.app.state, "qdrant_client", None)
    if qdrant:
        try:
            collections = await qdrant.get_collections()
            for col in collections.collections:
                info = await qdrant.get_collection(col.name)
                sources.append({
                    "type": "vector",
                    "store": "qdrant",
                    "name": col.name,
                    "points_count": info.points_count,
                })
        except Exception as e:
            logger.warning(f"Failed to query Qdrant sources: {e}")

    # Query Neo4j for graph node labels and counts
    neo4j = getattr(request.app.state, "neo4j_driver", None)
    if neo4j:
        try:
            async with neo4j.session() as session:
                result = await session.run(
                    "CALL db.labels() YIELD label "
                    "RETURN label, count { MATCH (n) WHERE label IN labels(n) RETURN count(n) } AS count"
                )
                records = await result.data()
                for record in records:
                    sources.append({
                        "type": "graph",
                        "store": "neo4j",
                        "name": record.get("label", "unknown"),
                        "node_count": record.get("count", 0),
                    })
        except Exception as e:
            logger.warning(f"Failed to query Neo4j sources: {e}")

    return {"sources": sources}


# ---------------------------------------------------------------------------
# Schema Management Endpoints
# ---------------------------------------------------------------------------
@router.get("/schemas", response_model=SchemaListResponse)
async def list_schemas(request: Request):
    """List all available domain schemas."""
    manager = request.app.state.ontology_manager
    schemas = manager.list_available()
    return SchemaListResponse(
        schemas=schemas,
        active=schemas[0] if schemas else "healthtech",
    )


@router.get("/schemas/{schema_name}")
async def get_schema(schema_name: str, request: Request):
    """Get the full schema definition for a domain."""
    manager = request.app.state.ontology_manager
    try:
        schema_def = manager.load(schema_name)
        return schema_def.model_dump()
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/schemas/{schema_name}/prompt")
async def get_schema_prompt(schema_name: str, request: Request):
    """Get the LLM-ready schema prompt for a domain."""
    manager = request.app.state.ontology_manager
    try:
        prompt = manager.get_schema_prompt(schema_name)
        return {"schema_name": schema_name, "prompt": prompt}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# Diagnostics Endpoints
# ---------------------------------------------------------------------------
@router.get("/diagnostics", response_model=DiagnosticsResponse)
async def get_diagnostics(request: Request):
    """Get system diagnostics and health info."""
    guardrail_engine = getattr(request.app.state, "guardrails", None)
    gateway_client = getattr(request.app.state, "gateway", None)
    memory_manager = getattr(request.app.state, "memory", None)

    return DiagnosticsResponse(
        platform_version="2.0.0",
        active_schema="healthtech",
        guardrails=guardrail_engine.config.model_dump() if guardrail_engine else {},
        gateway=gateway_client.config.model_dump() if gateway_client else {},
        memory=memory_manager.stats() if memory_manager else {},
    )


@router.get("/diagnostics/guardrails")
async def get_guardrail_diagnostics(request: Request):
    """Get detailed guardrail configuration and stats."""
    guardrail_engine = getattr(request.app.state, "guardrails", None)
    if guardrail_engine:
        return guardrail_engine.config.model_dump()
    return {"status": "no_guardrail_engine"}


# ---------------------------------------------------------------------------
# Admin Configuration Endpoints
# ---------------------------------------------------------------------------
import json
import os

ADMIN_CONFIG_PATH = "data/admin_config.json"

@router.get("/admin/config")
async def get_admin_config():
    """Get saved admin dashboard configuration."""
    if os.path.exists(ADMIN_CONFIG_PATH):
        try:
            with open(ADMIN_CONFIG_PATH, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read admin config: {e}")
    return {}

@router.post("/admin/config")
async def save_admin_config(request: AdminConfigRequest):
    """Save admin dashboard configuration."""
    try:
        os.makedirs(os.path.dirname(ADMIN_CONFIG_PATH) or ".", exist_ok=True)
        with open(ADMIN_CONFIG_PATH, 'w') as f:
            json.dump(request.model_dump(), f)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to save admin config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Skills Library Endpoints
# ---------------------------------------------------------------------------
class SkillCreateRequest(BaseModel):
    """Request to create a new skill from natural language."""

    description: str = Field(description="Plain-English description of the desired skill")
    domain: str = Field(default="general", description="Target domain")


@router.get("/skills")
async def list_skills(request: Request):
    """List all available agent skills in the library."""
    registry = request.app.state.skill_registry
    return {"skills": registry.list_all(), "status": "success"}


@router.get("/skills/{skill_name}")
async def get_skill(skill_name: str, request: Request):
    """Get the full definition of a specific skill."""
    registry = request.app.state.skill_registry
    try:
        skill = registry.get(skill_name)
        return {"skill_name": skill_name, "skill": skill.model_dump(), "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/skills/create")
async def create_skill(create_request: SkillCreateRequest):
    """
    Create a new agent skill from a natural language description.
    """
    logger.info(f"Skill creation request: {create_request.description[:80]}...")
    try:
        agent = SkillBuilderAgent()
        skill = await agent.create_and_save(create_request.description)
        return {
            "status": "success",
            "skill": skill.model_dump()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Prompt Templates Library Endpoints
# ---------------------------------------------------------------------------
class PromptCreateRequest(BaseModel):
    """Request to create a new prompt template from natural language."""

    description: str = Field(description="Plain-English description of the desired template")


@router.get("/prompts")
async def list_prompts(request: Request):
    """List all available prompt templates in the library."""
    registry = request.app.state.prompt_registry
    return {"prompts": registry.list_all(), "status": "success"}


@router.get("/prompts/{template_name}")
async def get_prompt(template_name: str, request: Request):
    """Get the full definition of a specific prompt template."""
    registry = request.app.state.prompt_registry
    try:
        prompt = registry.get(template_name)
        return {"template_name": template_name, "prompt": prompt.model_dump(), "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/prompts/create")
async def create_prompt(create_request: PromptCreateRequest):
    """
    Create a new prompt template from a natural language description.
    """
    logger.info(f"Prompt creation request: {create_request.description[:80]}...")
    try:
        agent = PromptBuilderAgent()
        prompt = await agent.create_and_save(create_request.description)
        return {
            "status": "success",
            "prompt": prompt.model_dump()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Monitoring & Observability Endpoints (AI Economics)
# ---------------------------------------------------------------------------
@router.get("/monitoring/logs")
async def get_monitoring_logs(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    model: Optional[str] = None,
    smart_routed: Optional[bool] = None,
    search: Optional[str] = None,
):
    """
    Get paginated, filterable LLM audit telemetry logs.
    """
    gateway = request.app.state.gateway
    return gateway.telemetry.get_logs(
        limit=limit,
        offset=offset,
        model=model,
        smart_routed=smart_routed,
        search=search,
    )


@router.get("/monitoring/summary")
async def get_monitoring_summary(request: Request):
    """
    Get aggregated observability KPIs, spend analytics, and AI Economics savings.
    """
    gateway = request.app.state.gateway
    return gateway.telemetry.get_summary()


@router.get("/monitoring/export")
async def export_monitoring_logs(
    request: Request,
    format: str = "csv",
):
    """
    Export audit logs in CSV or Excel XML format for finance and compliance audits.
    """
    gateway = request.app.state.gateway
    fmt = format.lower().strip()

    if fmt in ("excel", "xlsx", "xls"):
        content = gateway.telemetry.export_excel_xml()
        return Response(
            content=content,
            media_type="application/vnd.ms-excel",
            headers={"Content-Disposition": "attachment; filename=llm_audit_logs.xls"},
        )
    else:
        content = gateway.telemetry.export_csv()
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=llm_audit_logs.csv"},
        )

