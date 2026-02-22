from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
import os
import shutil

from ..agents.orchestrator import KnowledgeAgent
from ..ingestion.pipeline import IngestionPipeline

router = APIRouter()

# Global instances (singleton pattern for demo)
agent = None
ingestion_pipeline = IngestionPipeline() 
# Agent initialization might be delayed until needed or startup to avoid errors if keys missing
# But for now, we'll lazy load or init on module load if safely handled.

class ChatRequest(BaseModel):
    query: str
    user_id: Optional[str] = "default_user"

class ChatResponse(BaseModel):
    response: str
    tool_usage: List[str] = []

@router.on_event("startup")
async def startup_event():
    global agent
    try:
        agent = KnowledgeAgent()
        print("Agent initialized successfully.")
    except Exception as e:
        print(f"Failed to initialize Agent: {e}")

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    global agent
    if not agent:
        raise HTTPException(status_code=503, detail="Agent system not initialized")
    
    try:
        result = agent.ask(request.query)
        # Result is now a dict with "output" and "tool_usage"
        answer = result.get("output", "No response generated.")
        steps = result.get("tool_usage", [])
        
        return ChatResponse(response=str(answer), tool_usage=steps)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ingest")
async def ingest_data():
    """Triggers the ingestion pipeline manually."""
    try:
        # Build logic to run ingestion in background task usually
        # For demo, run synchronous
        ingestion_pipeline.run()
        return {"status": "Ingestion completed successfully"}
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Uploads a file to the processing directory."""
    try:
        file_location = os.path.join("data/unstructured", file.filename)
        # Ensure directory exists relative to run location
        os.makedirs(os.path.dirname(file_location), exist_ok=True)
        
        with open(file_location, "wb+") as file_object:
            shutil.copyfileobj(file.file, file_object)
            
        return {"info": f"file '{file.filename}' saved at '{file_location}'"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
