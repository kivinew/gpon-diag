"""
GPON Diagnostics API — FastAPI application.
Entry point for uvicorn / systemd service.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging
import os

from web.api.deps import get_config, get_db, get_olt_pool, lifespan_init, lifespan_shutdown
from web.api.exceptions import register_exception_handlers
from web.api.routes import (
    diagnose, optics, search, actions, history, port_summary, olts, health, ws, pages
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Lifespan — startup / shutdown
# ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await lifespan_init()
    logger.info("Application startup complete")
    yield
    # Shutdown
    await lifespan_shutdown()
    logger.info("Application shutdown complete")


# ──────────────────────────────────────────────
# FastAPI App
# ──────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title="GPON Diagnostics API",
        version="0.2.0",
        description="REST API + WebSocket for Huawei GPON ONT diagnostics",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS — allow Vite dev server + production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    register_exception_handlers(app)

    # API routes
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(diagnose.router, prefix="/api", tags=["diagnose"])
    app.include_router(optics.router, prefix="/api", tags=["optics"])
    app.include_router(search.router, prefix="/api", tags=["search"])
    app.include_router(actions.router, prefix="/api", tags=["actions"])
    app.include_router(history.router, prefix="/api", tags=["history"])
    app.include_router(port_summary.router, prefix="/api", tags=["port-summary"])
    app.include_router(olts.router, prefix="/api", tags=["olts"])
    # WebSocket routes (no /api prefix)
    app.include_router(ws.router, tags=["websocket"])

    # Page routes (serve Jinja2 UI)
    app.include_router(pages.router, tags=["pages"])
    pages.mount_static(app)

    return app


app = create_app()


# ──────────────────────────────────────────────
# Entry point for: uv run python -m web.api.main
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "web.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # True only in dev
        log_level="info",
    )