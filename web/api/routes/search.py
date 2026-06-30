"""
Search routes — find ONT by serial, address, or description.
"""
import anyio
import logging
from fastapi import APIRouter, Depends
from concurrent.futures import ThreadPoolExecutor, as_completed

from web.api.deps import get_config
from web.api.schemas import SearchRequest, SearchResponse, SearchResultItem
from web.api.exceptions import ONTNotFoundError, OLTConnectionError
from core.olt import OntNotFoundError as CoreONTNotFoundError, get_olt_connection, OltConnection

logger = logging.getLogger(__name__)

router = APIRouter()


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def search_on_single_olt(olt_config: dict, input_data: dict) -> SearchResultItem | None:
    """Search ONT on a single OLT (sync, for thread pool)."""
    from diagnose import _load_olt_credentials
    from core.parser import parse_ont_info, parse_optical_info
    from core.models import OntMetrics

    username, password = _load_olt_credentials(olt_config)
    if not username or not password:
        return None

    try:
        olt = get_olt_connection(
            olt_config["host"], olt_config.get("port", 23), username, password, 15
        )
        olt.connect()

        if input_data["type"] == "serial":
            loc = olt.find_ont_by_sn(input_data["value"])
        elif input_data["type"] == "description":
            loc = olt.find_ont_by_description(input_data["value"])
        else:
            loc = {
                "frame": input_data["frame"],
                "slot": input_data["slot"],
                "port": input_data["port"],
                "ont_id": input_data["ont_id"],
            }

        if not loc:
            return None

        input_data.update(loc)

        # Quick collect basic info
        raw_data = olt.collect_ont(
            input_data["frame"], input_data["slot"], input_data["port"], input_data["ont_id"],
            lambda *a, **k: None
        )

        metrics = OntMetrics()
        metrics.address = f"{input_data['frame']}/{input_data['slot']}/{input_data['port']}/{input_data['ont_id']}"

        if "ont_info" in raw_data:
            parse_ont_info(raw_data["ont_info"], metrics)
        if "optical_info" in raw_data:
            parse_optical_info(raw_data["optical_info"], metrics)

        return SearchResultItem(
            ont_address=metrics.address,
            olt_host=olt_config["host"],
            olt_name=olt_config.get("name", olt_config["host"]),
            serial=metrics.serial,
            description=metrics.description,
            is_online=metrics.is_online,
            model=metrics.model,
            ont_rx_power=metrics.ont_rx_power if metrics.ont_rx_power < 900 else None,
            olt_rx_power=metrics.olt_rx_power if metrics.olt_rx_power < 900 else None,
            distance_m=metrics.distance_m if metrics.distance_m >= 0 else None,
        )
    except Exception as e:
        logger.debug(f"Search failed on {olt_config['host']}: {e}")
        return None


async def search_across_olts(input_data: dict, config: dict, olt_host: str | None) -> list[SearchResultItem]:
    """Search ONT across one or all OLTs in parallel."""
    from diagnose import parse_input

    if olt_host:
        olts = [o for o in config.get("olts", []) if o.get("host") == olt_host]
    else:
        # Filter OLTs with credentials
        olts = []
        for o in config.get("olts", []):
            from diagnose import _load_olt_credentials
            u, p = _load_olt_credentials(o)
            if u and p:
                olts.append(o)

    if not olts:
        return []

    # Parse query once
    parsed_input = parse_input(input_data["query"])
    input_data = parsed_input

    # Parallel search
    results = []
    with ThreadPoolExecutor(max_workers=min(8, len(olts))) as executor:
        future_to_olt = {executor.submit(search_on_single_olt, olt, input_data): olt for olt in olts}
        for future in as_completed(future_to_olt):
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception:
                pass

    return results


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────
from web.api.deps import get_config
from web.api.schemas import SearchRequest, SearchResponse

router = APIRouter()


@router.post("/search", response_model=SearchResponse, summary="Search ONT across OLT(s)")
async def search_ont(
    req: SearchRequest,
    config=Depends(get_config),
):
    """Search for ONT by serial, address, or description."""
    input_data = {"query": req.query, "olt_host": req.olt_host}
    results = await search_across_olts(input_data, config, req.olt_host)
    return SearchResponse(results=results, total=len(results))