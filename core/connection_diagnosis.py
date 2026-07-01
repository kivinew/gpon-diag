"""OLT connection management and parallel search for ONTs."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from typing import Optional, Tuple, List

from core.olt import OltConnection, OntNotFoundError
from core.utils import load_olt_credentials

logger = logging.getLogger(__name__)

_search_lock = threading.Lock()
_search_result = {"found": False, "olt_config": None, "input_data": None}


def find_available_olt(config: dict) -> Optional[dict]:
    """
    Find first available OLT with valid credentials and reachable host.

    Args:
        config: Configuration dict with 'olts' list

    Returns:
        OLT config dict or None if none available
    """
    for olt_config in config.get("olts", []):
        host = olt_config["host"]
        username, password = load_olt_credentials(olt_config)
        if not username or not password:
            continue

        # Check reachability via ping (Windows: check for "TTL=" in output for success)
        try:
            import subprocess
            result = subprocess.run(
                ["ping", "-n", "1", "-w", "2000", host],
                capture_output=True, timeout=5, text=True
            )
            if "TTL=" not in result.stdout:
                continue
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            continue
        return olt_config
    return None


def search_ont_on_olt(olt_config: dict, input_data: dict) -> Optional[Tuple[dict, dict]]:
    """
    Search for ONT on a single OLT.

    Args:
        olt_config: OLT configuration dict
        input_data: Parsed input data (type + value/location)

    Returns:
        Tuple of (olt_config, input_data_with_location) or None
    """
    host = olt_config["host"]
    username, password = load_olt_credentials(olt_config)
    if not username or not password:
        return None
    try:
        # Create a fresh connection for this thread
        olt = OltConnection(host, 23, username, password, 30)
        olt.connect()
        # Wait for connection to stabilize
        time.sleep(1)
        # Try search based on input type
        if input_data["type"] == "serial":
            loc = olt.find_ont_by_sn(input_data["value"])
        elif input_data["type"] == "description":
            loc = olt.find_ont_by_description(input_data["value"])
        elif input_data["type"] == "address":
            # Already have location
            loc = {
                "frame": input_data["frame"],
                "slot": input_data["slot"],
                "port": input_data["port"],
                "ont_id": input_data["ont_id"]
            }
        else:
            loc = None
        olt.disconnect()
        if loc:
            result = input_data.copy()
            result.update(loc)
            return (olt_config, result)
    except Exception:
        pass
    return None


def find_olt_parallel(config: dict, input_data: dict, max_workers: int = 8) -> Tuple[dict, dict]:
    """
    Parallel search across all OLTs.

    Args:
        config: Configuration with 'olts' list
        input_data: Parsed input data
        max_workers: Maximum parallel workers

    Returns:
        Tuple of (olt_config, input_data_with_location)

    Raises:
        OntNotFoundError: If ONT not found on any OLT
    """
    global _search_result
    _search_result = {"found": False, "olt_config": None, "input_data": None}

    # Filter OLTs with credentials
    olts_with_creds = []
    for olt_config in config.get("olts", []):
        username, password = load_olt_credentials(olt_config)
        if username and password:
            olts_with_creds.append(olt_config)

    if not olts_with_creds:
        raise OntNotFoundError("No OLTs with valid credentials configured")

    print(f"Поиск по {len(olts_with_creds)} OLT параллельно...")

    with ThreadPoolExecutor(max_workers=min(max_workers, len(olts_with_creds))) as executor:
        future_to_olt = {
            executor.submit(search_ont_on_olt, olt_config, input_data): olt_config
            for olt_config in olts_with_creds
        }

        for future in as_completed(future_to_olt):
            result = future.result()
            if result:
                with _search_lock:
                    if not _search_result["found"]:
                        _search_result["found"] = True
                        _search_result["olt_config"] = result[0]
                        _search_result["input_data"] = result[1]
                        print(f"Найдено на {result[0].get('name', result[0]['host'])}")
                # Cancel remaining futures
                for f in future_to_olt:
                    f.cancel()
                return result

    raise OntNotFoundError(f"ONT не найдена на ни одной из {len(olts_with_creds)} OLT")