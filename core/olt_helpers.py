"""OLT connection helpers — shared logic for web routes and CLI.

Extracted to avoid code duplication across diagnose.py, web/api/routes/*
and other modules that need to connect to OLT and collect data.
"""

from __future__ import annotations
import anyio
import logging
from typing import TYPE_CHECKING, Dict, Optional, List

if TYPE_CHECKING:
    from core.olt import OltConnection
    from core.thresholds import Thresholds
    from core.report import DiagnosisReport

from core.olt import get_olt_connection, OntNotFoundError
from core.parser import (
    parse_ont_info, parse_optical_info, parse_line_quality,
    parse_ont_info_summary, parse_ont_version, parse_lan_ports,
    parse_mac_addresses, parse_ipconfig, parse_wan_info,
    parse_eth_errors, parse_register_info, parse_ping_result
)
from core.models import OntMetrics, OntSummary
from core.constants import DEFAULT_PING_TARGET

logger = logging.getLogger(__name__)


def load_olt_credentials(olt_config: Dict) -> tuple[str, str]:
    """Load OLT username/password from environment variables.
    
    Resolution order:
    1. credential_key from config -> GPON_OLT_<KEY>_USERNAME/PASSWORD
    2. Sanitized OLT name -> GPON_OLT_<OLT_NAME>_USERNAME/PASSWORD
    3. Sanitized host IP -> GPON_OLT_<HOST>_USERNAME/PASSWORD
    """
    import os
    from core.utils import _olt_secret_key
    
    # 1. Explicit credential_key
    explicit_key = olt_config.get('credential_key', '')
    if explicit_key:
        username = os.getenv(f'GPON_OLT_{explicit_key}_USERNAME', '')
        password = os.getenv(f'GPON_OLT_{explicit_key}_PASSWORD', '')
        if username and password:
            return username, password

    # 2. Sanitized OLT name
    olt_name = olt_config.get('name', '')
    if olt_name:
        key = _olt_secret_key(olt_name)
        username = os.getenv(f'GPON_OLT_{key}_USERNAME', '')
        password = os.getenv(f'GPON_OLT_{key}_PASSWORD', '')
        if username and password:
            return username, password

    # 3. Sanitized host IP
    host = olt_config.get('host', '')
    if host:
        host_key = ''.join(ch if ch.isalnum() else '_' for ch in host).replace('__', '_').strip('_')
        username = os.getenv(f'GPON_OLT_{host_key}_USERNAME', '')
        password = os.getenv(f'GPON_OLT_{host_key}_PASSWORD', '')
        return username, password

    return '', ''


async def connect_to_olt(olt_config: Dict) -> 'OltConnection':
    """Create and connect to OLT, returning the connection."""
    username, password = load_olt_credentials(olt_config)
    if not username or not password:
        raise ValueError(
            f"Missing OLT credentials for '{olt_config.get('name', olt_config['host'])}'. "
            f"Set env GPON_OLT_<KEY>_USERNAME/PASSWORD or use .env file."
        )

    olt = get_olt_connection(
        olt_config["host"],
        olt_config.get("port", 23),
        username, password, 30
    )
    await anyio.to_thread.run_sync(olt.connect)
    return olt


async def find_ont_on_olt(
    olt: 'OltConnection',
    input_data: Dict,
    log=None
) -> Dict:
    """Locate ONT on connected OLT, updating input_data with location."""
    _log = log or (lambda msg, **kw: logger.info(msg))

    if input_data["type"] == "serial":
        _log(f"Поиск ONT по SN {input_data['value']}...")
        loc = await anyio.to_thread.run_sync(olt.find_ont_by_sn, input_data["value"])
        if not loc:
            _log("не найдена, пробуем поиск по описанию...")
            loc = await anyio.to_thread.run_sync(olt.find_ont_by_description, input_data["value"])
        if not loc:
            _log("по описанию тоже не найдено")
            raise OntNotFoundError(f"ONT {input_data['value']} not found on OLT")
        _log("OK")
    elif input_data["type"] == "description":
        _log(f"Поиск ONT по описанию '{input_data['value']}'...")
        loc = await anyio.to_thread.run_sync(olt.find_ont_by_description, input_data["value"])
        if not loc:
            _log("не найдена")
            raise OntNotFoundError(f"ONT {input_data['value']} not found on OLT")
        _log("OK")
    else:
        # Already have address
        loc = {
            "frame": input_data["frame"],
            "slot": input_data["slot"],
            "port": input_data["port"],
            "ont_id": input_data["ont_id"],
        }

    input_data.update(loc)
    return loc


