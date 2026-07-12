"""
Page routes — serve Jinja2 UI (dashboard / index / result) and static assets.

The human-readable web UI lives in web/templates + web/static. These routes
make the FastAPI server render them so users don't get raw JSON at "/".
"""
import os
import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import URLPath
from starlette.routing import Mount

logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "templates")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static")


def _get_olts_from_config() -> list:
    """Load OLT list from config.yaml for template dropdowns."""
    try:
        import yaml
        # Resolve config.yaml relative to project root (same logic as deps.get_config)
        here = Path(__file__).resolve()
        candidates = [
            here.parents[3] / "config.yaml",   # project root via parents
            here.parents[2] / "config.yaml",   # fallback: web/api/../../
            Path.cwd() / "config.yaml",         # CWD
        ]
        for cfg_path in candidates:
            if cfg_path.exists():
                with cfg_path.open("r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                return config.get("olts", [])
        logger.warning("config.yaml not found in any expected location")
        return []
    except Exception as e:
        logger.warning(f"Failed to load OLT config: {e}")
        return []


def _get_history_from_db() -> list:
    """Load recent diagnosis history from DB for template tables."""
    try:
        from web.api.deps import get_session_maker
        from sqlalchemy import select
        from web.api.models import Diagnosis
        import asyncio

        session_maker = get_session_maker()
        # Use a new event loop if none is running (sync context)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're inside an async context — schedule via anyio
            import anyio
            result = anyio.from_thread.run(_sync_load_history, session_maker)
            return result
        else:
            return _sync_load_history(session_maker)
    except Exception as e:
        logger.warning(f"Failed to load history for template: {e}")
        return []


def _sync_load_history(session_maker) -> list:
    """Synchronous helper to load history rows."""
    from web.api.models import Diagnosis
    from sqlalchemy import select

    with session_maker() as session:
        stmt = (
            select(Diagnosis)
            .order_by(Diagnosis.created_at.desc())
            .limit(50)
        )
        rows = session.execute(stmt).scalars().all()
        result = []
        for row in rows:
            result.append({
                "id": row.id,
                "olt_name": row.olt_name,
                "olt_host": row.olt_host,
                "ont_address": row.ont_address,
                "input_value": row.input_value,
                "created_at": row.created_at,
                "report": None,  # report is parsed from report_json on demand
            })
        return result


class StaticMount(Mount):
    """Mount that resolves url_for('static', filename='x') for Jinja2 templates.

    Starlette's Mount.url_path_for only handles ``path=`` kwargs; the project
    templates call it with ``filename=``. This subclass maps that kwarg to a
    concrete path so templates don't need editing.
    """

    def url_path_for(self, name: str, **path_params: str):
        if name == "static":
            path = path_params.get("path") or path_params.get("filename")
            if path is not None:
                base = "/" + self.path.strip("/") + "/"
                return URLPath(base + path.lstrip("/"))
        return super().url_path_for(name, **path_params)


templates = Jinja2Templates(directory=os.path.abspath(TEMPLATES_DIR))
# The Jinja2 UI was authored for Flask, which injects `get_flashed_messages`.
# FastAPI/Jinja2 has no flash system, so provide a no-op so templates render.
templates.env.globals["get_flashed_messages"] = lambda with_categories=False: []

router = APIRouter()


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def page_dashboard(request: Request):
    olts = _get_olts_from_config()
    return templates.TemplateResponse(
        request=request, name="dashboard.html",
        context={"olts": olts, "history": []},
    )


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def page_dashboard_alias(request: Request):
    olts = _get_olts_from_config()
    return templates.TemplateResponse(
        request=request, name="dashboard.html",
        context={"olts": olts, "history": []},
    )


@router.get("/index", response_class=HTMLResponse, include_in_schema=False)
async def page_index(request: Request):
    olts = _get_olts_from_config()
    return templates.TemplateResponse(
        request=request, name="index.html",
        context={"olts": olts, "history": []},
    )


@router.get("/result", response_class=HTMLResponse, include_in_schema=False)
async def page_result(request: Request):
    return templates.TemplateResponse(request=request, name="result.html")


def mount_static(app) -> None:
    """Mount /static assets (web/static/js, css) used by the Jinja2 UI.

    Named "static" because templates call url_for('static', filename=...).
    Uses StaticMount so the `filename=` kwarg resolves to the file path.
    """
    if os.path.isdir(STATIC_DIR):
        # Append the StaticMount directly to the router so our url_path_for
        # override (handling the `filename=` kwarg) is the one the router
        # calls. app.mount() would wrap it in an outer Mount that never
        # delegates `filename=` down to our subclass.
        app.router.routes.append(
            StaticMount("/static", app=StaticFiles(directory=STATIC_DIR), name="static")
        )
