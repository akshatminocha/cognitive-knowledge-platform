# Cognitive Knowledge Platform (v2)

A modular, agentic AI platform for knowledge graph construction, semantic retrieval, and intelligent querying across industry domains.

## Architecture & Repositories

The v2 platform has been completely rewritten from a monolithic LangChain application to a highly modular, governance-first agentic system using the Google ADK, Model Context Protocol (MCP), and independent packages.

### Core Packages (`packages/`)

- **[AI Gateway](packages/ai-gateway/)**: A multi-model router with semantic caching and rate limiting. Abstracts away LLM provider differences and provides fallbacks.
- **[Guardrails Engine](packages/guardrails/)**: The governance layer. Enforces PII/PHI data masking, Cypher/SQL AST validation (read-only execution), prompt injection detection, and groundedness checks.
- **[Ontology Engine](packages/ontology-engine/)**: Schema-driven dynamic ontology manager. Defines how unstructured text is mapped into Neo4j graph nodes for different domains (Healthtech, Fintech, etc.).
- **[MCP Servers](packages/mcp-servers/)**: Standardized data access tool servers using the Model Context Protocol:
  - `GraphMCP` (Neo4j)
  - `RetrievalMCP` (Qdrant)
  - `TabularMCP` (PostgreSQL)
- **[Agent Harness](packages/agent-harness/)**: The cognitive runtime. Wraps the Google ADK with step budgets, a model-agnostic canonical session store (context engine), self-reflection loops, and long/short-term semantic memory.

### Platform Apps (`platform-app/`)

- **Backend**: FastAPI orchestrator that wires all packages together, exposing REST endpoints for querying, data ingestion, and schema management.
- **Frontend (Streamlit)**: A Streamlit-based UI with glassmorphism design for the chat interface, ingestion dashboard, skills library, and system diagnostics.
- **Frontend (React)**: A React + Vite SPA with a premium dark-mode glassmorphism UI, offering the same feature set as Streamlit with a richer, more interactive experience.
- **Evaluation**: Golden Q&A benchmark suite for regression testing the agent's accuracy and groundedness.

## Tech Stack (100% Open Source)

- **Execution**: Python 3.13+, Google ADK v2.6+
- **Data Fabric**: Neo4j (Graph), Qdrant (Vector), PostgreSQL (Tabular)
- **LLM Support**: Gemini, OpenAI, Anthropic, Ollama
- **APIs**: FastAPI, MCP, Streamlit, React + Vite

## Quick Start

### 1. Start Infrastructure
```bash
docker compose up -d
```

### 2. Configure Environment
```bash
cp .env.example .env
# Add your LLM API keys (GOOGLE_API_KEY, etc.)
```

### 3. Install the Platform
```bash
uv sync
```

### 4. Run (One Command)
```bash
# Streamlit frontend (default)
./run.sh

# React frontend
./run.sh --react

# Both frontends
./run.sh --all
```

### 5. Stop Everything
```bash
./scripts/stop.sh
```

See [SETUP.md](SETUP.md) for detailed manual setup instructions and service URLs.

## Running Evaluations
```bash
uv run python -m evaluation.run_benchmarks --model gemini-2.5-flash
```