async def collect_ont_data(
    olt: 'OltConnection',
    frame: str, slot: str, port: str, ont_id: str,
    log=None
) -> Dict:
    """Collect all ONT data from OLT."""
    _log = log or (lambda msg, **kw: logger.info(msg))
    
    raw_data = await anyio.to_thread.run_sync(
        olt.collect_ont, frame, slot, port, ont_id, _log
    )
    return raw_data


async def collect_optics_only(
    olt: 'OltConnection',
    frame: str, slot: str, port: str, ont_id: str,
    log=None
) -> Dict:
    """Collect only optical data (faster for real-time monitoring)."""
    _log = log or (lambda msg, **kw: logger.info(msg))
    
    # Only collect ont_info and optical_info
    from core.data_collector import OntDataCollector
    # For now, use full collect and filter - could optimize later
    raw_data = await anyio.to_thread.run_sync(
        olt.collect_ont, frame, slot, port, ont_id, _log
    )
    return {
        "ont_info": raw_data.get("ont_info", ""),
        "optical_info": raw_data.get("optical_info", ""),
        "line_quality": raw_data.get("line_quality", ""),
    }


def parse_ont_metrics(raw_data: Dict, input_data: Dict, olt_info: Dict = None) -> OntMetrics:
    """Parse raw OLT output into OntMetrics object."""
    metrics = OntMetrics()
    metrics.address = f"{input_data['frame']}/{input_data['slot']}/{input_data['port']}/{input_data['ont_id']}"
    metrics.frame = input_data["frame"]
    metrics.slot = input_data["slot"]
    metrics.port = input_data["port"]
    metrics.ont_id = input_data["ont_id"]
    
    if olt_info:
        metrics.olt_uptime = olt_info.get("uptime", "")
        metrics.olt_version = olt_info.get('version', '')

    if "ont_info" in raw_data:
        parse_ont_info(raw_data["ont_info"], metrics)
    if "ont_version" in raw_data:
        parse_ont_version(raw_data["ont_version"], metrics)
    if "optical_info" in raw_data:
        parse_optical_info(raw_data["optical_info"], metrics)
    if "line_quality" in raw_data:
        parse_line_quality(raw_data["line_quality"], metrics)
    if "lan_ports" in raw_data:
        from core.parser import parse_lan_ports
        parse_lan_ports(raw_data["lan_ports"], metrics)
    if "mac_addresses" in raw_data:
        from core.parser import parse_mac_addresses
        parse_mac_addresses(raw_data["mac_addresses"], metrics)
    if "ipconfig" in raw_data:
        from core.parser import parse_ipconfig
        parse_ipconfig(raw_data["ipconfig"], metrics)
    if "wan_info" in raw_data:
        from core.parser import parse_wan_info
        parse_wan_info(raw_data["wan_info"], metrics)
    if "register_info" in raw_data:
        from core.parser import parse_register_info
        parse_register_info(raw_data["register_info"], metrics)

    # Parse eth errors for each LAN port
    for lan_id in ["1", "2", "3", "4"]:
        key = f"eth_errors_raw_{lan_id}"
        if key in raw_data:
            from core.parser import parse_eth_errors
            parse_eth_errors(raw_data[key], metrics, lan_id)

    metrics.fetch_timestamp = __import__('datetime').datetime.now(
        __import__('core.constants').constants.TZ_LOCAL
    ).isoformat()

    return metrics


async def collect_port_summary(
    olt: 'OltConnection',
    frame: str, slot: str, port: str,
    log=None
) -> List[OntSummary]:
    """Collect 'display ont info summary' for all ONTs on a GPON port."""
    _log = log or (lambda msg, **kw: logger.info(msg))
    summaries = await anyio.to_thread.run_sync(
        olt.collect_port_summary, frame, slot, port, _log
    )
    return summaries


