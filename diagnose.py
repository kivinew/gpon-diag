#!/usr/bin/env python3
"""GPON Diagnostic Tool — main entry point.

Usage:
    uv run diagnose.py 0/1/3/9
    uv run diagnose.py 4857544312E0E379 --olt "OLT-17.232"
    uv run diagnose.py fl_12345 --clipboard
    uv run diagnose.py 0/1/3/9 --json --no-save
    uv run diagnose.py 0/1/3/9 --no-actions
    uv run diagnose.py 0/1/3/9 --only-optics
"""

import argparse
import json
import logging
from orchestrator import AgentRegistry, register_builtin_agents
import os
import re
import sys
import time
import yaml
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
# Load .env file for credentials – required for OLT connection
try:
    from dotenv import load_dotenv
    load_dotenv(".env")
except ImportError:
    # Fallback: read .env manually if dotenv not available
    env_path = ".env"
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())
except Exception:
    pass

TZ_LOCAL = timezone(timedelta(hours=7))

from core.models import OntMetrics, LanPort
from core.parser import (
    parse_ont_info, parse_ont_version, parse_optical_info,
    parse_line_quality, parse_lan_ports, parse_mac_addresses, parse_ipconfig,
    parse_wan_info, parse_eth_errors, parse_register_info, parse_ping_result,
)
from core.engine import create_extended_engine
from core.thresholds import Thresholds
from core.report import DiagnosisReport
from core.reporter import save_text_report
from core.olt import get_olt_connection, close_all, OntNotFoundError, OltConnection

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Initialize default AI agents for orchestration
_registry = AgentRegistry()
register_builtin_agents(_registry)

MAC_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "oui.txt")

_search_lock = threading.Lock()
_search_result = {"found": False, "olt_config": None, "input_data": None}

BAD_VERSIONS = {
    "V1R003C00S108",
    "V1R006C00S130",
    "V1R006C00S205",
    "V1R006C00S201",
    "V1R006C01S201",
}


def load_config(path="config.yaml"):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file '{path}' not found")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_mac_database():
    mac_db = {}
    if not os.path.exists(MAC_DB_PATH):
        return mac_db
    pattern = re.compile(
        r"^([0-9A-Fa-f]{2}[-]?[0-9A-Fa-f]{2}[-]?[0-9A-Fa-f]{2})\s+\(hex\)\s+(.+)|"
        r"^([0-9A-Fa-f]{6})\s+\(base 16\)\s+(.+)"
    )
    with open(MAC_DB_PATH, "r", encoding="utf-8") as f:
        for line in f:
            m = pattern.match(line.strip())
            if not m:
                continue
            oui = (m.group(1) or m.group(3)).replace("-", "").upper()
            vendor = (m.group(2) or m.group(4)).strip()
            mac_db[oui] = vendor.split()[0]
    return mac_db


def get_vendor(mac, mac_db):
    clean = re.sub(r"[^A-Fa-f0-9]", "", mac).upper()
    return mac_db.get(clean[:6], "n/a")


def sanitize_ont_param(value: str) -> str:
    if not re.fullmatch(r'\d+', value):
        raise ValueError(f"Invalid ONT parameter '{value}': must contain only digits")
    return value


def parse_input(buffer):
    buffer = buffer.strip()
    if not buffer:
        raise ValueError("Empty input")
    if re.fullmatch(r"(?i)(48575443|hwtc)[\da-f]{8}", buffer):
        return {"type": "serial", "value": buffer.upper()}
    tokens = buffer.replace("/", " ").split()
    if len(tokens) == 4 and all(t.isdigit() for t in tokens):
        return {"type": "address", "frame": tokens[0], "slot": tokens[1], "port": tokens[2], "ont_id": tokens[3]}
    # Description: добавляем префикс fl_ если это цифры 5-16 символов
    if re.fullmatch(r"^(fl_|kes)?\d{5,16}$", buffer) or (buffer.isdigit() and 5 <= len(buffer) <= 16):
        value = buffer
        if buffer.isdigit():
            value = f"fl_{buffer}"
        return {"type": "description", "value": value}
    return {"type": "description", "value": buffer}


