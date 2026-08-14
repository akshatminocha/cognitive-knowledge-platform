# Cognitive Knowledge Platform

## Overview
This platform integrates **MongoDB Atlas (Vector Search)** and **Neo4j (Graph RAG)** with **Gemini Pro** to provide a grounded, intelligent question-answering system over heterogeneous enterprise data.

## Features
-   **Synthetic Data Generation**: `backend/src/generation/synthetic_data.py`
-   **Multi-Modal Ingestion**: Supports PDF, MD, CSV.
-   **Hybrid Retrieval**: Combines Vector similarity with Graph traversal.
-   **Agentic Reasoning**: Gemini Agent selects the best tool for the job.

## Setup Instructions

### 1. Prerequisites
- Docker Desktop
- Python 3.10+
- Google API Key

### 2. Environment Setup
Rename `.env.example` to `.env` and add your API key:
```bash
cp .env.example .env
# Edit .env and set GOOGLE_API_KEY=AIzaSy...
```

### 3. Start Infrastructure
Run the following command to spin up MongoDB and Neo4j:
```bash
docker-compose up -d
```
*Note: Ensure Docker is running first.*

### 4. Install Dependencies
```bash
python3 -m venv .kb-venv
source .kb-venv/bin/activate
pip install -r requirements.txt
```

### 5. Run the Platform
Use the helper script to launch Backend and Frontend:
```bash
chmod +x run.sh
./run.sh
```
Or run manually:
- **Backend**: `uvicorn backend.src.main:app --reload`
- **Frontend**: `streamlit run frontend/app.py`
