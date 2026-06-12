"""Parser — converts raw Huawei CLI output into OntMetrics."""

import logging
import re
from core.models import OntMetrics, LanPort, MacDevice

logger = logging.getLogger(__name__)


PATTERNS = {
    "status":           r"Run state\s*:\s*(.+)",
    "serial":           r"(?i)SN\s*:\s*([\da-fA-F]{16})",
    "description":      r"Description\s*:\s*(.+)",
    "distance":         r"ONT distance\(m\)\s*:\s*(\d+)",
    "distance_last":    r"ONT last distance\(m\)\s*:\s*(\d+)",
    "online_duration":  r"ONT online duration\s*:\s*(.+)",
    "uptime":           r"Last up time\s*:\s*([\d-]+\s[\d:+-]+)",
    "downtime":         r"Last down time\s*:\s*([\d-]+\s[\d:+-]+)",
    "dying_gasp_time":  r"Last dying gasp time\s*:\s*([\d-]+\s[\d:+-]+)",
    "downcause":        r"Last down cause\s*:\s*(\S+)",
    "match_state":      r"Match state\s*:\s*(.+)",
    "config_state":     r"Config state\s*:\s*(.+)",
    "power_reduction":  r"Power reduction status\s*:\s*(.+)",
    "service_profile":  r"Service profile name\s*:\s*(.+)",
    "line_profile":     r"Line profile name\s*:\s*(.+)",
    "eth_port_count":   r"ETH\s+(\d+)\s+\d+",
    "gem_index":        r"<Gem Index\s+(\d+)>",
    "gem_vlan":         r"Mapping VLAN.*\n.*\n\s+\d+\s+(\d+)",
    "ont_model":        r"ONT Type\s*:\s*(.+)",
    "ont_model_alt":    r"Equipment-ID\s*:\s*(\w+)",
    "soft_version":     r"Main Software Version\s*:\s*(\S+)",
    "ont_rx_power":     r"Rx\s+optical power\(dBm\)\s*:\s*(-?[\d.]+)",
    "olt_rx_power":     r"OLT Rx ONT optical power\(dBm\)\s*:\s*(-?[\d.]+)",
    "ont_tx_power":     r"Tx optical power\(dBm\)\s*:\s*(-?[\d.]+)",
    "laser_bias":       r"Laser bias current\(mA\)\s*:\s*(\d+)",
    "ont_temperature":  r"Temperature\(C\)\s*:\s*(-?\d+)",
    "supply_voltage":   r"Voltage\(V\)\s*:\s*([\d.]+)",
    "catv_rx_power":    r"CATV Rx optical power\(dBm\)\s*:\s*(-?[\d.]+)",
    "module_subtype":   r"Module sub-type\s*:\s*(.+)",
    "vendor_pn":        r"Vendor PN\s*:\s*(.+)",
    "upstream_errors":  r"Upstream frame BIP error count\s*:\s*(\d+)",
    "downstream_errors":r"Downstream frame BIP error count\s*:\s*(\d+)",
    "lan_ports":        r"(\d+)\s+(\d+)\s+(GE|FE)\s+(\d+|-)+\s+(full|half|-)\s+(up|down)",
    "mac_entry":        r"(ETH|WLAN)\s+(\d+)\s+([\da-fA-F]{4}-[\da-fA-F]{4}-[\da-fA-F]{4})",
    "ip_output":        r"IP address\s*:\s*(\d+\.\d+\.\d+\.\d+)",
    "memory_usage":     r"Memory utilization[^:]*:\s*(\d+)",
    "cpu_temp":         r"CPU temperature[^:]*:\s*(\d+)",
    "cpu_usage":        r"CPU utilization[^:]*:\s*(\d+)",
}


def _search(text, pattern):
    m = re.search(pattern, text)
    return m.group(1).strip() if m else None


def _search_int(text, pattern):
    val = _search(text, pattern)
    try:
        return int(val) if val is not None else 0
    except (ValueError, TypeError):
        return 0


def _search_float(text, pattern):
    val = _search(text, pattern)
    try:
        return float(val) if val is not None else 999.0
    except (ValueError, TypeError):
        return 999.0


