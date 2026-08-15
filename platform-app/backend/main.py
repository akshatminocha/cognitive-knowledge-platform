"""
CKP Platform Backend — FastAPI application.

The v2 platform backend that wires together all packages:
- AI Gateway for LLM routing
- Guardrails for safety
- Agent Harness for execution
- MCP Servers for data access
- Ontology Engine for schema management
"""

from __future__ import annotations

import logging
import os

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes import router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# ---------------------------------------------------------------------------
# Lifespan: startup / shutdown hooks
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — initialize and tear down shared resources."""
    logger.info("CKP Platform starting up...")

    # TODO: Initialize shared resources on startup:
    # - AI Gateway instance
    # - GuardrailEngine instance
    # - OntologyManager with active schema
    # - AgentRunner with all components wired
    # These will be stored in app.state for route handlers to access.

    logger.info("CKP Platform ready")
    yield
    logger.info("CKP Platform shutting down...")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Cognitive Knowledge Platform",
    description=(
        "A modular, agentic AI platform for knowledge graph construction, "
        "semantic retrieval, and intelligent querying across industry domains."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — allow Streamlit frontend and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",  # Streamlit default
        "http://localhost:3000",  # React dev server
        "http://localhost:5173",  # Vite dev server
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routes
app.include_router(router, prefix="/api/v2")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "platform": "Cognitive Knowledge Platform",
    }
