"""
History routes — query past diagnoses.
"""
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from web.api.deps import get_db, get_config
from web.api.schemas import HistoryQueryParams, HistoryResponse, HistoryItem
from web.api.models import Diagnosis, PortSnapshot

logger = logging.getLogger(__name__)

router = APIRouter()


# ──────────────────────────────────────────────
# Helper: save diagnosis to DB
# ──────────────────────────────────────────────
async def save_diagnosis_to_db(report, input_data: dict, olt_config: dict, db: AsyncSession):
    """Save diagnosis report to database."""
    from web.api.models import Diagnosis
    import json

    diag = Diagnosis(
        timestamp=report.timestamp,
        olt_host=olt_config.get("host", ""),
        olt_name=olt_config.get("name", ""),
        ont_address=report.metrics.address,
        input_type=input_data.get("type", "address"),
        input_value=input_data.get("value", report.metrics.address),
        report_json=json.dumps(report.to_dict(), ensure_ascii=False),
    )
    db.add(diag)
    await db.commit()
    await db.refresh(diag)
    return diag


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────
@router.get("/history", response_model=HistoryResponse, summary="Query diagnosis history")
async def get_history(
    q: Optional[str] = Query(None, description="Search query (address, serial, description)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    olt_host: Optional[str] = Query(None, description="Filter by OLT host"),
    date_from: Optional[str] = Query(None, description="ISO date from"),
    date_to: Optional[str] = Query(None, description="ISO date to"),
    status: Optional[str] = Query(None, description="Filter by status (online/offline)"),
    db: AsyncSession = Depends(get_db),
):
    """Query historical diagnoses with filters."""
    stmt = select(Diagnosis)

    # Search query
    if q:
        stmt = stmt.where(
            or_(
                Diagnosis.ont_address.contains(q),
                Diagnosis.input_value.contains(q),
                Diagnosis.olt_name.contains(q),
            )
        )

    # Filters
    if olt_host:
        stmt = stmt.where(Diagnosis.olt_host == olt_host)

    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            stmt = stmt.where(Diagnosis.created_at >= dt_from)
        except ValueError:
            pass

    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            stmt = stmt.where(Diagnosis.created_at <= dt_to)
        except ValueError:
            pass

    if status == "online":
        stmt = stmt.where(Diagnosis.report_json.contains('"is_online": true'))
    elif status == "offline":
        stmt = stmt.where(Diagnosis.report_json.contains('"is_online": false'))

    # Total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()

    # Paginated results
    stmt = stmt.order_by(Diagnosis.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    records = result.scalars().all()

    history = []
    for r in records:
        import json
        report = json.loads(r.report_json) if r.report_json else {}

        history.append(HistoryItem(
            id=r.id,
            timestamp=r.timestamp,
            created_at=r.created_at.isoformat() if r.created_at else "",
            olt_name=r.olt_name,
            olt_host=r.olt_host,
            ont_address=r.ont_address,
            input_type=r.input_type,
            input_value=r.input_value,
            is_online=report.get("is_online", True),
            problems_count=len(report.get("problems", [])),
            model=report.get("model"),
            version=report.get("version"),
            ont_rx_power=report.get("ont_rx_power") if report.get("ont_rx_power", 999) < 900 else None,
            olt_rx_power=report.get("olt_rx_power") if report.get("olt_rx_power", 999) < 900 else None,
            distance_m=report.get("distance_m") if report.get("distance_m", -1) >= 0 else None,
            ping_status=report.get("ping_status"),
        ))

    return HistoryResponse(history=history, total=total, limit=limit, offset=offset)


@router.get("/history/{diag_id}", summary="Get single diagnosis by ID")
async def get_history_detail(diag_id: int, db: AsyncSession = Depends(get_db)):
    """Get full diagnosis report by ID."""
    result = await db.execute(select(Diagnosis).where(Diagnosis.id == diag_id))
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(404, "Record not found")

    import json
    report = json.loads(record.report_json) if record.report_json else {}

    return {
        "id": record.id,
        "timestamp": record.timestamp,
        "created_at": record.created_at.isoformat() if record.created_at else "",
        "olt_name": record.olt_name,
        "olt_host": record.olt_host,
        "ont_address": record.ont_address,
        "input_type": record.input_type,
        "input_value": record.input_value,
        "report": report,
    }