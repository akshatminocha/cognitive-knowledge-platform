# Cognitive Knowledge Platform (v2)

An enterprise-grade cognitive knowledge intelligence platform that transforms unstructured multimodal data into an interactive, grounded knowledge fabric. Autonomous multi-agent routing navigates dual graph (Neo4j) and vector (Qdrant) architectures powered by a dynamic Ontology Engine, while an AI Gateway enforces governance guardrails, manages AI economics, and ensures zero LLM lock-in.

---

## What's New in v2.0.0

- **Modular v2 Architecture:** Completely rewritten from monolithic scripts into an asynchronous-first, decoupled multi-package architecture powered by the Google Agent Development Kit (ADK) and Model Context Protocol (MCP).
- **Persistent Data Sources & Traceability:** Dynamic parsing of executed Cypher queries and vector similarity hits, rendering interactive traceability cards that persist across session switches.
- **Enterprise Admin Configuration Hub:** Runtime governance dashboard allowing live toggles of Microsoft Presidio PII/PHI scanners (SSN, Phone, Medical License, Credit Card), prompt injection thresholds, and visual inspection of Domain Schemas.
- **Canonical Session Store:** Multi-session conversation management backed by SQLite and an in-memory Canonical Context Engine, ensuring zero context loss across LLM provider switching.
- **Dynamic Skill Registry:** Hot-reloading YAML skills (`clinical_summary`, `knowledge_qa`, `fraud_detection`) with clinical disambiguation and cross-referencing.
- **Universal Knowledge Artifact (.uka):** One-click export of session histories, graph relationships, vector embeddings, and schema metadata into a portable, vendor-neutral `.uka` zip bundle.
- **Comprehensive Test Suite:** 44/44 passing automated unit, integration, and guardrails tests.

---

## Architecture & Packages

```
cognitive-knowledge-platform/
├── packages/
│   ├── ai-gateway/         # Multi-model routing, LiteLLM fallback chains, rate limiting & caching
│   ├── guardrails/         # PII/PHI masking (Presidio), AST validation (read-only Cypher/SQL), injection defense
│   ├── ontology-engine/    # Multi-domain YAML schemas (healthtech, fintech, edtech, enterprise_ops)
│   ├── mcp-servers/        # Model Context Protocol servers for Neo4j, Qdrant, and PostgreSQL
│   └── agent-harness/      # ADK cognitive runtime, context engine, reflection loops, UKA exporter
└── platform-app/
    ├── backend/            # FastAPI orchestrator, ingestion pipeline, REST API endpoints
    ├── frontend-react/     # React + Vite SPA, dark-mode glassmorphism, Lucide icons, session manager
    └── frontend/           # Streamlit UI (alternative lightweight client)
```

### Core Packages (`packages/`)

- **[AI Gateway](packages/ai-gateway/)**: A cost-aware multi-model router handling AI economics, semantic caching, and rate limiting. Abstracts away provider differences for seamless mid-session model swapping (Gemini, OpenAI, Anthropic, Ollama).
- **[Guardrails Engine](packages/guardrails/)**: Enterprise governance layer. Enforces PII/PHI data masking via Microsoft Presidio, Cypher/SQL AST validation (restricting queries to read-only execution), prompt injection detection, and groundedness verification.
- **[Ontology Engine](packages/ontology-engine/)**: Schema-driven dynamic ontology manager. Governs how unstructured text is mapped into Neo4j graph nodes and edges across domains (`healthtech.yaml`, `fintech.yaml`, `edtech.yaml`, `enterprise_ops.yaml`).
- **[MCP Servers](packages/mcp-servers/)**: Standardized tool servers built with FastMCP over STDIO:
  - `GraphMCP`: Neo4j graph queries and node/edge inspection.
  - `RetrievalMCP`: Qdrant vector collection search and chunk retrieval.
  - `TabularMCP`: PostgreSQL relational query execution.
- **[Agent Harness](packages/agent-harness/)**: The cognitive execution engine. Features step budgets, self-reflection loops, canonical context windowing, and the **Universal Knowledge Artifact (UKA)** exporter.

### Platform Apps (`platform-app/`)

