"""
History routes — query stored diagnosis reports.
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from web.api.deps import get_db
from web.api.schemas import HistoryQueryParams, HistoryItem, HistoryResponse
from web.api.models import Diagnosis

logger = logging.getLogger(__name__)

router = APIRouter()


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────
@router.get("/history", response_model=HistoryResponse, summary="Query diagnosis history")
async def get_history(
    params: HistoryQueryParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Search historical diagnosis results with filters."""
    query = select(Diagnosis)

    # Filters
    conditions = []
    if params.q:
        q = f"%{params.q}%"
        conditions.append(or_(
            Diagnosis.ont_address.ilike(q),
            Diagnosis.input_value.ilike(q),
        ))

    if params.olt_host:
        conditions.append(Diagnosis.olt_host == params.olt_host)

    if params.status == "online":
        # Need to check JSON in report_json
        # For now, we'll use a simple approach - filter after query
        pass
    elif params.status == "offline":
        pass

    if params.date_from:
        try:
            dt_from = datetime.fromisoformat(params.date_from)
            conditions.append(Diagnosis.created_at >= dt_from)
        except ValueError:
            pass

    if params.date_to:
        try:
            dt_to = datetime.fromisoformat(params.date_to)
            conditions.append(Diagnosis.created_at <= dt_to)
        except ValueError:
            pass

    if conditions:
        query = query.where(and_(*conditions))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Pagination + ordering
    query = query.order_by(desc(Diagnosis.created_at)).offset(params.offset).limit(params.limit)

    result = await db.execute(query)
    records = result.scalars().all()

    history_items = []
    for r in records:
        try:
            import json
            report = json.loads(r.report_json) if r.report_json else {}
        except (json.JSONDecodeError, TypeError):
            report = {}

        # Determine online status from report
        is_online = report.get("is_online", True)
        if params.status and params.status == "online" and not is_online:
            continue
        if params.status and params.status == "offline" and is_online:
            continue

        history_items.append(HistoryItem(
            id=r.id,
            timestamp=r.timestamp,
            created_at=r.created_at.isoformat(),
            olt_name=r.olt_name,
            olt_host=r.olt_host,
            ont_address=r.ont_address,
            input_type=r.input_type,
            input_value=r.input_value,
            is_online=is_online,
            problems_count=len(report.get("problems", [])),
            model=report.get("model"),
            version=report.get("version"),
            ont_rx_power=report.get("ont_rx_power"),
            olt_rx_power=report.get("olt_rx_power"),
            distance_m=report.get("distance_m"),
            ping_status=report.get("ping_status"),
        ))

    return HistoryResponse(
        history=history_items,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


@router.get("/history/{diag_id}", summary="Get single diagnosis by ID")
async def get_history_detail(diag_id: int, db: AsyncSession = Depends(get_db)):
    """Get full diagnosis report by ID."""
    result = await db.execute(select(Diagnosis).where(Diagnosis.id == diag_id))
    record = result.scalar_one_or_none()

    if not record:
        return {"error": "Record not found"}, 404

    try:
        import json
        report = json.loads(record.report_json) if record.report_json else {}
    except (json.JSONDecodeError, TypeError):
        report = {}

    return {
        "id": record.id,
        "timestamp": record.timestamp,
        "created_at": record.created_at.isoformat(),
        "olt_name": record.olt_name,
        "olt_host": record.olt_host,
        "ont_address": record.ont_address,
        "input_type": record.input_type,
        "input_value": record.input_value,
        "report": report,
    }


async def save_diagnosis_to_db(report, input_data: dict, olt_config: dict):
    """Save diagnosis report to database (called from diagnose route)."""
    from web.api.deps import get_session_maker
    from web.api.models import Diagnosis

    async with get_session_maker()() as session:
        import json
        diag = Diagnosis(
            timestamp=report.timestamp,
            olt_host=olt_config.get("host", ""),
            olt_name=olt_config.get("name", ""),
            ont_address=report.metrics.address,
            input_type=input_data["type"],
            input_value=input_data.get("value", ""),
            report_json=json.dumps(report.to_dict(), ensure_ascii=False),
        )
        session.add(diag)
        await session.commit()
        await session.refresh(diag)
        return diag.id