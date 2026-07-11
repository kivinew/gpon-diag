"""
Page routes — serve Jinja2 UI (dashboard / index / result) and static assets.

The human-readable web UI lives in web/templates + web/static. These routes
make the FastAPI server render them so users don't get raw JSON at "/".
"""
import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import URLPath
from starlette.routing import Mount

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "templates")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static")


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
    return templates.TemplateResponse(request=request, name="dashboard.html")


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def page_dashboard_alias(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html")


@router.get("/index", response_class=HTMLResponse, include_in_schema=False)
async def page_index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


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