def _olt_secret_key(olt_name: str) -> str:
    """Convert OLT name to env var key. OLT-17.232 -> 17_232 (strip OLT prefix)."""
    clean = ''.join(ch if ch.isalnum() else '_' for ch in olt_name).replace('__', '_').strip('_')
    # Strip leading OLT_ prefix if present
    if clean.upper().startswith("OLT_"):
        clean = clean[4:]
    return clean


def _load_olt_credentials(olt_config: dict):
    explicit_key = olt_config.get('credential_key', '')
    if explicit_key:
        username = os.getenv(f'GPON_OLT_{explicit_key}_USERNAME', '')
        password = os.getenv(f'GPON_OLT_{explicit_key}_PASSWORD', '')
        if username and password:
            return username, password

    olt_name = olt_config.get('name', '')
    key = _olt_secret_key(olt_name) if olt_name else ''
    if key:
        username = os.getenv(f'GPON_OLT_{key}_USERNAME', '')
        password = os.getenv(f'GPON_OLT_{key}_PASSWORD', '')
        if username and password:
            return username, password

    host = olt_config.get('host', '')
    host_key = ''.join(ch if ch.isalnum() else '_' for ch in host).replace('__', '_').strip('_')
    username = os.getenv(f'GPON_OLT_{host_key}_USERNAME', '')
    password = os.getenv(f'GPON_OLT_{host_key}_PASSWORD', '')
    return username, password


