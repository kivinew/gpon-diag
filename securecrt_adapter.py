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
from core.constants import DEFAULT_THRESHOLDS
from core.utils import parse_input, sanitize_ont_param, load_olt_credentials


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

    # Parse input using shared utility
    try:
        input_data = parse_input(buffer_text)
    except ValueError as e:
        crt.Dialog.MessageBox(
            f"Не удалось распознать: '{buffer_text}'\n"
            f"Ошибка: {e}\n"
            "Ожидается: F/S/P/ONT, серийный номер или лицевой счёт"
        )
        return

    # Select OLT (first one for now)
    olt_config = config.get("olts", [{}])[0]

    # Build thresholds from config with defaults from core.constants
    t = config.get("thresholds", {})
    thresholds = Thresholds(
        ont_rx_power_warn=t.get("ont_rx_power_warn_dbm", DEFAULT_THRESHOLDS["ont_rx_power_warn"]),
        ont_rx_power_crit=t.get("ont_rx_power_crit_dbm", DEFAULT_THRESHOLDS["ont_rx_power_crit"]),
        olt_rx_power_warn=t.get("olt_rx_power_warn_dbm", DEFAULT_THRESHOLDS["olt_rx_power_warn"]),
        olt_rx_power_crit=t.get("olt_rx_power_crit_dbm", DEFAULT_THRESHOLDS["olt_rx_power_crit"]),
        bip_error_warn=t.get("bip_error_warn", DEFAULT_THRESHOLDS["bip_error_warn"]),
        bip_error_crit=t.get("bip_error_crit", DEFAULT_THRESHOLDS["bip_error_crit"]),
        cpu_temp_warn=t.get("cpu_temp_warn_c", DEFAULT_THRESHOLDS["cpu_temp_warn"]),
        cpu_temp_crit=t.get("cpu_temp_crit_c", DEFAULT_THRESHOLDS["cpu_temp_crit"]),
        cpu_usage_warn=t.get("cpu_usage_warn_pct", DEFAULT_THRESHOLDS["cpu_usage_warn"]),
        memory_usage_warn=t.get("memory_usage_warn_pct", DEFAULT_THRESHOLDS["memory_usage_warn"]),
        distance_warn=t.get("distance_warn_m", DEFAULT_THRESHOLDS["distance_warn"]),
        distance_crit=t.get("distance_crit_m", DEFAULT_THRESHOLDS["distance_crit"]),
        bad_versions=t.get("bad_versions", DEFAULT_THRESHOLDS["bad_versions"]),
        no_ping_models=t.get("no_ping_models", DEFAULT_THRESHOLDS["no_ping_models"]),
    )

    # Collect data using SecureCRT's existing connection
    from core.collector import TelnetCollector

    host = olt_config.get("host", "")
    port = olt_config.get("port", 23)
    username, password = load_olt_credentials(olt_config)
    if not username or not password:
        crt.Dialog.MessageBox(
            f"Нет креденшелий для OLT '{olt_config.get('name', host)}'.\n"
            f"Установите env: GPON_OLT_<OLT_NAME>_USERNAME/PASSWORD"
        )
        return

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

            # Collect with sanitized parameters
            raw_data = coll.collect_ont(
                sanitize_ont_param(frame),
                sanitize_ont_param(slot),
                sanitize_ont_param(port_num),
                sanitize_ont_param(ont_id),
            )
    except ValueError as e:
        crt.Dialog.MessageBox(f"Ошибка валидации параметров: {e}")
        return
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