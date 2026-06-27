"""FastAPI REST API routes for Scrutator."""

import os
import yaml
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scrutator.api")
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime

from core.research_agent import ResearchAgent
from memory.types import MemoryEntry, PreferenceMemory

# Initialize configuration
def load_config() -> dict:
    from core.config import get_config_path
    config_path = get_config_path("settings.yaml")
    if not os.path.exists(config_path):
        return {
            "model": {"provider": "openrouter", "model": "openrouter/free", "temperature": 0.7},
            "search": {"searxng_url": "http://localhost:8888", "fallback_to_public": True},
            "research": {"loop_limits": {"quick": 3, "balanced": 7, "deep": 15}, "confidence_threshold": 85, "min_sources": 10},
            "memory": {"enabled": True, "storage_type": "json", "storage_path": "./memory_store.json"},
            "output": {"reports_dir": "./reports"},
            "translation": {"enabled": True}
        }
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

config = load_config()
agent = ResearchAgent(config)

from fastapi import Depends, Header, HTTPException, status
import secrets

API_KEY = os.getenv("SCRUTATOR_API_KEY") or config.get("api_key")
if not API_KEY:
    API_KEY = secrets.token_hex(16)
    logger.info(f"\n=================================================="
                f"\nGenerated Random REST API Master Key: {API_KEY}"
                f"\nPass this key in the 'X-API-Key' header of requests."
                f"\n==================================================\n")

def verify_api_key(x_api_key: str = Header(None)):
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key in 'X-API-Key' header"
        )

import time
from collections import defaultdict

# Rate Limiter
class RateLimiter:
    def __init__(self, requests_per_minute: int = 100):
        self.requests_per_minute = requests_per_minute
        self.requests = defaultdict(list)
    
    def is_allowed(self, client_id: str) -> bool:
        now = time.time()
        # Clean old entries
        self.requests[client_id] = [
            t for t in self.requests[client_id]
            if now - t < 60
        ]
        if len(self.requests[client_id]) >= self.requests_per_minute:
            return False
        self.requests[client_id].append(now)
        return True

_rate_limiter = RateLimiter()

app = FastAPI(
    title="Scrutator Research API",
    description="REST endpoints for controlling Scrutator research agent and memory system.",
    version="0.1.0"
)

# CORS configuration
cors_origins_str = os.getenv("CORS_ORIGINS") or config.get("cors_origins", "*")
cors_origins = [o.strip() for o in cors_origins_str.split(",") if o.strip()] if cors_origins_str != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True if cors_origins != ["*"] else False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait.")
    return await call_next(request)

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }

# Request Models
class ResearchRequest(BaseModel):
    query: str
    mode: Optional[str] = "balanced"
    languages: Optional[List[str]] = ["en"]
    regions: Optional[List[str]] = []
    memory_mode: Optional[str] = "auto"

class MemoryCreateRequest(BaseModel):
    type: str  # preference, knowledge, feedback
    topic: str
    content: str

# Endpoints
@app.get("/status")
def get_status():
    """Retrieve service configuration and status information."""
    return {
        "status": "Online",
        "provider": config.get("model", {}).get("provider"),
        "model": config.get("model", {}).get("model"),
        "memory_enabled": config.get("memory", {}).get("enabled"),
        "storage_type": config.get("memory", {}).get("storage_type")
    }

@app.post("/research", dependencies=[Depends(verify_api_key)])
def trigger_research(request: ResearchRequest):
    """Trigger a new autonomous research run."""
    try:
        report_data = agent.run(
            query=request.query,
            languages=request.languages,
            mode=request.mode,
            regions=request.regions,
            memory_mode=request.memory_mode
        )
        return {
            "query": report_data["query"],
            "overall_confidence": report_data["overall_confidence"],
            "sources_count": len(report_data["sources"]),
            "report_path": report_data["report_path"],
            "findings": {
                "summary": report_data["findings"].get("summary"),
                "key_insights": report_data["findings"].get("key_insights")
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/memories", dependencies=[Depends(verify_api_key)])
def get_memories():
    """Retrieve all memories in the vault."""
    if not agent.memory:
        return {"memories": [], "message": "Memory system disabled"}
    return {"memories": [m.to_dict() for m in agent.memory.entries]}

@app.post("/memories", dependencies=[Depends(verify_api_key)])
def add_memory(request: MemoryCreateRequest):
    """Save a new preference or knowledge memory manually."""
    if not agent.memory:
        raise HTTPException(status_code=400, detail="Memory system is disabled")
    
    timestamp = datetime.now()
    entry_id = f"api_{timestamp.strftime('%Y%m%d_%H%M%S')}"
    
    if request.type.lower() == "preference":
        entry = PreferenceMemory(id=entry_id, topic=request.topic, content=request.content, timestamp=timestamp)
    else:
        entry = MemoryEntry(id=entry_id, topic=request.topic, content=request.content, type=request.type.lower(), timestamp=timestamp)
        
    agent.memory.add(entry)
    return {"status": "Success", "id": entry_id}

@app.post("/memories/compress", dependencies=[Depends(verify_api_key)])
def compress_memories():
    """Trigger memory archival and compression."""
    if not agent.memory:
        raise HTTPException(status_code=400, detail="Memory system is disabled")
    agent.memory.compress()
    return {"status": "Success", "message": "Memory compressed"}

@app.get("/reports", dependencies=[Depends(verify_api_key)])
def list_reports():
    """List all saved research reports."""
    reports_dir = config.get("output", {}).get("reports_dir", "./reports")
    if not os.path.exists(reports_dir):
        return {"reports": []}
    files = [f for f in os.listdir(reports_dir) if f.endswith(".md")]
    return {"reports": files}

@app.get("/reports/{filename}", dependencies=[Depends(verify_api_key)])
def get_report(filename: str):
    """Retrieve a completed report file."""
    reports_dir = config.get("output", {}).get("reports_dir", "./reports")
    file_path = os.path.join(reports_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(file_path, media_type="text/markdown", filename=filename)
