"""Diagnosis Problem and Report models."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from core.models import OntMetrics

logger = logging.getLogger(__name__)


class DiagnosisProblem:
    SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}

    def __init__(self, severity, category, description, recommendation):
        self.severity = severity
        self.category = category
        self.description = description
        self.recommendation = recommendation

    @property
    def sort_key(self):
        return self.SEVERITY_ORDER.get(self.severity, 9)

    def __str__(self):
        icon = {"critical": "!!!", "warning": "(!)", "info": "(i)"}.get(self.severity, "")
        return f"{icon} {self.description}\n     -> {self.recommendation}"

    def to_dict(self):
        return {
            "severity": self.severity,
            "category": self.category,
            "description": self.description,
            "recommendation": self.recommendation,
        }


@dataclass
class DiagnosisReport:
    timestamp: str
    olt_name: str
    metrics: OntMetrics
    problems: list
    is_offline: bool = False

    @property
    def has_problems(self) -> bool:
        return len(self.problems) > 0

    def to_text(self) -> str:
        m = self.metrics
        lines = [
            f"OLT: {self.olt_name}",
            f"ONT: {m.address}",
            f"{'Терминал доступен.' if m.is_online else 'Терминал НЕДОСТУПЕН.'}",
        ]

        if not m.is_online:
            if m.last_down_time:
                lines.append(f"Отключён: {m.last_down_time}")
            if m.last_dying_gasp_time:
                lines.append(f"Dying Gasp: {m.last_dying_gasp_time}")
            if m.last_up_time:
                lines.append(f"Последнее включение: {m.last_up_time}")
            if m.distance_m >= 0:
                lines.append(f"Расстояние: {m.distance_m} м")
            if m.last_down_cause:
                lines.append(f"Причина: {m.last_down_cause}")
        else:
            if m.description:
                lines.append(f"Описание: {m.description}")
            if m.serial:
                lines.append(f"SN: {m.serial}")
            if m.model:
                lines.append(f"Модель: {m.model}")
            if m.version:
                lines.append(f"ПО: {m.version}")
            if m.distance_m >= 0:
                lines.append(f"Расстояние: {m.distance_m} м")
            if m.online_duration and m.online_duration != "-":
                lines.append(f"Аптайм: {m.online_duration}")
            if m.match_state:
                lines.append(f"Match state: {m.match_state}")
            if m.config_state:
                lines.append(f"Config state: {m.config_state}")
            if m.power_reduction and m.power_reduction != "-":
                lines.append(f"Power reduction: {m.power_reduction}")
            if m.service_profile:
                lines.append(f"Service profile: {m.service_profile}")
            if m.line_profile:
                lines.append(f"Line profile: {m.line_profile}")
            if m.eth_port_count:
                lines.append(f"ETH портов: {m.eth_port_count}")
            if m.gem_vlans:
                for gem_idx, vlan in sorted(m.gem_vlans.items(), key=lambda x: int(x[0])):
                    lines.append(f"GEM {gem_idx}: VLAN {vlan}")
            if m.ont_rx_power < 900:
                lines.append(f"ONT Rx: {m.ont_rx_power} dBm")
            if m.olt_rx_power < 900:
                lines.append(f"OLT Rx: {m.olt_rx_power} dBm")
            if m.ont_tx_power < 900:
                lines.append(f"ONT Tx: {m.ont_tx_power} dBm")
            if m.laser_bias_current >= 0:
                lines.append(f"Laser bias: {m.laser_bias_current} mA")
            if m.ont_temperature > -900:
                lines.append(f"Температура: {m.ont_temperature}°C")
            if m.supply_voltage >= 0:
                lines.append(f"Напряжение: {m.supply_voltage} V")
            if m.module_subtype:
                lines.append(f"Module class: {m.module_subtype}")
            if m.total_bip_errors > 0:
                lines.append(f"BIP ошибки: Up={m.upstream_errors}, Down={m.downstream_errors}")
            if m.has_lan_activity:
                for p in m.lan_ports:
                    if p.link_state == "up":
                        lines.append(f"LAN{p.lan_id}: {p.port_type} {p.speed} Mbps {p.duplex}")

            # WAN connections
            if hasattr(m, 'wan_connections') and m.wan_connections:
                lines.append("")
                lines.append("WAN-соединения:")
                for conn in m.wan_connections:
                    idx = conn.get('index', '?')
                    svc = conn.get('service_type', '')
                    status = conn.get('ipv4_connection_status', '')
                    ip = conn.get('ipv4_address', '-')
                    vlan = conn.get('manage_vlan', '')
                    lines.append(f"  #{idx} {svc}: {status}, IP={ip}, VLAN={vlan}")

        if self.problems:
            lines.append("")
            lines.append("=== ПРОБЛЕМЫ ===")
            for p in sorted(self.problems, key=lambda x: x.sort_key):
                lines.append(str(p))
        else:
            lines.append("")
            lines.append("Нарушений не выявлено.")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        m = self.metrics
        return {
            "timestamp": self.timestamp,
            "olt": self.olt_name,
            "ont": m.address,
            "is_online": m.is_online,
            "status": m.status,
            "serial": m.serial,
            "description": m.description,
            "model": m.model,
            "version": m.version,
            "distance_m": m.distance_m,
            "online_duration": m.online_duration,
            "match_state": m.match_state,
            "config_state": m.config_state,
            "power_reduction": m.power_reduction,
            "service_profile": m.service_profile,
            "line_profile": m.line_profile,
            "eth_port_count": m.eth_port_count,
            "gem_vlans": m.gem_vlans,
            "last_down_cause": m.last_down_cause,
            "last_up_time": m.last_up_time,
            "last_down_time": m.last_down_time,
            "last_dying_gasp_time": m.last_dying_gasp_time,
            "ont_rx_power": m.ont_rx_power,
            "olt_rx_power": m.olt_rx_power,
            "ont_tx_power": m.ont_tx_power,
            "laser_bias_current": m.laser_bias_current,
            "ont_temperature": m.ont_temperature,
            "supply_voltage": m.supply_voltage,
            "module_subtype": m.module_subtype,
            "upstream_errors": m.upstream_errors,
            "downstream_errors": m.downstream_errors,
            "lan_ports": [{"id": p.lan_id, "type": p.port_type, "speed": p.speed, "duplex": p.duplex, "link": p.link_state} for p in m.lan_ports],
            "wan_connections": m.wan_connections,
            "problems": [p.to_dict() for p in self.problems],
        }
