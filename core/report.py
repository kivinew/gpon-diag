"""Diagnosis Problem and Report models."""

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from core.models import OntMetrics

TZ_LOCAL = timezone(timedelta(hours=7))

logger = logging.getLogger(__name__)

MAC_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "oui.txt")


def _load_mac_database():
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


def _get_vendor(mac, mac_db):
    clean = re.sub(r"[^A-Fa-f0-9]", "", mac).upper()
    return mac_db.get(clean[:6], "n/a")


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


BAD_VERSIONS = {
    "V1R003C00S108",
    "V1R006C00S130",
    "V1R006C00S205",
    "V1R006C00S201",
    "V1R006C01S201",
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
        lines = [f"Головная станция: {self.olt_name} | ONT = {m.address}"]


        if m.description and m.description != "ONT_NO_DESCRIPTION":
            lines.append(f"Дескрипшн (лицевой счёт) = {m.description}")
        elif m.description == "ONT_NO_DESCRIPTION":
            lines.append("Дескрипшн (лицевой счёт) не установлен")
        if m.serial:
            lines.append(f"PON SN = {m.serial}")

        if not m.is_online:
            lines.append("Терминал недоступен.")
            if m.last_down_time and m.last_down_time != "-":
                lines.append(f"Отключён: {m.last_down_time}")
            if m.last_up_time and m.last_up_time != "-":
                lines.append(f"Время последнего включения: {m.last_up_time}")
            if m.distance_m >= 0:
                lines.append(f"Расстояние от OLT (м): {m.distance_m}")
            if m.last_down_cause and m.last_down_cause != "-":
                cause = m.last_down_cause
                if cause == "нет данных":
                    lines.append("Причина недоступности не зафиксирована.")
                elif "LOS" in cause or "LOSI" in cause or "LOBI" in cause:
                    lines.append(f"Причина: {cause} — отсутствует оптический сигнал.")
                elif "LOFi" in cause:
                    lines.append(f"Причина: {cause} — низкий оптический сигнал.")
                elif "dying-gasp" in cause:
                    lines.append(f"Причина: {cause} — отключение питания.")
                elif "wire-down" in cause:
                    lines.append(f"Причина: {cause} — магистральный кабель (массовая проблема).")
                else:
                    lines.append(f"Причина: {cause}")
            if m.last_down_cause == "-" and m.register_down_count == 0:
                lines.append("Нет записей о падениях в реестре.")

            if self.problems:
                lines.append("")
                lines.append("Рекомендации:")
                for p in sorted(self.problems, key=lambda x: x.sort_key):
                    lines.append(p.recommendation)

            return "\n".join(lines)

        # ONLINE
        lines.append("Терминал доступен.")
        if m.last_up_time:
            lines.append(f"Включён: {m.last_up_time}")
        if m.model:
            lines.append(f"Модель терминала: {m.model}")
        if m.version:
            bad = " !!!" if m.version in BAD_VERSIONS else ""
            lines.append(f"Версия ПО: {m.version}{bad}")
        if m.distance_m >= 0:
            lines.append(f"Расстояние от OLT (м): {m.distance_m}")
        if m.online_duration and m.online_duration != "-":
            lines.append(f"Аптайм: {m.online_duration}")
        if m.power_reduction and m.power_reduction != "-":
            lines.append(f"Power reduction: {m.power_reduction}")
        lines.append("")

        if m.ont_rx_power < 900:
            lines.append(f"ONT Rx (dBm): {m.ont_rx_power}")
        if m.olt_rx_power < 900:
            lines.append(f"OLT Rx (dBm): {m.olt_rx_power}")
        if m.upstream_errors > 0 or m.downstream_errors > 0:
            lines.append(f"Ошибки оптики: Up={m.upstream_errors}, Down={m.downstream_errors}")
        else:
            lines.append("Ошибок оптики не обнаружено.")
        lines.append("")

        if m.lan_ports:
            for p in m.lan_ports:
                if p.link_state == "up":
                    errs = m.eth_errors.get(p.lan_id, {})
                    fcs = errs.get("fcs", 0)
                    rx_bad = errs.get("received_bad_bytes", 0)
                    tx_bad = errs.get("sent_bad_bytes", 0)
                    err_str = ""
                    if fcs + rx_bad + tx_bad > 0:
                        err_str = f" [FCS={fcs}, bad={rx_bad + tx_bad}]"
                    lines.append(f"LAN{p.lan_id}: {p.port_type}, {p.speed} Mbps, {p.duplex}, Link=up{err_str}")
            if not m.has_lan_activity:
                lines.append("Ни один LAN-порт не в состоянии UP.")
        lines.append("")

        if m.mac_devices:
            mac_db = _load_mac_database()
            lines.append("MAC-адреса устройств за ONT:")
            seen = set()
            for dev in m.mac_devices:
                mac = dev.mac
                if mac in seen:
                    continue
                seen.add(mac)
                vendor = _get_vendor(mac, mac_db)
                port_label = "LAN" if dev.port_type == "ETH" else dev.port_type
                lines.append(f"{port_label}{dev.port_number} {mac} — {vendor}")
            lines.append("")

        if m.ping_status:
            pr = m.ping_result
            target = getattr(m, 'ping_target', '1.1.1.1')
            if pr and pr.get("transmit"):
                lines.append(f"Пинг: {m.ping_status} ({pr['receive']}/{pr['transmit']})")
                if pr.get("lost", 0) > 0:
                    lines.append(f"Потеряно пакетов: {pr['lost']}")
            else:
                lines.append(f"Пинг: {m.ping_status}")

        if self.problems:
            lines.append("")
            lines.append("Рекомендации:")
            for p in sorted(self.problems, key=lambda x: x.sort_key):
                lines.append(p.recommendation)
        else:
            lines.append("")
            lines.append("Нарушений не выявлено.")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        m = self.metrics
        return {
            "timestamp": self.timestamp,
            "head_station": self.olt_name,
            "ont": m.address,
            "is_online": m.is_online,
            "status": m.status,
            "serial": m.serial,
            "description": m.description,
            "model": m.model,
            "version": m.version,
            "distance_m": m.distance_m,
            "online_duration": m.online_duration,
            "olt_uptime": m.olt_uptime,
            "match_state": m.match_state,
            "config_state": m.config_state,
            "power_reduction": m.power_reduction,
            "service_profile": m.service_profile,
            "service_profile_id": m.service_profile_id,
            "line_profile": m.line_profile,
            "line_profile_id": m.line_profile_id,
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
            "eth_errors": m.eth_errors,
            "mac_devices": [{"mac": d.mac, "port_type": d.port_type, "port_number": d.port_number} for d in m.mac_devices],
            "wan_connections": m.wan_connections,
            "ping_status": m.ping_status,
            "ping_target": m.ping_target,
            "ping_result": m.ping_result,
            "register_down_count": m.register_down_count,
            "register_uptime": m.register_uptime,
            "register_downtime": m.register_downtime,
            "register_falls_24h": m.register_falls_24h,
            "register_falls_7d": m.register_falls_7d,
            "problems": [p.to_dict() for p in self.problems],
        }