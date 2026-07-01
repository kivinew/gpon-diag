"""OLT Connection — main interface combining connection pool, telnet session, and data collector."""

import logging
import re
import time
from typing import Dict, Optional

from core.connection_pool import get_olt_connection as _get_olt_connection, close_all as _close_all
from core.telnet_session import TelnetSession
from core.data_collector import OntDataCollector
from core.constants import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_COMMAND_TIMEOUT,
    IDLE_TIMEOUT,
    MAX_CONNECTIONS_PER_OLT,
)

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
OntNotFoundError = OntDataCollector.OntNotFoundError if hasattr(OntDataCollector, 'OntNotFoundError') else Exception

# Keep the same exception class name for backward compat
class OntNotFoundError(Exception):
    pass


class OltConnection:
    """
    Main OLT connection class — combines connection pooling, telnet session,
    and data collection. Maintains backward compatibility with existing code.
    """

    _banner_cache = ""  # Class-level cache for model info

    def __init__(self, host: str = "", port: int = 23,
                 username: str = "", password: str = "",
                 timeout: int = 15):
        # Create internal telnet session
        self._session = TelnetSession(host, port, username, password, timeout)
        # Create data collector using the session
        self._collector = OntDataCollector(self._session)

        # Expose common attributes for backward compatibility
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout

        # Delegated properties
        self._sock = None
        self._connected = False
        self._last_used = 0.0
        self._max_idle_seconds = IDLE_TIMEOUT
        self._skip_disconnect = False
        self._connect_attempts = 0

    # Property delegation to session
    @property
    def _sock(self):
        return self._session._sock

    @_sock.setter
    def _sock(self, value):
        self._session._sock = value

    @property
    def _connected(self):
        return self._session._connected

    @_connected.setter
    def _connected(self, value):
        self._session._connected = value

    @property
    def _last_used(self):
        return self._session._last_used

    @_last_used.setter
    def _last_used(self, value):
        self._session._last_used = value

    @property
    def _max_idle_seconds(self):
        return self._session._max_idle_seconds

    @_max_idle_seconds.setter
    def _max_idle_seconds(self, value):
        self._session._max_idle_seconds = value

    @property
    def _skip_disconnect(self):
        return self._session._skip_disconnect

    @_skip_disconnect.setter
    def _skip_disconnect(self, value):
        self._session._skip_disconnect = value

    @property
    def _connect_attempts(self):
        return self._session._connect_attempts

    @_connect_attempts.setter
    def _connect_attempts(self, value):
        self._session._connect_attempts = value

    @property
    def _banner(self):
        return self._session._banner

    @_banner.setter
    def _banner(self, value):
        self._session._banner = value
        # Also update class-level cache
        OltConnection._banner_cache = value

    # Method delegation
    def _check_idle_timeout(self):
        return self._session._check_idle_timeout()

    def connect(self):
        self._session.connect()
        # Update banner cache
        OltConnection._banner_cache = self._session._banner

    def get_olt_info(self) -> dict:
        """Get OLT model, uptime, and software version."""
        model = uptime = version = ""
        # Model extraction from banner
        try:
            banner = OltConnection._banner_cache
            model_match = re.search(r"\bMA(\d{4})T?\b", banner, re.I)
            if model_match:
                model = f"MA{model_match.group(1)}"
        except Exception:
            logger.debug("Failed to parse model from banner", exc_info=True)
        # Version extraction
        try:
            version_output = self._session.send_command("display version", max_more=0)
            version_match = re.search(r"VERSION\s*[:]\s*([^\s]+)", version_output, re.I)
            if version_match:
                version = version_match.group(1).strip()
        except Exception:
            logger.debug("Failed to retrieve OLT version", exc_info=True)
        # Uptime extraction
        try:
            uptime_output = self._session.send_command("display uptime", max_more=0)
            uptime_match = re.search(r"Uptime\s+is\s+([\w ,()]+)", uptime_output, re.I)
            if uptime_match:
                raw_uptime = uptime_match.group(1).strip()
                days_match = re.search(r"(\d+)\s*day", raw_uptime, re.I)
                uptime = f"{days_match.group(1)} day(s)" if days_match else raw_uptime
        except Exception:
            logger.debug("Failed to retrieve OLT uptime", exc_info=True)
        return {"model": model, "uptime": uptime, "version": version}

    def disconnect(self):
        self._session.disconnect()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    def _write(self, text):
        return self._session._write(text)

    def _read_to_prompt(self, seconds=2):
        return self._session._read_to_prompt(seconds)

    def send_command(self, command, max_more=0):
        return self._session.send_command(command, max_more)

    def _gpon_ctx(self, frame, slot):
        self._session._gpon_ctx(frame, slot)

    def _quit_gpon(self):
        self._session._quit_gpon()

    def _drain_socket(self):
        self._session._drain_socket()

    # Data collection methods delegate to collector
    def collect_ont(self, frame, slot, port, ont_id, log=None):
        return self._collector.collect_ont(frame, slot, port, ont_id, log)

    def collect_port_summary(self, frame, slot, port, log=None):
        return self._collector.collect_port_summary(frame, slot, port, log)

    def clear_line_quality(self, frame, slot, port, ont_id):
        self._collector.clear_line_quality(frame, slot, port, ont_id)

    def reset_lan_port(self, frame, slot, port, ont_id, lan_id):
        self._collector.reset_lan_port(frame, slot, port, ont_id, lan_id)

    def clear_eth_errors(self, frame, slot, port, ont_id, lan_id):
        self._collector.clear_eth_errors(frame, slot, port, ont_id, lan_id)

    def remote_ping(self, frame, slot, port, ont_id, ip="1.1.1.1"):
        return self._collector.remote_ping(frame, slot, port, ont_id, ip)

    def find_ont_by_sn(self, serial):
        return self._collector.find_ont_by_sn(serial)

    def find_ont_by_description(self, description):
        return self._collector.find_ont_by_description(description)

    @staticmethod
    def _parse_fsp(output):
        return OntDataCollector._parse_fsp(output)


# Module-level functions for backward compatibility
def get_olt_connection(host: str, port: int = 23,
                       username: str = "", password: str = "",
                       timeout: int = 15,
                       pool_index: Optional[int] = None) -> OltConnection:
    """Get or create connection from pool (max 2 per OLT)."""
    return _get_olt_connection(host, port, username, password, timeout, pool_index)


def close_all():
    """Close all OLT connections in the pool."""
    _close_all()