"""
Health check routes — for systemd/load balancer monitoring.
"""
import time
import logging
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from web.api.deps import get_db, get_db_engine, get_olt_pool, get_config
from web.api.schemas import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Track startup time
_start_time = time.time()


@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health_check(
    db: AsyncSession = Depends(get_db),
    config=Depends(get_config),
    olt_pool=Depends(get_olt_pool),
):
    """Liveness/readiness probe for systemd and load balancers."""
    db_connected = False
    try:
        await db.execute(text("SELECT 1"))
        db_connected = True
    except Exception:
        pass

    # Count active OLT connections
    from core.olt import _olt_registry
    active_connections = 0
    pool_size = 0
    for host, conns in _olt_registry.items():
        pool_size += len(conns)
        for c in conns:
            if c._connected:
                active_connections += 1

    return HealthResponse(
        status="ok" if db_connected else "degraded",
        version="0.2.0",
        uptime_seconds=time.time() - _start_time,
        db_connected=db_connected,
        olt_pool_size=pool_size,
        active_connections=active_connections,
    )


@router.get("/ready", summary="Readiness probe")
async def readiness_check(
    db: AsyncSession = Depends(get_db),
):
    """Kubernetes-style readiness probe."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        return {"status": "not ready"}, 503