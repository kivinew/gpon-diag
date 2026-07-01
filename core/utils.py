"""Shared utilities — consolidated from diagnose.py, core/report.py, securecrt_adapter.py."""

import logging
import os
import re
from pathlib import Path
from typing import Optional, Tuple

from core.constants import (
    CREDENTIAL_ENV_PREFIX,
    MAC_DB_PATH,
    ONLINE_STATUSES,
    DESCRIPTION_DIGITS_PATTERN,
    SERIAL_PATTERN,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# MAC vendor database (lazy-loaded, cached)
# ──────────────────────────────────────────────
_mac_db_cache: Optional[dict] = None


def _load_mac_database_impl() -> dict:
    """Internal implementation: load OUI database from file."""
    mac_db = {}
    if not os.path.exists(MAC_DB_PATH):
        logger.debug(f"MAC database not found at {MAC_DB_PATH}")
        return mac_db

    pattern = re.compile(
        r"^([0-9A-Fa-f]{2}[-]?[0-9A-Fa-f]{2}[-]?[0-9A-Fa-f]{2})\s+\(hex\)\s+(.+)|"
        r"^([0-9A-Fa-f]{6})\s+\(base 16\)\s+(.+)"
    )
    try:
        with open(MAC_DB_PATH, "r", encoding="utf-8") as f:
            for line in f:
                m = pattern.match(line.strip())
                if not m:
                    continue
                oui = (m.group(1) or m.group(3)).replace("-", "").upper()
                vendor = (m.group(2) or m.group(4)).strip()
                mac_db[oui] = vendor.split()[0]
    except OSError as e:
        logger.warning(f"Failed to load MAC database: {e}")
    return mac_db


def get_mac_database() -> dict:
    """Get MAC vendor database (cached, lazy-loaded)."""
    global _mac_db_cache
    if _mac_db_cache is None:
        _mac_db_cache = _load_mac_database_impl()
    return _mac_db_cache


def clear_mac_database_cache() -> None:
    """Clear the MAC database cache (useful for testing)."""
    global _mac_db_cache
    _mac_db_cache = None


def get_vendor(mac: str, mac_db: Optional[dict] = None) -> str:
    """Look up vendor by MAC address OUI."""
    db = mac_db or get_mac_database()
    clean = re.sub(r"[^A-Fa-f0-9]", "", mac).upper()
    return db.get(clean[:6], "n/a")


# ──────────────────────────────────────────────
# OLT credential loading
# ──────────────────────────────────────────────

def _olt_secret_key(olt_name: str) -> str:
    """Convert OLT name to env var key. OLT-17.232 -> 17_232."""
    clean = ''.join(ch if ch.isalnum() else '_' for ch in olt_name).replace('__', '_').strip('_')
    if clean.upper().startswith("OLT_"):
        clean = clean[4:]
    return clean


def load_olt_credentials(olt_config: dict) -> Tuple[str, str]:
    """
    Load OLT username/password from environment variables.

    Resolution order:
    1. credential_key from config -> GPON_OLT_<KEY>_USERNAME/PASSWORD
    2. Sanitized OLT name -> GPON_OLT_<OLT_NAME>_USERNAME/PASSWORD
    3. Sanitized host IP -> GPON_OLT_<HOST>_USERNAME/PASSWORD

    Returns (username, password) tuple. Both may be empty strings if not found.
    """
    # 1. Explicit credential_key
    explicit_key = olt_config.get('credential_key', '')
    if explicit_key:
        username = os.getenv(f'{CREDENTIAL_ENV_PREFIX}{explicit_key}_USERNAME', '')
        password = os.getenv(f'{CREDENTIAL_ENV_PREFIX}{explicit_key}_PASSWORD', '')
        if username and password:
            return username, password

    # 2. Sanitized OLT name
    olt_name = olt_config.get('name', '')
    key = _olt_secret_key(olt_name) if olt_name else ''
    if key:
        username = os.getenv(f'{CREDENTIAL_ENV_PREFIX}{key}_USERNAME', '')
        password = os.getenv(f'{CREDENTIAL_ENV_PREFIX}{key}_PASSWORD', '')
        if username and password:
            return username, password

    # 3. Sanitized host IP
    host = olt_config.get('host', '')
    host_key = ''.join(ch if ch.isalnum() else '_' for ch in host).replace('__', '_').strip('_')
    username = os.getenv(f'{CREDENTIAL_ENV_PREFIX}{host_key}_USERNAME', '')
    password = os.getenv(f'{CREDENTIAL_ENV_PREFIX}{host_key}_PASSWORD', '')
    return username, password


# ──────────────────────────────────────────────
# Input parsing
# ──────────────────────────────────────────────

def parse_input(buffer: str) -> dict:
    """
    Parse user input into structured data.

    Returns dict with:
    - type: "serial" | "address" | "description"
    - value: for serial/description
    - frame, slot, port, ont_id: for address
    """
    buffer = buffer.strip()
    if not buffer:
        raise ValueError("Empty input")

    # Serial number: 48575443xxxxxxxx or Hwtcxxxxxxxx
    if re.fullmatch(SERIAL_PATTERN, buffer):
        return {"type": "serial", "value": buffer.upper()}

    # F/S/P/ONT address: 4 numeric tokens
    tokens = buffer.replace("/", " ").split()
    if len(tokens) == 4 and all(t.isdigit() for t in tokens):
        return {
            "type": "address",
            "frame": tokens[0],
            "slot": tokens[1],
            "port": tokens[2],
            "ont_id": tokens[3]
        }

    # Description: numeric 5-16 digits gets fl_ prefix
    if re.fullmatch(DESCRIPTION_PATTERN, buffer) or re.fullmatch(DESCRIPTION_DIGITS_PATTERN, buffer):
        value = buffer
        if buffer.isdigit():
            value = f"fl_{buffer}"
        return {"type": "description", "value": value}

    # Custom description string
    return {"type": "description", "value": buffer}


def sanitize_ont_param(value: str) -> str:
    """Validate ONT parameter contains only digits."""
    if not re.fullmatch(r'\d+', value):
        raise ValueError(f"Invalid ONT parameter '{value}': must contain only digits")
    return value


# ──────────────────────────────────────────────
# Status helpers
# ──────────────────────────────────────────────

def is_online_status(status: str) -> bool:
    """Check if status indicates online state."""
    return status.lower() in ONLINE_STATUSES


def is_offline_status(status: str) -> bool:
    """Check if status indicates offline state."""
    return status.lower() in {"offline", "initial"}