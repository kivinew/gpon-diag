"""
Diagnose routes — async diagnosis with polling.
"""
import uuid
import logging
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from web.api.deps import get_db, get_thresholds, get_olt_pool, get_config
from web.api.schemas import (
    DiagnoseRequest,
    DiagnoseResponse,
    DiagnoseStatusResponse,
    DiagnosisReportResponse,
)
from web.api.exceptions import ONTNotFoundError, OLTConnectionError
from core.olt import OntNotFoundError as CoreONTNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory task store (replace with Redis in production)
_diagnosis_tasks: dict[str, dict] = {}


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
async def run_diagnosis_task(task_id: str, req: DiagnoseRequest, thresholds, olt_pool, config):
    """Background task to run diagnosis."""
    _diagnosis_tasks[task_id]["status"] = "running"
    _diagnosis_tasks[task_id]["progress"] = {"step": "connect", "message": "Connecting to OLT..."}

    try:
        # Import here to avoid circular imports
        import anyio
        from diagnose import (
            parse_input, run_diagnosis, find_available_olt, _load_olt_credentials, _build_thresholds
        )

        # Parse input
        input_data = parse_input(req.address)
        _diagnosis_tasks[task_id]["progress"] = {"step": "find", "message": "Locating ONT..."}

        # Resolve OLT
        if req.olt_host:
            olt_config = next((o for o in config.get("olts", []) if o.get("host") == req.olt_host), None)
            if not olt_config:
                raise OLTConnectionError(req.olt_host, "Not found in config")
        else:
            olt_config = find_available_olt(config)

        _diagnosis_tasks[task_id]["progress"] = {"step": "collect", "message": "Collecting ONT data..."}

        # Run diagnosis in thread pool (blocking telnet)
        report = await anyio.to_thread.run_sync(
            run_diagnosis,
            input_data,
            olt_config,
            thresholds,
            req.allow_actions,
            config.get("ping_target", "1.1.1.1"),
            None,  # on_olt_info
            False,  # use_ssh
        )

        # Save to DB
        from web.api.routes.history import save_diagnosis_to_db
        await save_diagnosis_to_db(report, input_data, olt_config)

        _diagnosis_tasks[task_id] = {
            "status": "completed",
            "result": report.to_dict(),
            "progress": {"step": "complete", "message": "Done"},
        }
        logger.info(f"Diagnosis {task_id} completed for {req.address}")

    except CoreONTNotFoundError as e:
        _diagnosis_tasks[task_id] = {
            "status": "failed",
            "error": str(e),
        }
        logger.warning(f"Diagnosis {task_id} failed: {e}")
    except Exception as e:
        logger.exception(f"Diagnosis {task_id} error")
        _diagnosis_tasks[task_id] = {
            "status": "failed",
            "error": str(e),
        }


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────
@router.post("/diagnose", response_model=DiagnoseResponse, summary="Start ONT diagnosis")
async def start_diagnosis(
    req: DiagnoseRequest,
    background_tasks: BackgroundTasks,
    thresholds=Depends(get_thresholds),
    olt_pool=Depends(get_olt_pool),
    config=Depends(get_config),
):
    """Start async diagnosis. Returns task_id for polling."""
    task_id = uuid.uuid4().hex[:12]
    _diagnosis_tasks[task_id] = {"status": "pending", "progress": None, "result": None, "error": None}

    background_tasks.add_task(run_diagnosis_task, task_id, req, thresholds, olt_pool, config)

    return DiagnoseResponse(task_id=task_id, status="pending")


@router.get("/diagnose/{task_id}", response_model=DiagnoseStatusResponse, summary="Get diagnosis status/result")
async def get_diagnosis_status(task_id: str):
    """Poll for diagnosis result."""
    task = _diagnosis_tasks.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    return DiagnoseStatusResponse(
        task_id=task_id,
        status=task["status"],
        progress=task.get("progress"),
        result=task.get("result"),
        error=task.get("error"),
    )


@router.get("/diagnose/{task_id}/report", response_model=DiagnosisReportResponse, summary="Get full report (when completed)")
async def get_diagnosis_report(task_id: str):
    """Get full diagnosis report (only when completed)."""
    task = _diagnosis_tasks.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task["status"] != "completed":
        raise HTTPException(409, f"Task not completed: {task['status']}")
    if not task.get("result"):
        raise HTTPException(500, "Result missing")

    return task["result"]