def run_diagnosis(input_data, olt_config, thresholds, allow_actions=True, log=None, ping_target="1.1.1.1", on_olt_info=None):
    _log = log or (lambda msg, end=" ", flush=True: print(msg, end=end, flush=flush))
    host = olt_config["host"]
    port = olt_config.get("port", 23)
    username, password = _load_olt_credentials(olt_config)
    if not username or not password:
        raise ValueError(
            f"Missing OLT credentials for '{olt_config.get('name', host)}'. "
            f"Set env GPON_OLT_<OLT_NAME>_USERNAME/PASSWORD or use .env file."
        )

    olt = get_olt_connection(host, port, username, password, 30)
    _log(f"Подключение к головной станции {host}...")
    olt.connect()
    # Wait for connection to stabilize after login - OLT may need time to accept commands
    time.sleep(1)
    if not olt._connected:
        raise ConnectionError(f"Failed to establish connection to {host}")
    _log("OK")

    _log("Получение информации о головной станции...")
    olt_info = olt.get_olt_info()
    _log(f"OK ({olt_info['model']})")
    if on_olt_info:
        on_olt_info(olt_info)

    olt_uptime = olt_info.get("uptime", "")

    if input_data["type"] == "serial":
        _log(f"Поиск ONT по SN {input_data['value']}...")
        loc = olt.find_ont_by_sn(input_data["value"])
        if not loc:
            _log("не найдена, пробуем поиск по описанию...")
            # fallback to description lookup using the same value (may be description or SN)
            loc = olt.find_ont_by_description(input_data["value"])
            if not loc:
                _log("по описанию тоже не найдено")
                return DiagnosisReport(datetime.now(TZ_LOCAL).isoformat(), host, OntMetrics(), [], True)
        _log("OK")
        input_data.update(loc)
    elif input_data["type"] == "description":
        _log(f"Поиск ONT по описанию '{input_data['value']}'...")
        loc = olt.find_ont_by_description(input_data["value"])
        if not loc:
            _log("не найдена")
            return DiagnosisReport(datetime.now(TZ_LOCAL).isoformat(), host, OntMetrics(), [], True)
        _log("OK")
        input_data.update(loc)

    addr = f"{input_data['frame']}/{input_data['slot']}/{input_data['port']}/{input_data['ont_id']}"
    _log(f"Сбор данных ONT {addr}:")
    raw_data = olt.collect_ont(
        sanitize_ont_param(input_data["frame"]),
        sanitize_ont_param(input_data["slot"]),
        sanitize_ont_param(input_data["port"]),
        sanitize_ont_param(input_data["ont_id"]),
        log=_log,
    )

    metrics = OntMetrics()
    metrics.address = f"{input_data['frame']}/{input_data['slot']}/{input_data['port']}/{input_data['ont_id']}"
    metrics.frame = input_data["frame"]
    metrics.slot = input_data["slot"]
    metrics.port = input_data["port"]
    metrics.ont_id = input_data["ont_id"]
    metrics.olt_uptime = olt_uptime
    metrics.olt_version = olt_info.get('version', '')

    if "ont_info" in raw_data: parse_ont_info(raw_data["ont_info"], metrics)
    if "ont_version" in raw_data: parse_ont_version(raw_data["ont_version"], metrics)
    if "optical_info" in raw_data: parse_optical_info(raw_data["optical_info"], metrics)
    if "line_quality" in raw_data: parse_line_quality(raw_data["line_quality"], metrics)
    if "lan_ports" in raw_data: parse_lan_ports(raw_data["lan_ports"], metrics)
    if "mac_addresses" in raw_data: parse_mac_addresses(raw_data["mac_addresses"], metrics)
    if "ipconfig" in raw_data: parse_ipconfig(raw_data["ipconfig"], metrics)
    if "wan_info" in raw_data: parse_wan_info(raw_data["wan_info"], metrics)

    for lan_id in ["1", "2", "3", "4"]:
        key = f"eth_errors_raw_{lan_id}"
        if key in raw_data:
            parse_eth_errors(raw_data[key], metrics, lan_id)

    if "register_info" in raw_data:
        parse_register_info(raw_data["register_info"], metrics)

    metrics.fetch_timestamp = datetime.now(TZ_LOCAL).isoformat()

    _log("Анализ...")
    engine = create_extended_engine(thresholds)
    problems = engine.diagnose(metrics)
    _log("OK")

    if allow_actions and metrics.is_online:
        if metrics.total_bip_errors > 0:
            _log("Сброс ошибок BIP...")
            olt.clear_line_quality(
                input_data["frame"], input_data["slot"],
                input_data["port"], input_data["ont_id"]
            )
            _log("OK")
        for port_obj in metrics.lan_ports:
            if port_obj.lan_id and port_obj.link_state == "up":
                _log(f"Сброс LAN{port_obj.lan_id}...")
                olt.reset_lan_port(
                    input_data["frame"], input_data["slot"],
                    input_data["port"], input_data["ont_id"],
                    int(port_obj.lan_id)
                )
                olt.clear_eth_errors(
                    input_data["frame"], input_data["slot"],
                    input_data["port"], input_data["ont_id"],
                    int(port_obj.lan_id)
                )
                _log("OK")

    if metrics.is_online and "310" not in metrics.model:
            _log(f"Remote ping ({ping_target})...")
            metrics.ping_target = ping_target
            remote_ping_result = olt.remote_ping(
                input_data["frame"], input_data["slot"],
                input_data["port"], input_data["ont_id"],
                ip=ping_target
            )
            parse_ping_result(remote_ping_result, metrics)
            pr = metrics.ping_result
            if pr.get("transmit", 0) > 0 and pr.get("receive", 0) > 0:
                metrics.ping_status = "успешно"
            elif "Failure" in remote_ping_result:
                metrics.ping_status = "неудачно"
            elif pr.get("transmit", 0) > 0 and pr.get("lost", 0) > 0:
                metrics.ping_status = "неудачно"
            elif pr.get("transmit", 0) > 0:
                metrics.ping_status = "нет ответа"
            else:
                metrics.ping_status = "нет ответа"
            _log(metrics.ping_status)

    return DiagnosisReport(
        datetime.now(TZ_LOCAL).isoformat(), host,
        metrics, problems, not metrics.is_online,
    )


def find_available_olt(config):
    for olt_config in config.get("olts", []):
        host = olt_config["host"]
        username, password = _load_olt_credentials(olt_config)
        if not username or not password:
            continue
        # Check reachability via ping (Windows: check for "TTL=" in output for success)
        try:
            import subprocess
            result = subprocess.run(
                ["ping", "-n", "1", "-w", "2000", host],
                capture_output=True, timeout=5, text=True
            )
            # On Windows: TTL= indicates successful response
            if "TTL=" not in result.stdout:
                continue
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            continue
        # Also check if OLT already has blocked connections in pool
        key = f"{host}:23"
        if key in _olt_registry:
            pool = _olt_registry[key]
            all_blocked = all(conn._skip_disconnect for conn in pool) if pool else False
            if all_blocked:
                continue  # Skip this OLT, it's blocked
        return olt_config
    return None


