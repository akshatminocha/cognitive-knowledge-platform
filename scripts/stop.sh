#!/bin/bash

# ==============================================================================
# CKP Stop Script — Gracefully shuts down all platform services
# ==============================================================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Stopping Cognitive Knowledge Platform...${NC}"

# 1. Stop FastAPI backend
if pgrep -f "uvicorn backend.main:app" > /dev/null 2>&1; then
    echo "Stopping FastAPI backend..."
    pkill -f "uvicorn backend.main:app" 2>/dev/null
    echo "  ✓ Backend stopped"
else
    echo "  – Backend not running"
fi

# 2. Stop Streamlit frontend
if pgrep -f "streamlit run" > /dev/null 2>&1; then
    echo "Stopping Streamlit frontend..."
    pkill -f "streamlit run" 2>/dev/null
    echo "  ✓ Streamlit stopped"
else
    echo "  – Streamlit not running"
fi

# 3. Stop React dev server (Vite)
if pgrep -f "vite" > /dev/null 2>&1; then
    echo "Stopping React dev server..."
    pkill -f "vite" 2>/dev/null
    echo "  ✓ React dev server stopped"
else
    echo "  – React dev server not running"
fi

# 4. Stop Docker containers
if docker compose ps --quiet 2>/dev/null | grep -q .; then
    echo "Stopping Docker containers..."
    docker compose down
    echo "  ✓ Docker containers stopped"
else
    echo "  – No Docker containers running"
fi

echo ""
echo -e "${GREEN}==============================${NC}"
echo -e "${GREEN}All services stopped.${NC}"
echo -e "${GREEN}==============================${NC}"
