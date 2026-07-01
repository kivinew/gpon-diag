"""Core diagnosis logic — business logic for ONT diagnosis."""

import logging
import time
from datetime import datetime
from typing import Optional, Callable

from core.models import OntMetrics, LanPort
from core.parser import (
    parse_ont_info, parse_ont_version, parse_optical_info,
    parse_line_quality, parse_lan_ports, parse_mac_addresses, parse_ipconfig,
    parse_wan_info, parse_eth_errors, parse_register_info, parse_ping_result,
)
from core.engine import create_extended_engine
from core.thresholds import Thresholds
from core.report import DiagnosisReport
from core.olt import get_olt_connection, close_all, OntNotFoundError, OltConnection
from core.constants import TZ_LOCAL, DEFAULT_PING_TARGET
from core.utils import sanitize_ont_param, load_olt_credentials

logger = logging.getLogger(__name__)


def run_diagnosis(
    input_data: dict,
    olt_config: dict,
    thresholds: Thresholds,
    allow_actions: bool = True,
    log: Optional[Callable] = None,
    ping_target: str = DEFAULT_PING_TARGET,
    on_olt_info: Optional[Callable] = None,
    use_ssh: bool = False,
) -> DiagnosisReport:
    """
    Run full diagnosis for a single ONT.

    Args:
        input_data: Parsed input (type: serial/address/description + location)
        olt_config: OLT configuration dict with host, port, credential_key, name
        thresholds: Diagnostic thresholds
        allow_actions: Whether to perform corrective actions (reset ports, clear counters)
        log: Optional logging callback
        ping_target: IP address for remote ping
        on_olt_info: Callback when OLT info is retrieved
        use_ssh: Unused, kept for compatibility

    Returns:
        DiagnosisReport with metrics and problems
    """
    _log = log or (lambda msg, end=" ", flush=True: print(msg, end=end, flush=flush))
    host = olt_config["host"]
    port = olt_config.get("port", 23)
    username, password = load_olt_credentials(olt_config)
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