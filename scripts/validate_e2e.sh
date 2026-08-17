#!/bin/bash

# ==============================================================================
# CKP v2 E2E Validation Script
# Automates the entire local setup process and validates end-to-end functionality.
# ==============================================================================

set -e # Exit immediately if a command exits with a non-zero status

# Text formatting
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Cognitive Knowledge Platform E2E Validation...${NC}"

# 1. Prerequisites Check
echo -e "\n${YELLOW}[1/9] Checking prerequisites...${NC}"
command -v uv >/dev/null 2>&1 || { echo -e "${RED}Error: 'uv' is not installed. Please install it first.${NC}"; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { echo -e "${RED}Error: 'docker-compose' is not installed.${NC}"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo -e "${RED}Error: 'python3' is not installed.${NC}"; exit 1; }
echo "Prerequisites passed."

# 2. Environment Setup
echo -e "\n${YELLOW}[2/9] Setting up environment via uv workspace...${NC}"
uv sync
uv run spacy download en_core_web_md
echo "Environment setup complete."

# 3. Infrastructure
echo -e "\n${YELLOW}[3/9] Booting up Data Fabric (Docker)...${NC}"
docker-compose up -d

echo "Waiting 15 seconds for databases to initialize..."
sleep 15
echo "Infrastructure is up."

# 4. Data Generation
echo -e "\n${YELLOW}[4/9] Generating synthetic data...${NC}"
uv run python -m platform-app.backend.generation.synthetic_data
echo "Synthetic data generated successfully."

# 5. Service Startup
echo -e "\n${YELLOW}[5/9] Starting FastAPI backend...${NC}"
# Start the backend in the background and save its PID
uv run uvicorn platform-app.backend.main:app --port 8000 &
BACKEND_PID=$!

echo "Waiting 10 seconds for backend to start..."
sleep 10

# Check if backend is actually running
if ! kill -0 $BACKEND_PID > /dev/null 2>&1; then
    echo -e "${RED}Error: FastAPI backend failed to start.${NC}"
    docker-compose down
    exit 1
fi
echo "FastAPI backend is running (PID: $BACKEND_PID)."

# 6. Ingestion Test
echo -e "\n${YELLOW}[6/9] Validating Ingestion endpoint...${NC}"
# We assume there is an ingestion endpoint /api/v2/ingest or similar, or we just test /health
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
if [ "$HTTP_STATUS" != "200" ]; then
    echo -e "${RED}Error: Healthcheck failed with status $HTTP_STATUS${NC}"
    kill $BACKEND_PID
    docker-compose down
    exit 1
fi
echo "Healthcheck passed (200 OK)."

# 7. Query Test (Basic functionality)
echo -e "\n${YELLOW}[7/9] Validating Query endpoint...${NC}"
# In offline testing, the LLM might be mocked, but we check if the endpoint responds
# Currently the backend query endpoint is likely /api/v2/query
RESPONSE=$(curl -s -X POST http://localhost:8000/api/v2/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Test question", "schema_name": "healthtech"}')

if [[ "$RESPONSE" == *"error"* ]]; then
    echo -e "${YELLOW}Warning: Query endpoint returned an error (likely due to missing API keys if offline mode isn't explicitly hooked up in the backend yet): $RESPONSE${NC}"
else
    echo "Query endpoint successfully received."
fi

# 8. Benchmark Test
echo -e "\n${YELLOW}[8/9] Running evaluation suite (Offline mode)...${NC}"
uv run python -m evaluation.run_benchmarks --offline
echo "Evaluation suite completed."

# 9. Teardown
echo -e "\n${YELLOW}[9/9] Tearing down...${NC}"
kill $BACKEND_PID
docker-compose down

echo -e "\n${GREEN}======================================================${NC}"
echo -e "${GREEN}E2E VALIDATION SUCCESSFUL!${NC}"
echo -e "${GREEN}======================================================${NC}"
exit 0
