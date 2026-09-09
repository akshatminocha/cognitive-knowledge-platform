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

    return QueryResponse(
        response=result.final_response or "No answer returned.",
        session_id=request_body.session_id or "new-session",
        model_used=request_body.model or "gemini-2.5-flash",
        total_steps=result.total_steps,
        duration_ms=result.total_duration_ms,
        groundedness_score=0.95, # Mocked guardrail for now
        pii_entities_masked=0,
        tools_used=[step.tool_name for step in result.steps if step.tool_name],
    )


@router.get("/sessions")
async def list_sessions():
    """List all active conversation sessions."""
    # TODO: Wire to ContextEngine.list_sessions()
    return {"sessions": []}


@router.delete("/sessions/{session_id}")
async def clear_session(session_id: str):
    """Clear a specific conversation session."""
    # TODO: Wire to ContextEngine.clear_session()
    return {"status": "cleared", "session_id": session_id}


# ---------------------------------------------------------------------------
# Ingestion Endpoints
# ---------------------------------------------------------------------------
@router.post("/ingest", response_model=IngestionResponse)
async def ingest_file(
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

    # TODO: Wire to ingestion pipeline
    logger.info(f"Ingestion request: {file.filename} (schema: {schema_name})")

    return IngestionResponse(
        filename=file.filename,
        status="pending_integration",
        chunks_created=0,
        entities_extracted=0,
        relationships_extracted=0,
        duration_ms=0.0,
    )


@router.get("/ingest/sources")
async def list_ingested_sources():
    """List all ingested data sources."""
    # TODO: Query Qdrant collections + Neo4j labels + PostgreSQL tables
    return {"sources": []}


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
async def get_diagnostics():
    """Get system diagnostics and health info."""
    # TODO: Wire to GuardrailEngine.get_diagnostics(), Gateway stats, Memory stats
    return DiagnosticsResponse(
        platform_version="2.0.0",
        active_schema="healthtech",
        guardrails={},
        gateway={},
        memory={},
    )


@router.get("/diagnostics/guardrails")
async def get_guardrail_diagnostics():
    """Get detailed guardrail configuration and stats."""
    # TODO: Wire to GuardrailEngine.get_diagnostics()
    return {"status": "pending_integration"}


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