def resolve_olt_config(config: Dict, olt_host: str = None, auto_select: bool = True) -> Dict:
    """Resolve OLT configuration from config.yaml.
    
    Args:
        config: Parsed config.yaml
        olt_host: Specific OLT host to use (optional)
        auto_select: If True and no olt_host, auto-detect available OLT
    """
    if olt_host:
        for olt in config.get("olts", []):
            if olt.get("host") == olt_host:
                return olt
        raise ValueError(f"OLT with host '{olt_host}' not found in config")
    
    if auto_select:
        from core.connection_diagnosis import find_available_olt
        olt_config = find_available_olt(config)
        if not olt_config:
            raise ValueError("No OLT available. Set --olt or check .env credentials.")
        return olt_config
    
    raise ValueError("Must specify olt_host or enable auto_select")


async def run_full_diagnosis(
    input_data: Dict,
    olt_config: Dict,
    thresholds: 'Thresholds',
    allow_actions: bool = True,
    ping_target: str = DEFAULT_PING_TARGET,
    log=None
) -> 'DiagnosisReport':
    """Run complete diagnosis pipeline - shared between CLI and web."""
    _log = log or (lambda msg, **kw: logger.info(msg))
    
    # Connect
    _log("Подключение к головной станции...")
    olt = await connect_to_olt(olt_config)
    _log("OK")
    
    # Get OLT info
    _log("Получение информации о головной станции...")
    olt_info = await anyio.to_thread.run_sync(olt.get_olt_info)
    _log(f"OK ({olt_info.get('model', 'unknown')})")
    
    # Find ONT
    await find_ont_on_olt(olt, input_data, _log)
    
    # Collect data
    addr = f"{input_data['frame']}/{input_data['slot']}/{input_data['port']}/{input_data['ont_id']}"
    _log(f"Сбор данных ONT {addr}:")
    raw_data = await collect_ont_data(
        olt, input_data["frame"], input_data["slot"],
        input_data["port"], input_data["ont_id"], _log
    )
    
    # Parse metrics
    _log("Парсинг метрик...")
    metrics = parse_ont_metrics(raw_data, input_data, olt_info)
    _log("OK")
    
    # Diagnose
    _log("Анализ...")
    from core.engine import create_extended_engine
    engine = create_extended_engine(thresholds)
    problems = engine.diagnose(metrics)
    _log("OK")
    
    # Actions (clear errors, reset ports)
    if allow_actions and metrics.is_online:
        if metrics.total_bip_errors > 0:
            _log("Сброс ошибок BIP...")
            await anyio.to_thread.run_sync(
                olt.clear_line_quality,
                input_data["frame"], input_data["slot"],
                input_data["port"], input_data["ont_id"]
            )
            _log("OK")
        for port_obj in metrics.lan_ports:
            if port_obj.lan_id and port_obj.link_state == "up":
                _log(f"Сброс LAN{port_obj.lan_id}...")
                await anyio.to_thread.run_sync(
                    olt.reset_lan_port,
                    input_data["frame"], input_data["slot"],
                    input_data["port"], input_data["ont_id"],
                    int(port_obj.lan_id)
                )
                await anyio.to_thread.run_sync(
                    olt.clear_eth_errors,
                    input_data["frame"], input_data["slot"],
                    input_data["port"], input_data["ont_id"],
                    int(port_obj.lan_id)
                )
                _log("OK")
    
    # Remote ping
    if metrics.is_online and "310" not in metrics.model:
        _log(f"Remote ping ({ping_target})...")
        metrics.ping_target = ping_target
        remote_ping_result = await anyio.to_thread.run_sync(
            olt.remote_ping,
            input_data["frame"], input_data["slot"],
            input_data["port"], input_data["ont_id"],
            ip=ping_target
        )
        from core.parser import parse_ping_result
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
    
    # Build report
    from datetime import datetime
    from core.constants import TZ_LOCAL
    from core.report import DiagnosisReport
    
    return DiagnosisReport(
        datetime.now(TZ_LOCAL).isoformat(),
        olt_config.get("name", olt_config["host"]),
        metrics, problems, not metrics.is_online
    )