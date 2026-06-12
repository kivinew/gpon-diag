#!/usr/bin/env python3
"""GPON Diagnostic Tool — main entry point."""

import argparse
import json
import logging
import os
import sys
import re
from datetime import datetime

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml
from core.models import OntMetrics, LanPort
from core.parser import (
    parse_wan_info,
    parse_ont_info, parse_ont_version, parse_optical_info,
    parse_line_quality, parse_lan_ports, parse_mac_addresses, parse_ipconfig,
)
from core.engine import create_extended_engine
from core.thresholds import Thresholds
from core.report import DiagnosisReport
from core.reporter import save_text_report
from core.olt import get_olt_connection, close_all


def load_config(path="config.yaml"):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file '{path}' not found")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def sanitize_ont_param(value: str) -> str:
    """Validate ONT parameter contains only digits."""
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
    if re.match(r"^(fl_|kes)?\d{5,16}$", buffer):
        return {"type": "description", "value": buffer}
    raise ValueError(f"Cannot recognize: '{buffer}'")


def _olt_secret_key(olt_name: str) -> str:
    # OLT-17.232 -> 17_232
    return ''.join(ch if ch.isalnum() else '_' for ch in olt_name).replace('__', '_').strip('_')


def _load_olt_credentials(olt_config: dict):
    # Priority: env vars by OLT name
    olt_name = olt_config.get('name', '')
    key = _olt_secret_key(olt_name) if olt_name else ''
    if key:
        username = os.getenv(f"GPON_OLT_{key}_USERNAME", '')
        password = os.getenv(f"GPON_OLT_{key}_PASSWORD", '')
        if username and password:
            return username, password

    # Fallback: try by host
    host = olt_config.get('host', '')
    host_key = ''.join(ch if ch.isalnum() else '_' for ch in host).replace('__', '_').strip('_')
    username = os.getenv(f"GPON_OLT_{host_key}_USERNAME", '')
    password = os.getenv(f"GPON_OLT_{host_key}_PASSWORD", '')
    return username, password


def run_diagnosis(input_data, olt_config, thresholds):
    host = olt_config["host"]
    port = olt_config.get("port", 23)
    username, password = _load_olt_credentials(olt_config)
    if not username or not password:
        logger.error(
            f"Missing OLT credentials for '{olt_config.get('name', host)}'. "
            f"Set env GPON_OLT_<OLT_NAME>_USERNAME/PASSWORD."
        )
        sys.exit(2)

    # Get singleton OLT connection
    olt = get_olt_connection(host, port, username, password)
    olt.connect()

    # Resolve ONT location if needed
    if input_data["type"] == "serial":
        loc = olt.find_ont_by_sn(input_data["value"])
        if not loc:
            return DiagnosisReport(datetime.now().isoformat(), olt_config.get("name", host), OntMetrics(), [], True)
        input_data.update(loc)
    elif input_data["type"] == "description":
        loc = olt.find_ont_by_description(input_data["value"])
        if not loc:
            return DiagnosisReport(datetime.now().isoformat(), olt_config.get("name", host), OntMetrics(), [], True)
        input_data.update(loc)

    raw_data = olt.collect_ont(
        sanitize_ont_param(input_data["frame"]),
        sanitize_ont_param(input_data["slot"]),
        sanitize_ont_param(input_data["port"]),
        sanitize_ont_param(input_data["ont_id"]),
    )

    # Build metrics
    metrics = OntMetrics()
    metrics.address = f"{input_data['frame']}/{input_data['slot']}/{input_data['port']}/{input_data['ont_id']}"
    metrics.frame = input_data["frame"]
    metrics.slot = input_data["slot"]
    metrics.port = input_data["port"]
    metrics.ont_id = input_data["ont_id"]

    if "ont_info" in raw_data: parse_ont_info(raw_data["ont_info"], metrics)
    if "ont_version" in raw_data: parse_ont_version(raw_data["ont_version"], metrics)
    if "optical_info" in raw_data: parse_optical_info(raw_data["optical_info"], metrics)
    if "line_quality" in raw_data: parse_line_quality(raw_data["line_quality"], metrics)
    if "lan_ports" in raw_data: parse_lan_ports(raw_data["lan_ports"], metrics)
    if "mac_addresses" in raw_data: parse_mac_addresses(raw_data["mac_addresses"], metrics)
    if "ipconfig" in raw_data: parse_ipconfig(raw_data["ipconfig"], metrics)
    if "wan_info" in raw_data: parse_wan_info(raw_data["wan_info"], metrics)

    metrics.fetch_timestamp = datetime.now().isoformat()

    engine = create_extended_engine(thresholds)
    problems = engine.diagnose(metrics)

    return DiagnosisReport(
        datetime.now().isoformat(), olt_config.get("name", host),
        metrics, problems, not metrics.is_online,
    )


def main():
    parser = argparse.ArgumentParser(description="GPON ONT Diagnostic Tool")
    parser.add_argument("input", help="ONT address (F/S/P/ONT), serial, or description")
    parser.add_argument("--olt", help="OLT name from config")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    olt_config = None
    for olt in config.get("olts", []):
        if args.olt and olt.get("name") == args.olt:
            olt_config = olt; break
        if not args.olt:
            olt_config = olt; break
    if not olt_config:
        print("Error: OLT not found. Use --olt to specify OLT name.", file=sys.stderr)
        sys.exit(1)

    try:
        input_data = parse_input(args.input)
    except ValueError as e:
        print(f"Error: Invalid input format - {e}", file=sys.stderr)
        sys.exit(1)

    t = config.get("thresholds", {})
    thresholds = Thresholds(
        ont_rx_power_warn=t.get("ont_rx_power_warn_dbm", -26.0),
        ont_rx_power_crit=t.get("ont_rx_power_crit_dbm", -30.0),
        olt_rx_power_warn=t.get("olt_rx_power_warn_dbm", -32.0),
        olt_rx_power_crit=t.get("olt_rx_power_crit_dbm", -35.0),
        bip_error_warn=t.get("bip_error_warn", 10000),
        bip_error_crit=t.get("bip_error_crit", 100000),
        cpu_temp_warn=t.get("cpu_temp_warn_c", 75),
        cpu_temp_crit=t.get("cpu_temp_crit_c", 85),
        cpu_usage_warn=t.get("cpu_usage_warn_pct", 80),
        memory_usage_warn=t.get("memory_usage_warn_pct", 85),
        distance_warn=t.get("distance_warn_m", 15000),
        distance_crit=t.get("distance_crit_m", 20000),
        bad_versions=t.get("bad_versions", []),
    )

    try:
        report = run_diagnosis(input_data, olt_config, thresholds)
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
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(report.to_text())

    if not args.no_save:
        try:
            filepath = save_text_report(report, config.get("report", {}).get("reports_dir", "data/reports"))
            print(f"\n[Report saved: {filepath}]")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")
            print(f"\n[Warning: Failed to save report: {e}]", file=sys.stderr)


if __name__ == "__main__":
    main()
