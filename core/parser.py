"""Parser — converts raw Huawei CLI output into OntMetrics."""

import logging
import re
from core.models import OntMetrics, LanPort, MacDevice

logger = logging.getLogger(__name__)

PATTERNS = {
    "status":           "Run state\\s*: *(.+)",
    "serial":           "(?i)SN\\s*: *([\\da-fA-F]{16})",
    "description":      "Description\\s*: *(.+)",
    "distance":         "ONT distance\\(m\\)\\s*: *(\\d+)",
    "distance_last":    "ONT last distance\\(m\\)\\s*: *(\\d+)",
    "online_duration":  "ONT online duration\\s*: *(.+)",
    "uptime":           "Last up time\\s*: *([\\d-]+[\\d:+-]+)",
    "downtime":         "Last down time\\s*: *([\\d-]+[\\d:+-]+)",
    "dying_gasp_time":  "Last dying gasp time\\s*: *([\\d-]+[\\d:+-]+)",
    "downcause":        "Last down cause\\s*: *(\\S+)",
    "match_state":      "Match state\\s*: *(.+)",
    "config_state":     "Config state\\s*: *(.+)",
    "power_reduction":  "Power reduction status\\s*: *(.+)",
    "service_profile":  "Service profile name\\s*: *(.+)",
    "line_profile":     "Line profile name\\s*: *(.+)",
    "eth_port_count":   "ETH\\s+(\\d+)\\s+\\d+",
    "gem_index":        "<Gem Index\\s+(\\d+)>",
    "gem_vlan":         "Mapping VLAN.*\\n.*\\n\\s+\\d+\\s+(\\d+)",
    "ont_model":        "ONT Type\\s*: *(.+)",
    "ont_model_alt":    "Equipment-ID\\s*: *(\\w+)",
    "soft_version":     "Main Software Version\\s*: *(\\S+)",
    "ont_rx_power":     "Rx\\s+optical power\\(dBm\\)\\s*: *(-?[\\d.]+)",
    "olt_rx_power":     "OLT Rx ONT optical power\\(dBm\\)\\s*: *(-?[\\d.]+)",
    "ont_tx_power":     "Tx optical power\\(dBm\\)\\s*: *(-?[\\d.]+)",
    "laser_bias":       "Laser bias current\\(mA\\)\\s*: *(\\d+)",
    "ont_temperature":  "Temperature\\(C\\)\\s*: *(-?\\d+)",
    "supply_voltage":   "Voltage\\(V\\)\\s*: *([\\d.]+)",
    "catv_rx_power":    "CATV Rx optical power\\(dBm\\)\\s*: *(-?[\\d.]+)",
    "module_subtype":   "Module sub-type\\s*: *(.+)",
    "vendor_pn":        "Vendor PN\\s*: *(.+)",
    "upstream_errors":  "Upstream frame BIP error count\s*: *(\\d+)",
    "downstream_errors":"Downstream frame BIP error count\s*: *(\\d+)",
    "lan_ports":        "(\\d+)\\s+(\\d+)\\s+(GE|FE)\\s+(\\d+|-)\\s+(full|half|-)\\s+(up|down)",
    "mac_entry":        "(ETH|WLAN)\\s+(\\d+)\\s+([\\da-fA-F]{4}-[\\da-fA-F]{4}-[\\da-fA-F]{4})",
    "ip_output":        "IP address\\s*: *(\\d+\\.\\d+\\.\\d+\\.\\d+)",
    "memory_usage":     "Memory utilization[^:]*: *(\\d+)",
    "cpu_temp":         "CPU temperature[^:]*: *(\\d+)",
    "cpu_usage":        "CPU utilization[^:]*: *(\\d+)",
    # Ethernet errors
    "eth_fcs":          "Received FCS error frames\s*: *(\\d+)",
    "eth_received_bad_bytes": "Received bad bytes\s*: *(\\d+)",
    "eth_sent_bad_bytes": "Sent bad bytes\s*: *(\\d+)",
    # Register info
    "register_status":  "Status\\s*: *(.+)",
    "register_age":     "Age\\(s\\)\\s*: *(\\d+)",
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
    port_section = re.search(r"Port-type\\s+Port-number.*?ETH\\s+(\\d+)\\s+", raw, re.DOTALL)
    m.eth_port_count = int(port_section.group(1)) if port_section else 0
    # GEM VLAN mapping
    m.gem_vlans = {}
    gem_blocks = re.split(r"<Gem Index\\s+(\\d+)>", raw)
    for i in range(1, len(gem_blocks), 2):
        gem_idx = gem_blocks[i]
        block = gem_blocks[i + 1] if i + 1 < len(gem_blocks) else ""
        # Find first Mapping VLAN value in this block
        vlan_m = re.search(r"Mapping VLAN[\\s\\S]*?\\n\\s+\\d+\\s+(\\d+)", block)
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
    sections = re.split(r'Index\\s*:\\s*(\\d+)', raw)
    for i in range(1, len(sections), 2):
        if i + 1 < len(sections):
            idx = sections[i]
            block = sections[i + 1]
            conn = {"index": idx}
            for field in ["Service type", "Connection type", "IPv4 Connection status",
                          "IPv4 access type", "IPv4 address", "Subnet mask",
                          "Default gateway", "Manage VLAN", "Manage priority"]:
                val = _search(block, rf"{field}\\s*:\\s*(.+)")
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

def parse_eth_errors(raw: str, m: OntMetrics, lan_id: str) -> None:
    """Parse 'display statistics ont-eth' output for a specific LAN port."""
    if lan_id not in m.eth_errors:
        m.eth_errors[lan_id] = {}
    fcs = _search_int(raw, PATTERNS["eth_fcs"])
    rx_bad = _search_int(raw, PATTERNS["eth_received_bad_bytes"])
    tx_bad = _search_int(raw, PATTERNS["eth_sent_bad_bytes"])
    if fcs is not None:
        m.eth_errors[lan_id]["fcs"] = fcs
    if rx_bad is not None:
        m.eth_errors[lan_id]["received_bad_bytes"] = rx_bad
    if tx_bad is not None:
        m.eth_errors[lan_id]["sent_bad_bytes"] = tx_bad

def parse_register_info(raw: str, m: OntMetrics) -> None:
    """Parse 'display ont register-info' output."""
    m.register_status = _search(raw, PATTERNS["register_status"]) or ""
    m.register_age = _search_int(raw, PATTERNS["register_age"])