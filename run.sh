#!/bin/bash

# 1. Start Infrastructure
echo "Starting Database Infrastructure..."
docker compose up -d

# 2. Check for .env
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "⚠️  Please update .env with your required LLM API keys (e.g., GOOGLE_API_KEY, OPENAI_API_KEY)!"
fi

# 3. Sync dependencies
echo "Syncing dependencies via uv..."
uv sync

# 4. Start Backend (in background)
echo "Starting FastAPI Backend..."
nohup uv run uvicorn platform_app.backend.main:app --host 0.0.0.0 --port 8000 --reload > backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend running (PID: $BACKEND_PID)"

# 5. Start Frontend
echo "Starting Streamlit Frontend..."
uv run streamlit run platform-app/frontend/app.py --server.port 8501
