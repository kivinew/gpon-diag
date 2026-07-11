"""
Action routes — reset LAN, clear BIP, remote ping.
"""
import anyio
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from web.api.deps import get_db, get_thresholds, get_olt_pool, get_config
from web.api.schemas import (
    ResetLanRequest, ClearBipRequest, RemotePingRequest, ActionResponse
)
from web.api.exceptions import ONTNotFoundError, OLTConnectionError
from core.olt import OntNotFoundError as CoreONTNotFoundError, get_olt_connection

logger = logging.getLogger(__name__)

router = APIRouter()


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
async def get_olt_and_location(address: str, olt_host: str | None, config: dict):
    """Resolve OLT connection and ONT location."""
    from core.utils import parse_input, load_olt_credentials as _load_olt_credentials
    from core.connection_diagnosis import find_available_olt

    input_data = parse_input(address)

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

    if input_data["type"] != "address":
        olt = get_olt_connection(olt_config["host"], olt_config.get("port", 23), username, password, 30)
        await anyio.to_thread.run_sync(olt.connect)

        if input_data["type"] == "serial":
            loc = olt.find_ont_by_sn(input_data["value"])
        else:
            loc = olt.find_ont_by_description(input_data["value"])

        if not loc:
            raise ONTNotFoundError(input_data["value"], olt_config["host"])
        input_data.update(loc)

    return olt_config, input_data, username, password


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────
@router.post("/actions/reset-lan", response_model=ActionResponse, summary="Reset LAN port (off→on)")
async def reset_lan(
    req: ResetLanRequest,
    config=Depends(get_config),
    olt_pool=Depends(get_olt_pool),
):
    """Reset LAN port: operational-state off then on, then clear error counters."""
    try:
        olt_config, input_data, username, password = await get_olt_and_location(
            req.address, req.olt_host, config
        )

        olt = get_olt_connection(
            olt_config["host"], olt_config.get("port", 23), username, password, 30
        )
        await anyio.to_thread.run_sync(olt.connect)

        # Reset port
        await anyio.to_thread.run_sync(
            olt.reset_lan_port,
            input_data["frame"], input_data["slot"],
            input_data["port"], input_data["ont_id"], req.lan_id
        )

        # Clear errors
        await anyio.to_thread.run_sync(
            olt.clear_eth_errors,
            input_data["frame"], input_data["slot"],
            input_data["port"], input_data["ont_id"], req.lan_id
        )

        return ActionResponse(
            success=True,
            message=f"LAN{req.lan_id} reset and errors cleared on {req.address}"
        )
    except CoreONTNotFoundError as e:
        raise ONTNotFoundError(str(e), req.olt_host)
    except Exception as e:
        logger.exception(f"Reset LAN failed for {req.address}")
        raise OLTConnectionError(req.olt_host or "unknown", str(e))


@router.post("/actions/clear-bip", response_model=ActionResponse, summary="Clear BIP error counters")
async def clear_bip(
    req: ClearBipRequest,
    config=Depends(get_config),
    olt_pool=Depends(get_olt_pool),
):
    """Clear upstream/downstream BIP error counters."""
    try:
        olt_config, input_data, username, password = await get_olt_and_location(
            req.address, req.olt_host, config
        )

        olt = get_olt_connection(
            olt_config["host"], olt_config.get("port", 23), username, password, 30
        )
        await anyio.to_thread.run_sync(olt.connect)

        await anyio.to_thread.run_sync(
            olt.clear_line_quality,
            input_data["frame"], input_data["slot"],
            input_data["port"], input_data["ont_id"]
        )

        return ActionResponse(
            success=True,
            message=f"BIP errors cleared on {req.address}"
        )
    except CoreONTNotFoundError as e:
        raise ONTNotFoundError(str(e), req.olt_host)
    except Exception as e:
        logger.exception(f"Clear BIP failed for {req.address}")
        raise OLTConnectionError(req.olt_host or "unknown", str(e))


@router.post("/actions/ping", response_model=ActionResponse, summary="Remote ping from ONT")
async def remote_ping(
    req: RemotePingRequest,
    config=Depends(get_config),
    olt_pool=Depends(get_olt_pool),
):
    """Execute remote ping from ONT to target IP."""
    try:
        olt_config, input_data, username, password = await get_olt_and_location(
            req.address, req.olt_host, config
        )

        olt = get_olt_connection(
            olt_config["host"], olt_config.get("port", 23), username, password, 30
        )
        await anyio.to_thread.run_sync(olt.connect)

        output = await anyio.to_thread.run_sync(
            olt.remote_ping,
            input_data["frame"], input_data["slot"],
            input_data["port"], input_data["ont_id"],
            req.target_ip
        )

        # Parse result
        from core.parser import parse_ping_result
        from core.models import OntMetrics

        metrics = OntMetrics()
        parse_ping_result(output, metrics)

        return ActionResponse(
            success=True,
            message=f"Ping to {req.target_ip}: {metrics.ping_status}",
            data={
                "transmit": metrics.ping_result.get("transmit", 0),
                "receive": metrics.ping_result.get("receive", 0),
                "lost": metrics.ping_result.get("lost", 0),
                "loss_pct": metrics.ping_result.get("loss_pct", -1),
                "avg_rtt": metrics.ping_result.get("avg_rtt", -1),
            }
        )
    except CoreONTNotFoundError as e:
        raise ONTNotFoundError(str(e), req.olt_host)
    except Exception as e:
        logger.exception(f"Remote ping failed for {req.address}")
        raise OLTConnectionError(req.olt_host or "unknown", str(e))