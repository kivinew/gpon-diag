"""
OLT routes — list and status of configured OLTs.
"""
import anyio
import logging
from fastapi import APIRouter, Depends, HTTPException

from web.api.deps import get_config
from web.api.schemas import OLTsResponse, OLTInfo
from web.api.exceptions import OLTConnectionError
from core.olt import get_olt_connection
from core.utils import load_olt_credentials as _load_olt_credentials

logger = logging.getLogger(__name__)

router = APIRouter()


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────
@router.get("/olts", response_model=OLTsResponse, summary="List all configured OLTs")
async def list_olts(config=Depends(get_config)):
    """Get all OLTs from config with basic info."""
    olts_config = config.get("olts", [])
    olts = []

    for o in olts_config:
        olts.append(OLTInfo(
            name=o.get("name", o["host"]),
            host=o["host"],
            port=o.get("port", 23),
            credential_key=o.get("credential_key", "RADIUS"),
            reachable=False,  # Will be checked if requested
        ))

    return OLTsResponse(olts=olts, total=len(olts))


@router.get("/olts/{host}/status", response_model=OLTInfo, summary="Check OLT reachability and get info")
async def get_olt_status(host: str, config=Depends(get_config)):
    """Check if OLT is reachable and get model/version/uptime."""
    olt_config = next((o for o in config.get("olts", []) if o.get("host") == host), None)
    if not olt_config:
        raise HTTPException(404, f"OLT {host} not found in config")

    from core.utils import load_olt_credentials as _load_olt_credentials

    username, password = _load_olt_credentials(olt_config)
    if not username or not password:
        return OLTInfo(
            name=olt_config.get("name", host),
            host=host,
            port=olt_config.get("port", 23),
            credential_key=olt_config.get("credential_key", "RADIUS"),
            reachable=False,
        )

    try:
        olt = get_olt_connection(host, olt_config.get("port", 23), username, password, 10)
        await anyio.to_thread.run_sync(olt.connect)
        info = await anyio.to_thread.run_sync(olt.get_olt_info)

        return OLTInfo(
            name=olt_config.get("name", host),
            host=host,
            port=olt_config.get("port", 23),
            credential_key=olt_config.get("credential_key", "RADIUS"),
            reachable=True,
            model=info.get("model"),
            version=info.get("version"),
            uptime=info.get("uptime"),
        )
    except Exception as e:
        logger.warning(f"OLT status check failed for {host}: {e}")
        return OLTInfo(
            name=olt_config.get("name", host),
            host=host,
            port=olt_config.get("port", 23),
            credential_key=olt_config.get("credential_key", "RADIUS"),
            reachable=False,
        )