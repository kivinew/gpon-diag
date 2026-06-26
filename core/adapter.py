"""Adapter — bridges GPON_class.py to the new diagnostic framework."""

import os
import sys
import re
from datetime import datetime

# GPON_class.py location — MUST be first import
_GPON_DIR = "/mnt/e/DOWNLOADS/CREATIVE/PYTHON/GitHub/SecureCRT_Backups/GPON_HW"
sys.path.insert(0, _GPON_DIR)

# Now import GPON_class
import importlib
import GPON_class as _gc
importlib.reload(_gc)

from core.models import OntMetrics, LanPort
from core.engine import create_default_engine
from core.thresholds import Thresholds
from core.report import DiagnosisReport
from core.crt_stub import FakeCRT


def diagnose_ont(ont_address, olt_config, thresholds):
    host = olt_config["host"]
    port = olt_config.get("port", 23)
    username = olt_config.get("username", "")
    password = olt_config.get("password", "")

    crt = FakeCRT(host, port, username, password)
    
    try:
        crt.connect()
        _gc.inject_crt(crt)
        
        gpon = _gc.GPON()
        
        # Try to locate ONT by serial number, description or raw address.
        # Original code handled only specific serial patterns. Extend to accept any
        # alphanumeric identifier as a possible serial number.
        if re.fullmatch(r"(?i)(48575443|hwtc)[\da-f]{8}", ont_address.strip()):
            ont = gpon.find_by_sn(ont_address.strip().upper())
        elif "/" in ont_address:
            parts = ont_address.replace("/", " ").split()
            ont = _gc.Ont(parts)
        else:
            # Fallback: try serial lookup first, then description search.
            candidate = ont_address.strip()
            ont = gpon.find_by_sn(candidate.upper())
            if ont is None:
                ont = gpon.find_by_description(candidate)
        
        
        if ont is None:
            now = datetime.now().isoformat()
            return DiagnosisReport(now, olt_config.get("name", host), OntMetrics(address=ont_address), [], True)
        
        gpon.ont = ont
        gpon.config = _gc.GPONConfig()
        gpon.send(f"scroll {gpon.config.scroll_lines}")
        gpon.get_ont_info()
        
        metrics = OntMetrics()
        # Preserve the original ONT identifier for the report
        metrics.address = ont_address
        metrics.frame = ont.frame
        metrics.slot = ont.slot
        metrics.port = ont.port
        metrics.ont_id = ont.ont_id
        
        d = gpon.data
        metrics.status = d.get("status", "")
        metrics.serial = d.get("serial", "")
        metrics.description = d.get("description", "")
        metrics.model = d.get("model", "")
        metrics.version = d.get("version", "")
        dist = d.get("distance", "")
        metrics.distance_m = int(dist) if dist and dist != "-" else -1
        try:
            metrics.ont_rx_power = float(d["ont_rx_power"]) if d.get("ont_rx_power") and d["ont_rx_power"] != "-" else 999.0
        except (ValueError, TypeError):
            metrics.ont_rx_power = 999.0
        try:
            metrics.olt_rx_power = float(d["olt_rx_power"]) if d.get("olt_rx_power") and d["olt_rx_power"] != "-" else 999.0
        except (ValueError, TypeError):
            metrics.olt_rx_power = 999.0
        metrics.upstream_errors = d.get("upstream_errors", 0)
        metrics.downstream_errors = d.get("downstream_errors", 0)
        metrics.last_down_cause = d.get("downcause", "")
        metrics.last_up_time = d.get("uptime", "")
        metrics.last_down_time = d.get("downtime", "")
        metrics.memory_usage = int(d["memory_usage"]) if d.get("memory_usage") and str(d["memory_usage"]).isdigit() else -1
        metrics.cpu_usage = int(d["cpu_usage"]) if d.get("cpu_usage") and str(d["cpu_usage"]).isdigit() else -1
        metrics.cpu_temp = int(d["cpu_temp"]) if d.get("cpu_temp") and str(d["cpu_temp"]).lstrip("-").isdigit() else -999
        metrics.ip_address = d.get("ip_address", "")
        metrics.troubleshooting = d.get("troubleshooting", "")
        metrics.fetch_timestamp = datetime.now().isoformat()
        
        for p in d.get("lan_ports", []):
            metrics.lan_ports.append(LanPort(
                lan_id=p.get("lan_id", ""), port_type=p.get("port_type", ""),
                speed=p.get("speed", ""), duplex=p.get("duplex", ""), link_state=p.get("link_state", ""),
            ))
        
        engine = create_default_engine(thresholds)
        problems = engine.diagnose(metrics)
        
        return DiagnosisReport(
            datetime.now().isoformat(), olt_config.get("name", host),
            metrics, problems, not metrics.is_online,
        )
        
    finally:
        crt.disconnect()
