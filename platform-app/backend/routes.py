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

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

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
async def query_agent(request: QueryRequest):
    """
    Send a natural language query to the CKP agent.

    The query flows through the full governance pipeline:
    1. Input guardrails (PII masking + injection detection)
    2. Agent execution with MCP tools
    3. Output guardrails (groundedness check)
    4. PII re-hydration (if authorized)
    """
    # TODO: Wire to AgentRunner.run()
    # runner = app.state.runner
    # result = await runner.run(request.query, session_id=request.session_id)

    return QueryResponse(
        response="[Agent integration pending — Phase 7 scaffold]",
        session_id=request.session_id or "new-session",
        model_used=request.model or "gemini-2.5-flash",
        total_steps=0,
        duration_ms=0.0,
        groundedness_score=0.0,
        pii_entities_masked=0,
        tools_used=[],
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
async def list_schemas():
    """List all available domain schemas."""
    # TODO: Wire to OntologyManager.list_available()
    return SchemaListResponse(
        schemas=["healthtech", "fintech", "edtech", "enterprise_ops"],
        active="healthtech",
    )


@router.get("/schemas/{schema_name}")
async def get_schema(schema_name: str):
    """Get the full schema definition for a domain."""
    # TODO: Wire to OntologyManager.load(schema_name).model_dump()
    return {"schema_name": schema_name, "status": "pending_integration"}


@router.get("/schemas/{schema_name}/prompt")
async def get_schema_prompt(schema_name: str):
    """Get the LLM-ready schema prompt for a domain."""
    # TODO: Wire to OntologyManager.get_schema_prompt(schema_name)
    return {"schema_name": schema_name, "prompt": "pending_integration"}


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
