# Cognitive Knowledge Platform (v2)

An advanced cognition system that securely transforms multimodal data into an interactive knowledge base. Autonomous multi-agent smart routing navigates dual graph and vector architectures powered by a dynamic Ontology Engine, while an AI Gateway enforces governance guardrails, manages AI economics, and ensures zero LLM lock-in experience.

## Architecture & Repositories

The v2 platform has been completely rewritten from a monolithic LangChain application to a highly modular, governance-first agentic system using the Google ADK, Model Context Protocol (MCP), and independent packages.

### Core Packages (`packages/`)

- **[AI Gateway](packages/ai-gateway/)**: A cost-aware multi-model router handling AI economics, semantic caching, and rate limiting. Abstracts away LLM provider differences for seamless mid-session model swapping.
- **[Guardrails Engine](packages/guardrails/)**: The governance layer. Enforces PII/PHI data masking, Cypher/SQL AST validation (read-only execution), prompt injection detection, and groundedness checks.
- **[Ontology Engine](packages/ontology-engine/)**: Schema-driven dynamic ontology manager. Defines how unstructured text is mapped into Neo4j graph nodes for different domains (Healthtech, Fintech, etc.).
- **[MCP Servers](packages/mcp-servers/)**: Standardized data access tool servers using the Model Context Protocol:
  - `GraphMCP` (Neo4j)
  - `RetrievalMCP` (Qdrant)
  - `TabularMCP` (PostgreSQL)
- **[Agent Harness](packages/agent-harness/)**: The cognitive runtime. Features step budgets, self-reflection loops, long/short-term semantic memory, and the **Universal Knowledge Artifact (UKA)** exporter—packaging your session history into a `.uka` bundle for zero-lock-in context portability.

### Platform Apps (`platform-app/`)

- **Backend**: FastAPI orchestrator that wires all packages together, exposing REST endpoints for querying, data ingestion, and schema management.
- **Frontend (Streamlit)**: A Streamlit-based UI with glassmorphism design for the chat interface, ingestion dashboard, skills library, and system diagnostics.
- **Frontend (React)**: A React + Vite SPA with a premium dark-mode glassmorphism UI, offering the same feature set as Streamlit with a richer, more interactive experience.
- **Evaluation**: Golden Q&A benchmark suite for regression testing the agent's accuracy and groundedness.

## The Universal Knowledge Artifact (.uka)

The platform pioneers the **Universal Knowledge Artifact (UKA)** format. Instead of your chat history and memory being locked into OpenAI's threads or Anthropic's context windows, the Agent Harness exports your entire session into a vendor-neutral `.uka` zip bundle. This allows you to hot-swap LLMs (e.g., from GPT-4o to Gemini 2.5) mid-conversation without losing any graph context or semantic memory.

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