def search_ont_on_olt(olt_config, input_data):
    """Search for ONT on a single OLT. Returns (olt_config, input_data_with_location) or None."""
    host = olt_config["host"]
    username, password = _load_olt_credentials(olt_config)
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


def find_olt_parallel(config, input_data, max_workers=8):
    """Parallel search across all OLTs. Returns (olt_config, input_data_with_location) or raises OntNotFoundError."""
    global _search_result
    _search_result = {"found": False, "olt_config": None, "input_data": None}
    
    # Filter OLTs with credentials
    olts_with_creds = []
    for olt_config in config.get("olts", []):
        username, password = _load_olt_credentials(olt_config)
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


def main():
    parser = argparse.ArgumentParser(description="GPON ONT Diagnostic Tool")
    parser.add_argument("input", nargs="?", default=None,
                        help="ONT address (F/S/P/ONT), serial, or description")
    parser.add_argument("--olt", help="OLT name or IP from config (default: auto-detect)")
    parser.add_argument("--auto-search", action="store_true",
                        help="Search across all OLTs in parallel (default: single OLT)")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    parser.add_argument("--no-save", action="store_true", help="Don't save report to file")
    parser.add_argument("--no-actions", action="store_true",
                        help="Full diagnostics without port resets and counter clears")
    parser.add_argument("--only-optics", action="store_true",
                        help="Only check optics (powers + BIP errors)")
    args = parser.parse_args()

    if args.input is None:
        try:
            args.input = input("ONT (адрес F/S/P/ONT, серийный номер или описание): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        input_data = parse_input(args.input)
    except ValueError as e:
        print(f"Error: Invalid input format - {e}", file=sys.stderr)
        sys.exit(1)

    olt_config = None
    if args.auto_search:
        # Parallel search across all OLTs
        try:
            olt_config, input_data = find_olt_parallel(config, input_data)
        except OntNotFoundError as e:
            print(f"Ошибка: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.olt:
        for olt in config.get("olts", []):
            if olt.get("name") == args.olt or olt.get("host") == args.olt:
                olt_config = olt
                break
        if not olt_config:
            print(f"Error: OLT '{args.olt}' not found in config.", file=sys.stderr)
            sys.exit(1)
    else:
        olt_config = find_available_olt(config)
        if not olt_config:
            print("Error: No OLT available. Set --olt or check .env credentials.", file=sys.stderr)
            sys.exit(1)
        print(f"Using OLT: {olt_config.get('name', olt_config['host'])}")

    t = config.get("thresholds", {})
    thresholds = Thresholds(
        ont_rx_power_warn=t.get("ont_rx_power_warn_dbm", -26.0),
        ont_rx_power_crit=t.get("ont_rx_power_crit_dbm", -30.0),
        olt_rx_power_warn=t.get("olt_rx_power_warn_dbm", -32.0),
        olt_rx_power_crit=t.get("olt_rx_power_crit_dbm", -35.0),
        bip_error_warn=t.get("bip_error_warn", 10000),
        bip_error_crit=t.get("bip_error_crit", 100000),
        cpu_usage_warn=t.get("cpu_usage_warn_pct", 80),
        memory_usage_warn=t.get("memory_usage_warn_pct", 85),
        cpu_temp_warn=t.get("cpu_temp_warn_c", 75),
        cpu_temp_crit=t.get("cpu_temp_crit_c", 85),
        distance_warn=t.get("distance_warn_m", 20000),
        distance_crit=t.get("distance_crit_m", 21000),
        bad_versions=t.get("bad_versions", []),
        no_ping_models=t.get("no_ping_models", []),
    )

    try:
        report = run_diagnosis(input_data, olt_config, thresholds,
                               allow_actions=not args.no_actions,
                               ping_target=config.get("ping_target", "1.1.1.1"))
    except OntNotFoundError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.exception("Diagnosis failed")
        print(f"Error: Diagnosis failed - {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        close_all()

    if args.json:
        output = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
    else:
        output = report.to_text()

    print(output)

    try:
        import pyperclip
        pyperclip.copy(output)
        print("\n[Copied to clipboard]")
    except Exception:
        pass

    if not args.no_save:
        try:
            filepath = save_text_report(report, config.get("report", {}).get("reports_dir", "data/reports"))
            print(f"[Report saved: {filepath}]")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")


if __name__ == "__main__":
    main()
