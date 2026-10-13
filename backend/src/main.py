from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.routes import router as api_router
from .config import Config

app = FastAPI(title="Cognitive Knowledge Platform", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routes
app.include_router(api_router, prefix="/api/v1")

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "cognitive-knowledge-platform"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.src.main:app", host=Config.BACKEND_HOST, port=int(Config.BACKEND_PORT), reload=True)