- **Backend (FastAPI)**: Central REST API orchestrator that wires all packages together, exposing endpoints for querying (`/api/v2/query`), ingestion (`/api/v2/ingest`), sessions (`/api/v2/sessions`), diagnostics (`/api/v2/diagnostics`), and admin governance (`/api/v2/admin/config`).
- **Frontend (React + Vite)**: Modern single-page application with dark-mode glassmorphic aesthetics, Lucide React icons, real-time data sources traceability, multi-session management, and UKA export.
- **Frontend (Streamlit)**: Streamlit-based interface providing chat, ingestion, and diagnostics.

---

## The Universal Knowledge Artifact (.uka)

The platform introduces the **Universal Knowledge Artifact (UKA)** format. 

### Why UKA?
In the current AI landscape, conversational memory and semantic context are locked into proprietary vendor ecosystems (e.g., OpenAI Threads, Anthropic context windows, or proprietary enterprise SaaS databases). Moving your AI application to a new model or platform requires starting from scratch.

### What is UKA?
Just as `.pdf` standardized document sharing across operating systems, **`.uka` standardizes the sharing of AI context.** 

Instead of trapping knowledge in a specific vendor's API, the Agent Harness exports your entire session into a vendor-neutral `.uka` zip bundle containing:
- **Conversation State:** Full canonical transcript with timestamps and tool execution traces.
- **Graph Topology:** Extracted entities and relationships exported in portable JSON/JSON-LD.
- **Vector Chunks:** Dense text segments and embedding metadata.
- **Domain Schemas:** The active ontology definitions governing the session.

Export a `.uka` bundle and import it into any UKA-compliant system, mobile app, or internal tool—the receiving agent immediately inherits the exact graph context, memory, and grounded knowledge.

---

## Tech Stack

| Layer | Technologies |
| :--- | :--- |
| **Agent Framework** | Python 3.13+, Google ADK (Agent Development Kit), FastMCP |
| **Graph Database** | Neo4j 5.26 (Bolt, Cypher, GDS) |
| **Vector Database** | Qdrant (HNSW index, Cosine distance) |
| **Relational Database** | PostgreSQL 16 (Session metadata, audit logs) |
| **API & Backend** | FastAPI, Uvicorn, LiteLLM, Microsoft Presidio |
| **Frontend** | React 18, Vite, Lucide Icons, Vanilla CSS (Glassmorphism), Streamlit |
| **Package Management** | `uv` (fast Python package installer & resolver) |

---

## Quick Start

### 1. Prerequisites
- Docker & Docker Compose
- [uv](https://github.com/astral-sh/uv) (Python 3.13+)
- Node.js 18+ (for React frontend)

### 2. Start Infrastructure
```bash
docker compose up -d
```
*Starts Neo4j (`:7687`), Qdrant (`:6333`), and PostgreSQL (`:5432`).*

### 3. Configure Environment
```bash
cp .env.example .env
# Set your LLM API keys:
# GOOGLE_API_KEY=your_key_here
# Optional: OPENAI_API_KEY, ANTHROPIC_API_KEY
```

### 4. Install Dependencies
```bash
uv sync
```

### 5. Launch the Platform
```bash
# Launch FastAPI backend + React frontend (Recommended)
./run.sh --react

# Or launch with Streamlit frontend
./run.sh

# Or launch both frontends simultaneously
./run.sh --all
```

- **React UI:** `http://localhost:5173`
- **FastAPI API & Docs:** `http://localhost:8000/docs`
- **Neo4j Browser:** `http://localhost:7474`
- **Qdrant Dashboard:** `http://localhost:6333/dashboard`

### 6. Stop Services
```bash
./scripts/stop.sh
```

---

## Verification & Testing

Run the full automated test suite using `uv`:

```bash
uv run pytest
```

Output:
```
============================= 44 passed in 18.30s ==============================
```

Test coverage includes:
- `tests/test_agent_harness/`: Canonical message formatting, context windowing, SQLite persistence.
- `tests/test_gateway/`: LiteLLM multi-provider routing, budget enforcement, caching.
- `tests/test_guardrails/`: Presidio PII masking, read-only AST Cypher validation, prompt injection shields.
- `tests/test_integration/`: End-to-end multi-format ingestion pipelines.
- `tests/test_ontology_engine/`: Domain schema loading and LLM entity extraction.

### Running Regression Benchmarks
```bash
uv run python -m evaluation.run_benchmarks --model gemini-2.5-flash
```

---

## License

Apache 2.0. See [LICENSE](LICENSE) for details.
