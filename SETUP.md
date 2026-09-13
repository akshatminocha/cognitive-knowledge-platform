# CKP v2 — Local Setup Guide

This guide walks you through configuring, installing, and running the Cognitive Knowledge Platform (v2) locally.

## Prerequisites
- **Python 3.13+**
- **Node.js 18+** and **npm** (for the React frontend)
- **uv** (Python package manager. Install: `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Docker Desktop** (for Neo4j, Qdrant, PostgreSQL databases)

---

## Quick Start (One Command)

### Start Everything
```bash
# Default: Docker + Backend + Streamlit frontend
./run.sh

# Alternative: Docker + Backend + React frontend
./run.sh --react

# Both frontends simultaneously
./run.sh --all
```

### Stop Everything
```bash
./scripts/stop.sh
```

---

## Manual Setup (Step by Step)

### 1. Environment Configuration
```bash
cp .env.example .env
# Edit .env and set GOOGLE_API_KEY for the Gemini Agent
```

### 2. Start Databases
Start the data fabric (Neo4j, Qdrant, PostgreSQL) via Docker:
```bash
docker compose up -d
```
Wait ~10 seconds for databases to initialize and pass their health checks.

### 3. Install Python Packages
CKP v2 is configured as a `uv.workspace`. A single command installs all internal packages (`ckp-ai-gateway`, `ckp-agent-harness`, `ckp-platform-app`, etc.) in editable mode:
```bash
uv sync
```

**Post-install (optional):** Download a SpaCy NLP model for PII detection:
```bash
uv run spacy download en_core_web_lg
```

### 4. Start the Backend (FastAPI)
```bash
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Start a Frontend

**Option A — Streamlit** (in a new terminal):
```bash
uv run streamlit run platform-app/frontend/app.py --server.port 8501
```

**Option B — React** (in a new terminal):
```bash
cd platform-app/frontend-react
npm install
npm run dev
```

---

## Service URLs

| Service           | URL                                    | Notes                     |
|-------------------|----------------------------------------|---------------------------|
| **FastAPI Backend**   | http://localhost:8000              | REST API + `/health`      |
| **API Docs (Swagger)**| http://localhost:8000/docs         | Interactive API explorer  |
| **Streamlit Frontend**| http://localhost:8501              | Python-based UI           |
| **React Frontend**    | http://localhost:5173              | Vite dev server           |
| **Neo4j Browser**     | http://localhost:7474              | Graph DB UI               |
| **Qdrant Dashboard**  | http://localhost:6333/dashboard    | Vector DB dashboard       |
| **PostgreSQL**        | `postgresql://ckp_user:changeme@localhost:5432/ckp_db` | Tabular DB |

---

## Manual Stop (Step by Step)

### Stop Frontend & Backend
Press `Ctrl+C` in each terminal running the frontend/backend.

If running in the background:
```bash
pkill -f "uvicorn backend.main:app"    # Stop backend
pkill -f "streamlit run"                # Stop Streamlit
pkill -f "vite"                         # Stop React dev server
```

### Stop Databases
```bash
docker compose down
```

> **⚠️ Caution:** To also wipe all database data: `docker compose down -v`

---

## Validate Functionality

### Quick API test
```bash
# Health check
curl http://localhost:8000/health

# Agent query
curl -X POST http://localhost:8000/api/v2/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What can you help me with?", "schema_name": "healthtech"}'
```

### Full E2E Validation
```bash
bash scripts/validate_e2e.sh
```

---

## Run Evaluations (Optional)
```bash
# Offline mode (validates pipeline, no LLM calls)
uv run python -m evaluation.run_benchmarks --offline

# Full benchmark (makes live LLM calls)
uv run python -m evaluation.run_benchmarks --model gemini-2.5-flash
```
