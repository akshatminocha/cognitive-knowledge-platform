# =============================================================================
# Cognitive Knowledge Platform — Makefile
# =============================================================================

.PHONY: setup start stop dev frontend frontend-react test test-gateway test-guardrails test-ontology test-mcp test-harness test-integration eval lint clean infra-up infra-down

# --- Setup ---
setup:
	@echo "Installing uv (if not present)..."
	@command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
	@echo "Syncing workspace dependencies..."
	uv sync
	@echo "Copying .env.example to .env (if not exists)..."
	@test -f .env || cp .env.example .env
	@echo "Installing React frontend dependencies..."
	cd platform-app/frontend-react && npm install --silent
	@echo "Setup complete."

# --- Infrastructure ---
infra-up:
	docker compose up -d
	@echo "Neo4j UI:  http://localhost:7474"
	@echo "Qdrant UI: http://localhost:6333/dashboard"

infra-down:
	docker compose down

# --- Run (One Command) ---
start:
	./run.sh

stop:
	./scripts/stop.sh

# --- Development ---
dev:
	@echo "Starting FastAPI backend..."
	uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	@echo "Starting Streamlit frontend..."
	uv run streamlit run platform-app/frontend/app.py --server.port 8501

frontend-react:
	@echo "Starting React frontend..."
	cd platform-app/frontend-react && npm run dev

# --- Testing ---
test:
	uv run pytest tests/ -v

test-gateway:
	uv run pytest tests/test_gateway/ -v

test-guardrails:
	uv run pytest tests/test_guardrails/ -v

test-ontology:
	uv run pytest tests/test_ontology/ -v

test-mcp:
	uv run pytest tests/test_mcp/ -v

test-harness:
	uv run pytest tests/test_harness/ -v

test-integration:
	uv run pytest tests/test_integration/ -v

# --- Evaluation ---
eval:
	uv run python evaluation/run_benchmarks.py --schema healthtech --model gemini-2.5-flash

# --- E2E Validation ---
validate:
	bash scripts/validate_e2e.sh

# --- Linting ---
lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .

# --- Cleanup ---
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .ruff_cache dist build
	rm -rf platform-app/frontend-react/dist
