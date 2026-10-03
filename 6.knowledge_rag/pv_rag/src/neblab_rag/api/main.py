"""FastAPI application factory.

Use the factory pattern (``create_app``) so importing this module has no
side effects. Run with::

    uvicorn neblab_rag.api.main:create_app --factory --reload --port 8000
"""

from fastapi import FastAPI

from neblab_rag.api.routes import health
from neblab_rag.api.routes import query as query_routes
from neblab_rag.config import get_settings
from neblab_rag.logging_config import configure_logging


def create_app() -> FastAPI:
    """Build the FastAPI app with config + logging + routers wired in."""
    settings = get_settings()
    configure_logging(level=settings.log_level)

    app = FastAPI(
        title="NEBLab RAG API",
        version="0.1.0",
        description="北方生态屏障数字实验室 RAG 知识库",
    )
    app.include_router(health.router)
    app.include_router(query_routes.router)
    return app
