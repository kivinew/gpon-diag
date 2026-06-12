"""SecureCRT adapter — allows using the new diagnostic core from SecureCRT.

Usage in SecureCRT:
    1. Copy ONT address / serial / description to clipboard
    2. Run this script
    3. Result is copied to clipboard and shown in message box
"""

import os
import sys

# Add script directory to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import pyperclip
import yaml

from core.models import OntMetrics, DiagnosisReport
from core.parser import (
    parse_ont_info, parse_ont_version, parse_optical_info,
    parse_line_quality, parse_lan_ports, parse_mac_addresses, parse_ipconfig,
)
from core.engine import create_default_engine
from core.thresholds import Thresholds
from core.reporter import format_text


def inject_crt(crt_obj):
    """Store CRT object for screen I/O (compatibility with old scripts)."""
    import core.collector as _c
    # Not needed for new architecture, but kept for compat
    pass


def run_from_securecrt(crt):
    """Main entry point called from SecureCRT."""

    # Load config
    config_path = os.path.join(SCRIPT_DIR, "config.yaml")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        crt.Dialog.MessageBox("config.yaml not found in script directory")
        return

    # Get input from clipboard
    buffer_text = pyperclip.paste().strip()
    if not buffer_text:
        crt.Dialog.MessageBox("Буфер обмена пуст. Скопируйте F/S/P/ONT, SN или лицевой счёт.")
        return

    # Parse input
    import re
    input_data = None

    # Serial number
    if re.fullmatch(r"(?i)(48575443|hwtc)[\da-f]{8}", buffer_text):
        input_data = {"type": "serial", "value": buffer_text.upper()}
    # F/S/P/ONT
    else:
        tokens = buffer_text.replace("/", " ").split()
        if len(tokens) == 4 and all(t.isdigit() for t in tokens):
            input_data = {
                "type": "address",
                "frame": tokens[0], "slot": tokens[1],
                "port": tokens[2], "ont_id": tokens[3],
            }
        elif re.match(r"^(fl_|kes)?\d{5,16}$", buffer_text):
            input_data = {"type": "description", "value": buffer_text}

    if not input_data:
        crt.Dialog.MessageBox(
            f"Не удалось распознать: '{buffer_text}'\n"
            "Ожидается: F/S/P/ONT, серийный номер или лицевой счёт"
        )
        return

    # Select OLT (first one for now)
    olt_config = config.get("olts", [{}])[0]

    # Build thresholds
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
        distance_warn=t.get("distance_warn_m", 5000),
        distance_crit=t.get("distance_crit_m", 10000),
        bad_versions=t.get("bad_versions", []),
        no_ping_models=t.get("no_ping_models", []),
    )

    # Collect data using SecureCRT's existing connection
    from core.collector import TelnetCollector

    host = olt_config.get("host", "")
    port = olt_config.get("port", 23)
    username = olt_config.get("username", "")
    password = olt_config.get("password", "")

    try:
        with TelnetCollector(host, port, username, password) as coll:
            # Resolve ONT location
            if input_data["type"] == "serial":
                loc = coll.find_ont_by_sn(input_data["value"])
                if not loc:
                    crt.Dialog.MessageBox(f"ONT с SN {input_data['value']} не найдена")
                    return
                input_data.update(loc)
            elif input_data["type"] == "description":
                loc = coll.find_ont_by_description(input_data["value"])
                if not loc:
                    crt.Dialog.MessageBox(f"ONT с описанием '{input_data['value']}' не найдена")
                    return
                input_data.update(loc)

            frame = input_data["frame"]
            slot = input_data["slot"]
            port_num = input_data["port"]
            ont_id = input_data["ont_id"]

            # Collect
            raw_data = coll.collect_ont(frame, slot, port_num, ont_id)
    except Exception as e:
        crt.Dialog.MessageBox(f"Ошибка подключения к OLT:\n{e}")
        return

    # Parse
    metrics = OntMetrics()
    metrics.address = f"{input_data['frame']}/{input_data['slot']}/{input_data['port']}/{input_data['ont_id']}"
    metrics.frame = input_data["frame"]
    metrics.slot = input_data["slot"]
    metrics.port = input_data["port"]
    metrics.ont_id = input_data["ont_id"]

    if "ont_info" in raw_data:
        parse_ont_info(raw_data["ont_info"], metrics)
    if "ont_version" in raw_data:
        parse_ont_version(raw_data["ont_version"], metrics)
    if "optical_info" in raw_data:
        parse_optical_info(raw_data["optical_info"], metrics)
    if "line_quality" in raw_data:
        parse_line_quality(raw_data["line_quality"], metrics)
    if "lan_ports" in raw_data:
        parse_lan_ports(raw_data["lan_ports"], metrics)
    if "mac_addresses" in raw_data:
        parse_mac_addresses(raw_data["mac_addresses"], metrics)
    if "ipconfig" in raw_data:
        parse_ipconfig(raw_data["ipconfig"], metrics)

    # Diagnose
    engine = create_default_engine(thresholds)
    problems = engine.diagnose(metrics)

    report = DiagnosisReport(
        timestamp=__import__("datetime").datetime.now().isoformat(),
        olt_name=olt_config.get("name", host),
        metrics=metrics,
        problems=problems,
        is_offline=not metrics.is_online,
    )

    # Output
    text = format_text(report)
    pyperclip.copy(text)
    crt.Dialog.MessageBox(text, "GPON Диагностика")
