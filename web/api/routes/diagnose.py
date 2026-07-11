"""
Diagnose routes — SSE-streamed ONT diagnosis.

The web UI (web/static/js/dashboard.js) opens a streaming fetch to POST /api/diagnose
and reads Server-Sent-Events. Each event is a `json` event with a JSON payload
containing a `type` field. Supported types:
  - {"type": "progress", "step": <str>, "message": <str>}
  - {"type": "history",  "history": [ ... Diagnosis.to_dict() ... ]}
  - {"type": "result",   "report": <human-readable text from DiagnosisReport.to_text()>}
  - {"type": "error",    "message": <str>}
"""
import json
import logging

import anyio
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from web.api.deps import get_thresholds, get_config
from web.api.exceptions import ONTNotFoundError, OLTConnectionError
from core.olt import OntNotFoundError as CoreONTNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter()


async def _event(payload: dict) -> str:
    """Format a Server-Sent-Event."""
    return f"event: json\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/diagnose", summary="Start ONT diagnosis (SSE stream)")
async def start_diagnosis(
    request: Request,
    thresholds=Depends(get_thresholds),
    config=Depends(get_config),
):
    """Run diagnosis and stream progress + human-readable result as SSE.

    Body (JSON): {"address": "F/S/P/ONT"|"serial"|"fl_...", "olt_host": <optional>, "allow_actions": <bool>}
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    address = (body.get("address") or "").strip()
    olt_host = body.get("olt_host") or None
    allow_actions = bool(body.get("allow_actions", True))

    async def event_generator():
        try:
            yield await _event({"type": "progress", "step": "connect", "message": "Подключение к OLT..."})

            from core.utils import parse_input, load_olt_credentials as _load_olt_credentials
            from core.connection_diagnosis import find_available_olt
            from core.config_parser import _build_thresholds
            from core.diagnose_logic import run_diagnosis

            input_data = parse_input(address)
            yield await _event({"type": "progress", "step": "find", "message": "Поиск ONT..."})

            if olt_host:
                olt_config = next(
                    (o for o in config.get("olts", []) if o.get("host") == olt_host), None
                )
                if not olt_config:
                    yield await _event({"type": "error", "message": f"OLT {olt_host} не найден в конфиге"})
                    return
            else:
                olt_config = find_available_olt(config)

            if not olt_config:
                yield await _event({"type": "error", "message": "Нет доступных OLT с корректными учётными данными"})
                return

            username, password = _load_olt_credentials(olt_config)
            if not username or not password:
                yield await _event({"type": "error", "message": f"Нет учётных данных для OLT {olt_config.get('host')}"})
                return

            # Build thresholds from config (ensure correct object type)
            try:
                th = _build_thresholds(config)
            except Exception:
                th = thresholds

            yield await _event({"type": "progress", "step": "collect", "message": "Сбор данных ONT..."})

            def _run():
                return run_diagnosis(
                    input_data,
                    olt_config,
                    th,
                    allow_actions,
                    None,  # log
                    config.get("ping_target", "1.1.1.1"),
                    None,  # on_olt_info
                    False,  # use_ssh
                )

            report = await anyio.to_thread.run_sync(_run)

            yield await _event({"type": "progress", "step": "analyze", "message": "Анализ результатов..."})

            # Save to DB (best-effort)
            try:
                from web.api.deps import get_db
                from web.api.routes.history import save_diagnosis_to_db
                async for db in get_db():
                    await save_diagnosis_to_db(report, input_data, olt_config, db)
                    break
            except Exception as e:
                logger.warning(f"Failed to save diagnosis to DB: {e}")

            # Recent history for this ONT
            try:
                from web.api.deps import get_db
                from sqlalchemy import select
                from web.api.models import Diagnosis
                async for db in get_db():
                    res = await db.execute(
                        select(Diagnosis)
                        .where(Diagnosis.ont_address == report.metrics.address)
                        .order_by(Diagnosis.created_at.desc())
                        .limit(10)
                    )
                    rows = res.scalars().all()
                    hist = []
                    for r in rows:
                        try:
                            hist.append(json.loads(r.report_json) if r.report_json else {})
                        except Exception:
                            pass
                    if hist:
                        yield await _event({"type": "history", "history": hist})
                    break
            except Exception as e:
                logger.warning(f"Failed to load history: {e}")

            yield await _event({"type": "result", "report": report.to_text()})

        except CoreONTNotFoundError as e:
            yield await _event({"type": "error", "message": f"ONT не найдена: {e}"})
        except Exception as e:
            logger.exception("Diagnosis stream error")
            yield await _event({"type": "error", "message": f"Ошибка диагностики: {e}"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
