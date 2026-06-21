"""Collector — backward-compatible alias for OltConnection.

All telnet logic lives in core/olt.py. This module re-exports TelnetCollector
as an alias to maintain compatibility with securecrt_adapter.py.
"""

from core.olt import OltConnection as TelnetCollector, get_olt_connection, close_all

__all__ = ["TelnetCollector", "get_olt_connection", "close_all"]