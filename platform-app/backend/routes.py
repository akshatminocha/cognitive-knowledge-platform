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
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, Request
from pydantic import BaseModel, Field

from agent_harness.skills.skill_builder_agent import SkillBuilderAgent
from agent_harness.prompts.prompt_builder_agent import PromptBuilderAgent
from agent_harness.uka_export import UKAExporter
from fastapi.responses import FileResponse
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


# ---------------------------------------------------------------------------
# Query Endpoints
# ---------------------------------------------------------------------------
@router.post("/query", response_model=QueryResponse)
async def query_agent(request_body: QueryRequest, request: Request):
    """
    Send a natural language query to the CKP agent.
    """
    runner = request.app.state.runner
    registry = request.app.state.skill_registry
    gateway = request.app.state.gateway

    skill_name = request_body.active_skill
    
    # Auto-routing if skill is "auto"
    if not skill_name or skill_name == "auto":
        skills = registry.list_all()
        skill_descriptions = [f"- {s['name']}: {s.get('description', '')}" for s in skills]
        sys_prompt = "You are a router. Return ONLY the exact name of the best skill for the query. If none fit, return 'knowledge_qa'."
        user_prompt = f"Query: '{request_body.query}'\nSkills:\n" + "\n".join(skill_descriptions)
        
        try:
            res = await gateway.completion(
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                model=request_body.model
            )
            skill_name = res["choices"][0]["message"]["content"].strip()
            # fallback if hallucinates
            if not any(s["name"] == skill_name for s in skills):
                skill_name = "knowledge_qa"
        except Exception as e:
            logger.warning(f"Auto-routing failed, fallback to knowledge_qa: {e}")
            skill_name = "knowledge_qa"

    logger.info(f"Executing query with skill: {skill_name}")
    
    # Apply skill to runner config
    try:
        if skill_name:
            runner.config.active_skill = registry.get(skill_name)
    except Exception:
        runner.config.active_skill = None

    # Execute the agent
    result = await runner.run(request_body.query, session_id=request_body.session_id)

    # Collect rich data sources from tools
    source_map = {}
    import re
    for step in result.steps:
        if step.tool_name == "semantic_search":
            key = "vector_knowledge_chunks"
            if key not in source_map:
                source_map[key] = {
                    "type": "vector",
                    "label": "Vector Store: knowledge_chunks",
                    "explanation": "Semantic search performed on ingested chunks.",
                    "data": []
                }
            if isinstance(step.tool_output, list):
                for hit in step.tool_output:
                    if isinstance(hit, dict):
                        text = hit.get("text", "")[:150] + "..."
                        fname = hit.get("metadata", {}).get("filename", "Document")
                        source_map[key]["data"].append({"file": fname, "snippet": text})
        
        elif step.tool_name == "execute_cypher":
            labels = ["Neo4j"]
            if step.tool_input and "query" in step.tool_input:
                query = step.tool_input["query"]
                found = re.findall(r":([A-Za-z0-9_]+)", query)
                if found:
                    labels = list(set(found))
            
            label_str = ", ".join(labels)
            key = f"graph_{label_str}"
            
            if key not in source_map:
                source_map[key] = {
                    "type": "graph",
                    "label": f"Graph: {label_str}",
                    "explanation": f"Graph query executed matching {label_str} nodes.",
                    "data": []
                }
            
            if isinstance(step.tool_output, list):
                for record in step.tool_output:
                    rec_str = str(record)
                    source_map[key]["data"].append(rec_str[:150] + ("..." if len(rec_str) > 150 else ""))

    unique_sources = list(source_map.values())[:3]
                        
    return QueryResponse(
        response=result.final_response or "No answer returned.",
        session_id=request_body.session_id or "new-session",
        model_used=request_body.model or "gemini-2.5-flash",
        total_steps=result.total_steps,
        duration_ms=result.total_duration_ms,
        groundedness_score=0.95, # Mocked guardrail for now
        pii_entities_masked=0,
        tools_used=[step.tool_name for step in result.steps if step.tool_name],
        sources=list(unique_sources)
    )


@router.get("/sessions")
async def list_sessions(request: Request):
    """List all active conversation sessions."""
    ctx = request.app.state.context_engine
    return {"sessions": ctx.list_sessions()}


@router.delete("/sessions/{session_id}")
async def clear_session(session_id: str, request: Request):
    """Clear a specific conversation session."""
    ctx = request.app.state.context_engine
    ctx.clear_session(session_id)
    return {"status": "cleared", "session_id": session_id}


@router.get("/sessions/{session_id}/export")
async def export_session(session_id: str, request: Request, format: str = "zip"):
    """Export a session as a Universal Knowledge Artifact (UKA)."""
    ctx = request.app.state.context_engine
    exporter = UKAExporter(ctx)
    
    tmp_dir = Path(tempfile.mkdtemp())
    if format == "json":
        out_path = tmp_dir / f"uka_{session_id}.json"
        exporter.export_to_json(session_id, out_path)
        return FileResponse(out_path, filename=f"{session_id}.json")
    else:
        out_path = tmp_dir / f"uka_{session_id}.uka"
        exporter.export_to_bundle(session_id, out_path)
        return FileResponse(out_path, filename=f"{session_id}.uka")


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

