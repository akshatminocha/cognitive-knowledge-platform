#!/bin/bash

# ==============================================================================
# CKP Run Script — Starts all platform services
#
# Usage:
#   ./run.sh              Start with Streamlit frontend (default)
#   ./run.sh --react      Start with React frontend
#   ./run.sh --all        Start both Streamlit and React frontends
# ==============================================================================

set -e

FRONTEND_MODE="${1:-streamlit}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${GREEN}Starting Cognitive Knowledge Platform...${NC}"

# 1. Start Infrastructure
echo -e "\n${YELLOW}[1/4] Starting Database Infrastructure...${NC}"
docker compose up -d

# 2. Check for .env
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "⚠️  Please update .env with your required LLM API keys (e.g., GOOGLE_API_KEY)!"
fi

# 3. Sync dependencies
echo -e "\n${YELLOW}[2/4] Syncing Python dependencies via uv...${NC}"
uv sync

# 4. Start Backend (in background)
echo -e "\n${YELLOW}[3/4] Starting FastAPI Backend...${NC}"
nohup uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload > backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend running (PID: $BACKEND_PID)"

# 5. Start Frontend(s)
echo -e "\n${YELLOW}[4/4] Starting Frontend...${NC}"

if [ "$FRONTEND_MODE" = "--react" ]; then
    echo -e "${CYAN}Mode: React (Vite)${NC}"
    echo -e "Installing React dependencies..."
    cd platform-app/frontend-react && npm install --silent && cd ../..
    echo -e "Starting React dev server on http://localhost:5173..."
    cd platform-app/frontend-react && npm run dev
elif [ "$FRONTEND_MODE" = "--all" ]; then
    echo -e "${CYAN}Mode: Both (Streamlit + React)${NC}"
    # Start React in background
    echo -e "Installing React dependencies..."
    cd platform-app/frontend-react && npm install --silent && cd ../..
    nohup bash -c 'cd platform-app/frontend-react && npm run dev' > /dev/null 2>&1 &
    echo "React dev server starting on http://localhost:5173..."
    # Start Streamlit in foreground
    echo "Starting Streamlit on http://localhost:8501..."
    uv run streamlit run platform-app/frontend/app.py --server.port 8501
else
    echo -e "${CYAN}Mode: Streamlit${NC}"
    echo "Starting Streamlit on http://localhost:8501..."
    uv run streamlit run platform-app/frontend/app.py --server.port 8501
fi
