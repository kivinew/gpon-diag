"""Connection pool management for OLT connections."""

import logging
import threading
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

_olt_registry: Dict[str, List['OltConnection']] = {}  # List of connections per OLT (pool of 2)
_MAX_CONNECTIONS_PER_OLT = 2
_pool_lock = threading.Lock()  # Lock for thread-safe pool access


def get_olt_connection(host: str, port: int = 23,
                       username: str = "", password: str = "",
                       timeout: int = 15,
                       pool_index: Optional[int] = None) -> 'OltConnection':
    """Get or create connection from pool (max 2 per OLT)."""
    key = f"{host}:{port}"

    with _pool_lock:
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
    for pool in _olt_registry.values():
        for conn in pool:
            conn.disconnect()
    _olt_registry.clear()