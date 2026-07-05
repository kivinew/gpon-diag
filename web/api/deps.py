"""
Dependency Injection providers for FastAPI routes.
Singletons: config, DB engine, OLT pool.
"""
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import AsyncGenerator, Optional

import yaml
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from core.olt import get_olt_connection, close_all as close_olt_pool
from core.thresholds import Thresholds

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
@lru_cache
def get_config() -> dict:
    """Load config.yaml once at startup."""
    import os
    # Try multiple locations for config.yaml
    possible_paths = [
        Path(__file__).parents[3] / "config.yaml",  # Standard location
        Path.cwd() / "config.yaml",  # Current working directory
    ]
    for config_path in possible_paths:
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as f:
                return yaml.safe_load(f)
    raise FileNotFoundError("config.yaml not found in any expected location")


@lru_cache
def get_thresholds() -> Thresholds:
    """Build Thresholds dataclass from config."""
    config = get_config()
    raw = config.get("thresholds", {})
    return Thresholds(
        ont_rx_power_warn=raw.get("ont_rx_power_warn_dbm", -26.5),
        ont_rx_power_crit=raw.get("ont_rx_power_crit_dbm", -30.0),
        olt_rx_power_warn=raw.get("olt_rx_power_warn_dbm", -33.0),
        olt_rx_power_crit=raw.get("olt_rx_power_crit_dbm", -35.0),
        bip_error_warn=raw.get("bip_error_warn", 10000),
        bip_error_crit=raw.get("bip_error_crit", 100000),
        cpu_temp_warn=raw.get("cpu_temp_warn_c", 75),
        cpu_temp_crit=raw.get("cpu_temp_crit_c", 90),
        cpu_usage_warn=raw.get("cpu_usage_warn_pct", 90),
        memory_usage_warn=raw.get("memory_usage_warn_pct", 85),
        ont_temperature_warn=raw.get("ont_temperature_warn_c", 65),
        ont_temperature_crit=raw.get("ont_temperature_crit_c", 75),
        distance_warn=raw.get("distance_warn_m", 19000),
        distance_crit=raw.get("distance_crit_m", 20000),
        bad_versions=raw.get("bad_versions", []),
        no_ping_models=raw.get("no_ping_models", []),
    )


# ──────────────────────────────────────────────
# Database (SQLAlchemy 2.0 async + aiosqlite)
# ──────────────────────────────────────────────
_db_engine: Optional[AsyncEngine] = None
_async_session_maker: Optional[sessionmaker] = None


def get_db_engine() -> AsyncEngine:
    global _db_engine
    if _db_engine is None:
        config = get_config()
        db_path = Path(__file__).parents[3] / "data" / "diagnoses.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # WAL mode for better concurrency
        url = f"sqlite+aiosqlite:///{db_path}?journal_mode=WAL&synchronous=NORMAL"
        _db_engine = create_async_engine(url, echo=False, pool_pre_ping=True)
    return _db_engine


def get_session_maker() -> sessionmaker:
    global _async_session_maker
    if _async_session_maker is None:
        _async_session_maker = sessionmaker(
            get_db_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _async_session_maker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields AsyncSession."""
    async with get_session_maker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ──────────────────────────────────────────────
# OLT Connection Pool (reuses core.olt singleton)
# ──────────────────────────────────────────────
def get_olt_pool():
    """Returns the core.olt connection pool functions."""
    return {
        "get_connection": get_olt_connection,
        "close_all": close_olt_pool,
    }


# ──────────────────────────────────────────────
# Lifespan hooks
# ──────────────────────────────────────────────
async def lifespan_init():
    """Initialize on startup."""
    from sqlalchemy import text
    # Trigger config load
    get_config()
    get_thresholds()
    get_db_engine()
    # Test DB connection
    async with get_session_maker()() as session:
        await session.execute(text("SELECT 1"))


async def lifespan_shutdown():
    """Cleanup on shutdown."""
    global _db_engine, _async_session_maker
    close_olt_pool()
    if _db_engine:
        await _db_engine.dispose()
        _db_engine = None
        _async_session_maker = None