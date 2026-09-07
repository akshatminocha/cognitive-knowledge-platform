# CKP v2 — Local Setup Guide

This guide walks you through configuring, installing, and running the Cognitive Knowledge Platform (v2) locally. The v2 architecture is highly modular and utilizes a `uv` workspace.

## 1. Prerequisites
- **Python 3.13+**
- **uv** (Package manager. Install via `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Docker Desktop** (Required for the data fabric)

## 2. Environment Configuration
Copy the environment template and add your API keys:
```bash
cp .env.example .env
# Edit .env and set GOOGLE_API_KEY for the Gemini Agent
```

## 3. Start Infrastructure
Start the data fabric (Neo4j, Qdrant, PostgreSQL) in the background:
```bash
docker-compose up -d
```
*Wait ~10 seconds for the databases to initialize and pass their health checks.*

## 4. Install Packages (via `uv`)
Since CKP v2 is configured as a `uv.workspace` in the root `pyproject.toml`, installation is a single command. It will automatically resolve all internal dependencies between packages (`ckp-ai-gateway`, `ckp-agent-harness`, `ckp-platform-app`, etc.) and install them in editable mode.

```bash
uv sync
```

**Post-Install Step**: The Guardrails engine uses Presidio to detect PII, which requires downloading a SpaCy NLP model. You can choose the model size based on your machine's resources:

- **Large** (Recommended, ~1GB RAM): `uv run spacy download en_core_web_lg`
- **Medium** (~100MB RAM, faster startup): `uv run spacy download en_core_web_md`
- **Small** (~30MB RAM, lightest): `uv run spacy download en_core_web_sm`

```bash
# Example: Download the large model
uv run spacy download en_core_web_lg
```
*(Note: If you use the medium or small model, you will need to update the model name in your guardrails config accordingly).*

## 5. Generate Synthetic Data
Before starting the application, generate some demo data for the Neo4j and Qdrant databases.
```bash
uv run python -m platform-app.backend.generation.synthetic_data
```
*This outputs CSV files to `platform-app/data/synthetic/`.*

## 6. Run the Platform

**Start the Backend (FastAPI)**:
```bash
uv run uvicorn platform-app.backend.main:app --reload --port 8000
```

**Start the Frontend (Streamlit)** (in a new terminal):
```bash
uv run streamlit run platform-app/frontend/app.py
```

## 7. Validate Functionality
You can manually test the APIs to ensure everything is connected:

```bash
# Check health
curl http://localhost:8000/health

# Run an agent query
curl -X POST http://localhost:8000/api/v2/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What medications is patient PAT-001 taking?", "schema_name": "healthtech"}'
```

## 8. Run the Evaluation Suite (Optional)
To test the agent's performance against the golden benchmark dataset:
```bash
# Offline mode (validates the pipeline, no LLM calls made)
uv run python -m evaluation.run_benchmarks --offline

# Full benchmark mode (makes live LLM calls)
uv run python -m evaluation.run_benchmarks --model gemini-2.5-flash
```

## 9. Teardown
To shut everything down:
```bash
# Stop backend and frontend with Ctrl+C in their respective terminals
docker-compose down
```