def parse_ont_info(raw: str, m: OntMetrics) -> None:
    m.status = _search(raw, PATTERNS["status"]) or ""
    m.serial = _search(raw, PATTERNS["serial"]) or ""
    m.description = _search(raw, PATTERNS["description"]) or ""
    # Distance: prefer primary, fallback to last known
    dist = _search(raw, PATTERNS["distance"])
    if dist and dist != "-":
        m.distance_m = int(dist)
    else:
        dist_last = _search(raw, PATTERNS["distance_last"])
        m.distance_m = int(dist_last) if dist_last and dist_last != "-" else -1
    m.last_up_time = _search(raw, PATTERNS["uptime"]) or ""
    m.last_down_time = _search(raw, PATTERNS["downtime"]) or ""
    m.last_dying_gasp_time = _search(raw, PATTERNS["dying_gasp_time"]) or ""
    m.last_down_cause = _search(raw, PATTERNS["downcause"]) or ""
    m.match_state = _search(raw, PATTERNS["match_state"]) or ""
    m.config_state = _search(raw, PATTERNS["config_state"]) or ""
    m.power_reduction = _search(raw, PATTERNS["power_reduction"]) or ""
    m.service_profile = _search(raw, PATTERNS["service_profile"]) or ""
    m.line_profile = _search(raw, PATTERNS["line_profile"]) or ""
    # ETH port count from Port-type / Port-number table
    port_section = re.search(r"Port-type\s+Port-number.*?ETH\s+(\d+)\s+", raw, re.DOTALL)
    m.eth_port_count = int(port_section.group(1)) if port_section else 0
    # GEM VLAN mapping
    m.gem_vlans = {}
    gem_blocks = re.split(r"<Gem Index\s+(\d+)>", raw)
    for i in range(1, len(gem_blocks), 2):
        gem_idx = gem_blocks[i]
        block = gem_blocks[i + 1] if i + 1 < len(gem_blocks) else ""
        # Find first Mapping VLAN value in this block
        vlan_m = re.search(r"Mapping VLAN[\s\S]*?\n\s+\d+\s+(\d+)", block)
        if vlan_m:
            m.gem_vlans[gem_idx] = vlan_m.group(1)
    mem = _search(raw, PATTERNS["memory_usage"])
    m.memory_usage = int(mem) if mem else -1
    cpu_t = _search(raw, PATTERNS["cpu_temp"])
    m.cpu_temp = int(cpu_t) if cpu_t else -999
    cpu_u = _search(raw, PATTERNS["cpu_usage"])
    m.cpu_usage = int(cpu_u) if cpu_u else -1
    m.online_duration = _search(raw, PATTERNS["online_duration"]) or ""


def parse_ont_version(raw: str, m: OntMetrics) -> None:
    model = _search(raw, PATTERNS["ont_model"])
    if not model:
        model = _search(raw, PATTERNS["ont_model_alt"])
    m.model = model or ""
    m.version = _search(raw, PATTERNS["soft_version"]) or ""


def parse_optical_info(raw: str, m: OntMetrics) -> None:
    m.ont_rx_power = _search_float(raw, PATTERNS["ont_rx_power"])
    m.olt_rx_power = _search_float(raw, PATTERNS["olt_rx_power"])
    m.ont_tx_power = _search_float(raw, PATTERNS["ont_tx_power"])
    m.laser_bias_current = _search_int(raw, PATTERNS["laser_bias"])
    m.ont_temperature = _search_int(raw, PATTERNS["ont_temperature"])
    m.supply_voltage = _search_float(raw, PATTERNS["supply_voltage"])
    m.module_subtype = _search(raw, PATTERNS["module_subtype"]) or ""
    m.vendor_pn = _search(raw, PATTERNS["vendor_pn"]) or ""


def parse_line_quality(raw: str, m: OntMetrics) -> None:
    m.upstream_errors = _search_int(raw, PATTERNS["upstream_errors"])
    m.downstream_errors = _search_int(raw, PATTERNS["downstream_errors"])


def parse_lan_ports(raw: str, m: OntMetrics) -> None:
    m.lan_ports = []
    for match in re.finditer(PATTERNS["lan_ports"], raw):
        m.lan_ports.append(LanPort(
            lan_id=match.group(2), port_type=match.group(3),
            speed=match.group(4), duplex=match.group(5), link_state=match.group(6),
        ))


def parse_mac_addresses(raw: str, m: OntMetrics) -> None:
    m.mac_devices = []
    for match in re.finditer(PATTERNS["mac_entry"], raw):
        m.mac_devices.append(MacDevice(
            port_type=match.group(1), port_number=match.group(2), mac=match.group(3),
        ))


def parse_ipconfig(raw: str, m: OntMetrics) -> None:
    m.ip_address = _search(raw, PATTERNS["ip_output"]) or ""


def parse_wan_info(raw: str, m: OntMetrics) -> None:
    """Parse 'display ont wan-info' output. Extracts WAN connections."""
    m.wan_connections = []
    # Split by Index sections
    sections = re.split(r'Index\s*:\s*(\d+)', raw)
    for i in range(1, len(sections), 2):
        if i + 1 < len(sections):
            idx = sections[i]
            block = sections[i + 1]
            conn = {"index": idx}
            for field in ["Service type", "Connection type", "IPv4 Connection status",
                          "IPv4 access type", "IPv4 address", "Subnet mask",
                          "Default gateway", "Manage VLAN", "Manage priority"]:
                val = _search(block, rf"{field}\s*:\s*(.+)")
                if val:
                    conn[field.lower().replace(" ", "_")] = val
            m.wan_connections.append(conn)


def parse_lan_ports_detail(raw: str, m: OntMetrics) -> None:
    """Parse 'display ont port state' output with speed/duplex."""
    m.lan_ports = []
    for match in re.finditer(PATTERNS["lan_ports"], raw):
        m.lan_ports.append(LanPort(
            lan_id=match.group(2), port_type=match.group(3),
            speed=match.group(4), duplex=match.group(5), link_state=match.group(6),
        ))
