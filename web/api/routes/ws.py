"""
WebSocket routes for real-time updates.
"""
import json
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends

from web.api.deps import get_config
from web.api.schemas import WSMessage

logger = logging.getLogger(__name__)

router = APIRouter()

# Connection managers for different WS types
_port_ws_connections: dict[str, list[WebSocket]] = {}
_optics_ws_connections: dict[str, list[WebSocket]] = {}
_diagnose_ws_connections: dict[str, list[WebSocket]] = {}


async def connect_ws(ws: WebSocket, pool: dict, key: str):
    await ws.accept()
    if key not in pool:
        pool[key] = []
    pool[key].append(ws)
    logger.debug(f"WS connected: {key} (total: {len(pool[key])})")


def disconnect_ws(ws: WebSocket, pool: dict, key: str):
    if key in pool and ws in pool[key]:
        pool[key].remove(ws)
        if not pool[key]:
            del pool[key]
    logger.debug(f"WS disconnected: {key}")


async def broadcast(pool: dict, key: str, message: dict):
    """Broadcast message to all connections in pool for key."""
    if key not in pool:
        return
    dead = []
    for ws in pool[key]:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        disconnect_ws(ws, pool, key)


# ──────────────────────────────────────────────
# Port Summary WebSocket
# ──────────────────────────────────────────────
@router.websocket("/ws/port-summary")
async def ws_port_summary(
    ws: WebSocket,
    frame: str = Query(...),
    slot: str = Query(...),
    port: str = Query(...),
    olt_host: Optional[str] = Query(None),
    config=Depends(get_config),
):
    """WebSocket for real-time port summary updates."""
    key = f"{olt_host or 'auto'}:{frame}/{slot}/{port}"
    await connect_ws(ws, _port_ws_connections, key)

    try:
        # Send initial snapshot
        from web.api.routes.port_summary import get_port_summary
        from web.api.schemas import PortSummaryRequest

        req = PortSummaryRequest(frame=frame, slot=slot, port=port, olt_host=olt_host)
        result = await get_port_summary(req.frame, req.slot, req.port, req.olt_host, config)
        await ws.send_json({"type": "snapshot", **result.model_dump()})

        # Keep alive - client will receive broadcasts from background task
        while True:
            await ws.receive_text()  # Keep connection alive
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Port summary WS error: {e}")
    finally:
        disconnect_ws(ws, _port_ws_connections, key)


# ──────────────────────────────────────────────
# Optics WebSocket
# ──────────────────────────────────────────────
@router.websocket("/ws/optics")
async def ws_optics(
    ws: WebSocket,
    address: str = Query(...),
    olt_host: Optional[str] = Query(None),
    config=Depends(get_config),
):
    """WebSocket for real-time optics updates."""
    key = f"{olt_host or 'auto'}:{address}"
    await connect_ws(ws, _optics_ws_connections, key)

    try:
        # Send initial data
        from web.api.routes.optics import get_optics

        result = await get_optics(address, olt_host, None, None, config)
        await ws.send_json({"type": "optics", "data": result.model_dump()})

        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Optics WS error: {e}")
    finally:
        disconnect_ws(ws, _optics_ws_connections, key)


# ──────────────────────────────────────────────
# Diagnosis Progress WebSocket
# ──────────────────────────────────────────────
@router.websocket("/ws/diagnose/{task_id}")
async def ws_diagnose_progress(
    ws: WebSocket,
    task_id: str,
):
    """WebSocket for diagnosis progress updates."""
    await connect_ws(ws, _diagnose_ws_connections, task_id)

    try:
        # Send current status if available
        from web.api.routes.diagnose import _diagnosis_tasks
        if task_id in _diagnosis_tasks:
            task = _diagnosis_tasks[task_id]
            await ws.send_json({
                "type": "progress",
                "step": task.get("progress", {}).get("step", "pending"),
                "message": task.get("progress", {}).get("message", "Waiting..."),
            })

        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Diagnose WS error: {e}")
    finally:
        disconnect_ws(ws, _diagnose_ws_connections, task_id)


# ──────────────────────────────────────────────
# Public broadcast functions (for background tasks)
# ──────────────────────────────────────────────
async def broadcast_port_summary(key: str, data: dict):
    """Broadcast port summary update to all connected clients."""
    await broadcast(_port_ws_connections, key, {"type": "update", **data})


async def broadcast_optics(key: str, data: dict):
    """Broadcast optics update to all connected clients."""
    await broadcast(_optics_ws_connections, key, {"type": "optics", "data": data})


async def broadcast_diagnose_progress(task_id: str, step: str, message: str, percent: Optional[int] = None):
    """Broadcast diagnosis progress to connected clients."""
    await broadcast(_diagnose_ws_connections, task_id, {
        "type": "progress",
        "step": step,
        "message": message,
        "percent": percent,
    })


async def broadcast_diagnose_complete(task_id: str, report: dict):
    """Broadcast diagnosis completion."""
    await broadcast(_diagnose_ws_connections, task_id, {
        "type": "complete",
        "report": report,
    })


async def broadcast_diagnose_error(task_id: str, error: str):
    """Broadcast diagnosis error."""
    await broadcast(_diagnose_ws_connections, task_id, {
        "type": "error",
        "message": error,
    })