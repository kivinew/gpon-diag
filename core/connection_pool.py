"""Connection pool management for OLT connections."""

import logging
import threading
import time
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

_olt_registry: Dict[str, List['OltConnection']] = {}  # List of connections per OLT (pool of 2)
_MAX_CONNECTIONS_PER_OLT = 2
_pool_lock = threading.Lock()  # Lock for thread-safe pool access
_MAX_IDLE_SECONDS = 120  # Max idle time before cleanup


def _cleanup_idle_connections():
    """Remove idle/stale connections from the pool. Must be called with _pool_lock held."""
    now = time.time()
    keys_to_remove = []
    for key, pool in _olt_registry.items():
        # Filter out disconnected or stale connections
        active = []
        for conn in pool:
            if conn._connected and conn._sock is not None:
                # Check idle timeout
                if conn._last_used > 0 and (now - conn._last_used) <= conn._max_idle_seconds:
                    active.append(conn)
                else:
                    logger.debug(f"Cleaning up idle connection to {key}")
                    conn.disconnect()
            else:
                logger.debug(f"Cleaning up disconnected connection to {key}")
                conn.disconnect()
        if active:
            _olt_registry[key] = active
        else:
            keys_to_remove.append(key)
    for key in keys_to_remove:
        _olt_registry.pop(key, None)


def get_olt_connection(host: str, port: int = 23,
                       username: str = "", password: str = "",
                       timeout: int = 15,
                       pool_index: Optional[int] = None) -> 'OltConnection':
    """Get or create connection from pool (max 2 per OLT)."""
    key = f"{host}:{port}"

    with _pool_lock:
        _cleanup_idle_connections()
        
        if key not in _olt_registry:
            _olt_registry[key] = []

        pool = _olt_registry[key]

        if pool_index is not None:
            while len(pool) <= pool_index:
                pool.append(OltConnection(host, port, username, password, timeout))
            return pool[pool_index]

        # Find available connection
        for conn in pool:
            if conn._connected and conn._sock is not None:
                return conn

        # Create new connection if pool not full
        if len(pool) < _MAX_CONNECTIONS_PER_OLT:
            conn = OltConnection(host, port, username, password, timeout)
            pool.append(conn)
            return conn

        # Pool full - return first connection
        return pool[0]


def close_all():
    """Close all OLT connections in the pool."""
    with _pool_lock:
        for pool in _olt_registry.values():
            for conn in pool:
                conn.disconnect()
        _olt_registry.clear()


def get_pool_stats() -> dict:
    """Get connection pool statistics for monitoring."""
    with _pool_lock:
        stats = {}
        for key, pool in _olt_registry.items():
            stats[key] = {
                "total": len(pool),
                "connected": sum(1 for c in pool if c._connected and c._sock is not None),
                "idle": sum(1 for c in pool if c._connected and c._last_used > 0 and (time.time() - c._last_used) > c._max_idle_seconds),
            }
        return stats