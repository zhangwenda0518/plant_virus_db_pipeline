"""FastAPI application factory for Plant Virus RAG.

Run with:
    uvicorn plant_virus_rag.api.main:create_pv_app --factory --reload --port 8001
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from neblab_rag.config import get_settings
from neblab_rag.logging_config import configure_logging
from plant_virus_rag.api.routes import health
from plant_virus_rag.api.routes import query as query_routes


def create_pv_app() -> FastAPI:
    """Build the Plant Virus RAG FastAPI app."""
    settings = get_settings()
    configure_logging(level=settings.log_level)

    app = FastAPI(
        title="Plant Virus RAG API",
        version="0.1.0",
        description="Plant Virus Database RAG Knowledge Base",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:8001"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(query_routes.router)
    return app
