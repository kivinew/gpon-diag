"""
Optics routes — real-time optical data.
"""
import anyio
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from web.api.deps import get_db, get_thresholds, get_olt_pool, get_config
from web.api.schemas import OpticsRequest, OpticsResponse
from web.api.exceptions import ONTNotFoundError, OLTConnectionError
from core.olt import OntNotFoundError as CoreONTNotFoundError, get_olt_connection

logger = logging.getLogger(__name__)

router = APIRouter()


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
async def collect_optics_data(address: str, olt_host: str | None, thresholds, config, olt_pool):
    """Collect optics data for an ONT."""
    from diagnose import parse_input, _load_olt_credentials
    from core.parser import parse_ont_info, parse_optical_info, parse_line_quality
    from core.models import OntMetrics

    input_data = parse_input(address)

    # Resolve OLT
    if olt_host:
        olt_config = next((o for o in config.get("olts", []) if o.get("host") == olt_host), None)
        if not olt_config:
            raise OLTConnectionError(olt_host, "Not found in config")
    else:
        from diagnose import find_available_olt
        olt_config = find_available_olt(config)

    if not olt_config:
        raise OLTConnectionError(olt_host or "auto", "No available OLT")

    # Resolve ONT location if needed
    if input_data["type"] != "address":
        username, password = _load_olt_credentials(olt_config)
        if not username or not password:
            raise OLTConnectionError(olt_config["host"], "Missing credentials")

        olt = get_olt_connection(olt_config["host"], olt_config.get("port", 23), username, password, 30)
        await anyio.to_thread.run_sync(olt.connect)

        if input_data["type"] == "serial":
            loc = olt.find_ont_by_sn(input_data["value"])
        else:
            loc = olt.find_ont_by_description(input_data["value"])

        if not loc:
            raise ONTNotFoundError(input_data["value"], olt_config["host"])
        input_data.update(loc)

    # Collect optics data
    username, password = _load_olt_credentials(olt_config)
    olt = get_olt_connection(olt_config["host"], olt_config.get("port", 23), username, password, 30)
    await anyio.to_thread.run_sync(olt.connect)

    raw_data = await anyio.to_thread.run_sync(
        olt.collect_ont,
        input_data["frame"], input_data["slot"], input_data["port"], input_data["ont_id"],
        lambda *a, **k: None  # silent log
    )

    # Parse
    metrics = OntMetrics()
    metrics.address = f"{input_data['frame']}/{input_data['slot']}/{input_data['port']}/{input_data['ont_id']}"

    if "ont_info" in raw_data:
        parse_ont_info(raw_data["ont_info"], metrics)
    if "optical_info" in raw_data:
        parse_optical_info(raw_data["optical_info"], metrics)
    if "line_quality" in raw_data:
        parse_line_quality(raw_data["line_quality"], metrics)

    return OpticsResponse(
        ont_rx_power=metrics.ont_rx_power,
        olt_rx_power=metrics.olt_rx_power,
        ont_tx_power=metrics.ont_tx_power,
        laser_bias_current=metrics.laser_bias_current,
        ont_temperature=metrics.ont_temperature,
        supply_voltage=metrics.supply_voltage,
        distance_m=metrics.distance_m,
        upstream_errors=metrics.upstream_errors,
        downstream_errors=metrics.downstream_errors,
        total_bip_errors=metrics.total_bip_errors,
        is_online=metrics.is_online,
        model=metrics.model,
        serial=metrics.serial,
        description=metrics.description,
    )


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────
@router.get("/optics/{address}", response_model=OpticsResponse, summary="Get ONT optics data")
async def get_optics(
    address: str,
    olt_host: str | None = Query(None, description="Specific OLT host"),
    thresholds=Depends(get_thresholds),
    olt_pool=Depends(get_olt_pool),
    config=Depends(get_config),
):
    """Get real-time optical parameters for an ONT."""
    try:
        result = await collect_optics_data(address, olt_host, thresholds, config, olt_pool)
        return result
    except CoreONTNotFoundError as e:
        raise ONTNotFoundError(str(e), olt_host)
    except Exception as e:
        logger.exception(f"Optics collection failed for {address}")
        raise OLTConnectionError(olt_host or "unknown", str(e))