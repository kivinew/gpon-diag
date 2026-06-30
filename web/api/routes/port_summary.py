"""
Port Summary routes — get all ONTs on a GPON port.
"""
import anyio
import logging
from fastapi import APIRouter, Depends, Query, HTTPException

from web.api.deps import get_config
from web.api.schemas import PortSummaryRequest, PortSummaryResponse, OntSummaryItem
from web.api.exceptions import ONTNotFoundError, OLTConnectionError
from core.olt import OntNotFoundError as CoreONTNotFoundError, get_olt_connection

logger = logging.getLogger(__name__)

router = APIRouter()


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────
@router.get(
    "/port-summary/{frame}/{slot}/{port}",
    response_model=PortSummaryResponse,
    summary="Get all ONTs on a GPON port"
)
async def get_port_summary(
    frame: str,
    slot: str,
    port: str,
    olt_host: str | None = Query(None, description="Specific OLT host"),
    config=Depends(get_config),
):
    """Get 'display ont info summary' for all ONTs on a GPON port."""
    from diagnose import _load_olt_credentials, find_available_olt

    # Resolve OLT
    if olt_host:
        olt_config = next((o for o in config.get("olts", []) if o.get("host") == olt_host), None)
        if not olt_config:
            raise OLTConnectionError(olt_host, "Not found in config")
    else:
        olt_config = find_available_olt(config)

    if not olt_config:
        raise OLTConnectionError(olt_host or "auto", "No available OLT")

    username, password = _load_olt_credentials(olt_config)
    if not username or not password:
        raise OLTConnectionError(olt_config["host"], "Missing credentials")

    # Collect port summary
    olt = get_olt_connection(olt_config["host"], olt_config.get("port", 23), username, password, 30)
    await anyio.to_thread.run_sync(olt.connect)

    try:
        summaries = await anyio.to_thread.run_sync(
            olt.collect_port_summary,
            frame, slot, port,
            lambda *a, **k: None
        )
    except CoreONTNotFoundError as e:
        raise ONTNotFoundError(str(e), olt_config["host"])

    # Convert to response
    items = []
    for s in summaries:
        items.append(OntSummaryItem(
            ont_id=str(s.ont_id),
            status=s.status,
            rx_power=s.rx_power if s.rx_power < 900 else None,
            tx_power=s.tx_power if s.tx_power < 900 else None,
            distance=s.distance if s.distance >= 0 else None,
            last_down_cause=s.last_down_cause,
            description=s.description,
            collected_at=s.collected_at,
            is_online=s.is_online,
            rx_power_status=s.rx_power_status,
        ))

    return PortSummaryResponse(
        summaries=items,
        count=len(items),
        frame=frame,
        slot=slot,
        port=port,
        olt_host=olt_config["host"],
        olt_name=olt_config.get("name", olt_config["host"]),
    )