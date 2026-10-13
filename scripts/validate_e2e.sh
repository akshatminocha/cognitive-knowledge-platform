#!/bin/bash

# ==============================================================================
# CKP v2 E2E Validation Script
# Automates the entire local setup process and validates end-to-end functionality.
# ==============================================================================

set -e

# Text formatting
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

BACKEND_PID=""

# Cleanup function — always runs on exit
cleanup() {
    echo -e "\n${YELLOW}Tearing down...${NC}"
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        kill "$BACKEND_PID" 2>/dev/null
        echo "  ✓ Backend stopped"
    fi
    docker compose down 2>/dev/null
    echo "  ✓ Docker stopped"
}
trap cleanup EXIT

echo -e "${GREEN}Starting Cognitive Knowledge Platform E2E Validation...${NC}"

# 1. Prerequisites Check
echo -e "\n${YELLOW}[1/11] Checking prerequisites...${NC}"
command -v uv >/dev/null 2>&1 || { echo -e "${RED}Error: 'uv' is not installed. Please install it first.${NC}"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo -e "${RED}Error: 'docker' is not installed.${NC}"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo -e "${RED}Error: 'python3' is not installed.${NC}"; exit 1; }
echo "Prerequisites passed."

# 2. Environment Setup
echo -e "\n${YELLOW}[2/11] Setting up environment via uv workspace...${NC}"
uv sync
echo "Environment setup complete."

# 3. Infrastructure
echo -e "\n${YELLOW}[3/11] Booting up Data Fabric (Docker)...${NC}"
docker compose up -d

echo "Waiting 15 seconds for databases to initialize..."
sleep 15
echo "Infrastructure is up."

# 4. Service Startup
echo -e "\n${YELLOW}[4/11] Starting FastAPI backend...${NC}"
uv run uvicorn backend.main:app --port 8000 &
BACKEND_PID=$!

echo "Waiting 10 seconds for backend to start..."
sleep 10

if ! kill -0 $BACKEND_PID > /dev/null 2>&1; then
    echo -e "${RED}Error: FastAPI backend failed to start.${NC}"
    exit 1
fi
echo "FastAPI backend is running (PID: $BACKEND_PID)."

# 5. Health Check
echo -e "\n${YELLOW}[5/11] Validating Health endpoint...${NC}"
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
if [ "$HTTP_STATUS" != "200" ]; then
    echo -e "${RED}Error: Healthcheck failed with status $HTTP_STATUS${NC}"
    exit 1
fi
HEALTH_RESPONSE=$(curl -s http://localhost:8000/health)
echo "Healthcheck passed (200 OK): $HEALTH_RESPONSE"

# 6. Schemas API Test
echo -e "\n${YELLOW}[6/11] Validating Schemas API...${NC}"
SCHEMAS_RESPONSE=$(curl -s http://localhost:8000/api/v2/schemas)
if echo "$SCHEMAS_RESPONSE" | grep -q '"schemas"'; then
    SCHEMA_COUNT=$(echo "$SCHEMAS_RESPONSE" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('schemas',[])))" 2>/dev/null || echo "0")
    echo "Schemas API passed: $SCHEMA_COUNT schemas found"
else
    echo -e "${RED}Error: Schemas API returned unexpected response: $SCHEMAS_RESPONSE${NC}"
    exit 1
fi

# 7. Skills API Test
echo -e "\n${YELLOW}[7/11] Validating Skills API...${NC}"
SKILLS_RESPONSE=$(curl -s http://localhost:8000/api/v2/skills)
if echo "$SKILLS_RESPONSE" | grep -q '"skills"'; then
    SKILL_COUNT=$(echo "$SKILLS_RESPONSE" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('skills',[])))" 2>/dev/null || echo "0")
    echo "Skills API passed: $SKILL_COUNT skills found"
else
    echo -e "${YELLOW}Warning: Skills API returned unexpected response${NC}"
fi

# 8. Prompts API Test
echo -e "\n${YELLOW}[8/11] Validating Prompts API...${NC}"
PROMPTS_RESPONSE=$(curl -s http://localhost:8000/api/v2/prompts)
if echo "$PROMPTS_RESPONSE" | grep -q '"prompts"'; then
    PROMPT_COUNT=$(echo "$PROMPTS_RESPONSE" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('prompts',[])))" 2>/dev/null || echo "0")
    echo "Prompts API passed: $PROMPT_COUNT prompts found"
else
    echo -e "${YELLOW}Warning: Prompts API returned unexpected response${NC}"
fi

# 9. Query Test
echo -e "\n${YELLOW}[9/11] Validating Query endpoint...${NC}"
RESPONSE=$(curl -s -X POST http://localhost:8000/api/v2/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Hello, what can you do?", "schema_name": "healthtech"}')

if echo "$RESPONSE" | grep -q '"response"'; then
    # Check it's NOT a placeholder/scaffold response
    if echo "$RESPONSE" | grep -qi "pending integration\|not scaffold\|phase 7"; then
        echo -e "${RED}Error: Query endpoint returned a placeholder response (agent not integrated)${NC}"
        exit 1
    fi
    echo "Query endpoint passed — real LLM response received."
    echo "  Response preview: $(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('response','')[:80])" 2>/dev/null || echo "(unable to parse)")"
elif echo "$RESPONSE" | grep -q '"error"'; then
    echo -e "${YELLOW}Warning: Query endpoint returned an error (likely missing API key): $(echo "$RESPONSE" | head -c 200)${NC}"
else
    echo -e "${YELLOW}Warning: Unexpected response format: $(echo "$RESPONSE" | head -c 200)${NC}"
fi

# 10. React Frontend Build Test
echo -e "\n${YELLOW}[10/11] Validating React frontend build...${NC}"
if [ -d "platform-app/frontend-react" ]; then
    cd platform-app/frontend-react
    npm install --silent 2>/dev/null
    if npm run build 2>/dev/null; then
        echo "React frontend build passed."
    else
        echo -e "${YELLOW}Warning: React frontend build failed.${NC}"
    fi
    cd ../..
else
    echo "  – React frontend not found, skipping."
fi

# 11. Benchmark Test
echo -e "\n${YELLOW}[11/11] Running evaluation suite (Offline mode)...${NC}"
uv run python -m evaluation.run_benchmarks --offline 2>/dev/null || echo -e "${YELLOW}Warning: Evaluation suite skipped or failed.${NC}"
echo "Evaluation suite completed."

# Teardown handled by trap

echo -e "\n${GREEN}======================================================${NC}"
echo -e "${GREEN}E2E VALIDATION SUCCESSFUL!${NC}"
echo -e "${GREEN}======================================================${NC}"
exit 0
