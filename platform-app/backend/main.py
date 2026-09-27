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

from agent_harness.runner import AgentRunner
from agent_harness.context_engine import ContextEngine
from agent_harness.memory import MemoryManager
from agent_harness.skills.registry import SkillRegistry
from agent_harness.prompts.registry import PromptRegistry
from guardrails.engine import GuardrailEngine
from ai_gateway.gateway import GatewayClient
from ontology_engine.manager import OntologyManager

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

    # Initialize shared resources on startup:
    app.state.gateway = GatewayClient()
    app.state.guardrails = GuardrailEngine()
    app.state.ontology_manager = OntologyManager()
    
    # Initialize registries
    app.state.skill_registry = SkillRegistry()
    app.state.skill_registry.load_directory()
    
    app.state.prompt_registry = PromptRegistry()
    app.state.prompt_registry.load_directory()
    
    # Initialize context engine and memory
    app.state.context_engine = ContextEngine()
    app.state.memory = MemoryManager()
    
    # Initialize the core runner
    app.state.runner = AgentRunner()

    # Initialize optional database clients (graceful degradation if unavailable)
    app.state.qdrant_client = None
    app.state.neo4j_driver = None
    
    try:
        from qdrant_client import AsyncQdrantClient
        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        app.state.qdrant_client = AsyncQdrantClient(url=qdrant_url)
        logger.info(f"Qdrant client initialized ({qdrant_url})")
    except Exception as e:
        logger.warning(f"Qdrant client not available (non-fatal): {e}")

    try:
        from neo4j import AsyncGraphDatabase
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "changeme")
        app.state.neo4j_driver = AsyncGraphDatabase.driver(
            neo4j_uri, auth=(neo4j_user, neo4j_password),
        )
        logger.info(f"Neo4j driver initialized ({neo4j_uri})")
    except Exception as e:
        logger.warning(f"Neo4j driver not available (non-fatal): {e}")

    logger.info("CKP Platform ready")
    yield
    
    # Teardown
    if app.state.qdrant_client:
        try:
            await app.state.qdrant_client.close()
        except Exception:
            pass
    if app.state.neo4j_driver:
        try:
            await app.state.neo4j_driver.close()
        except Exception:
            pass
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
