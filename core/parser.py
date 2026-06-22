"""Parser — converts raw Huawei CLI output into OntMetrics."""

import datetime
import logging
import re
from core.models import OntMetrics, LanPort, MacDevice

logger = logging.getLogger(__name__)

PATTERNS = {
    "status":           r"Run state\s*: *(.+)",
    "serial":           r"(?i)SN\s*: *([\da-fA-F]{16})",
    "description":      r"Description\s*: *(.+)",
    "distance":         r"ONT distance\(m\)\s*: *(\d+)",
    "distance_last":    r"ONT last distance\(m\)\s*: *(\d+)",
    "online_duration":  r"ONT online duration\s*: *(.+)",
    "uptime":           r"Last up time\s*:\s*(.+)",
    "downtime":         r"Last down time\s*: *([\d-]+\s[\d:+-]+)",
    "dying_gasp_time":  r"Last dying gasp time\s*: *([\d-]+\s[\d:+-]+)",
    "downcause":        r"Last down cause\s*: *(\S+)",
    "match_state":      r"Match state\s*: *(.+)",
    "config_state":     r"Config state\s*: *(.+)",
    "power_reduction":  r"Power reduction status\s*: *(.+)",
    "line_profile":     r"Line profile name\s*: *(.+)",
    "line_profile_id":  r"Line profile ID\s*: *(\d+)",
    "service_profile":  r"Service profile name\s*: *(.+)",
    "service_profile_id": r"Service profile ID\s*: *(\d+)",
    "eth_port_count":   r"ETH\s+(\d+)\s+\d+",
    "gem_index":        r"<Gem Index\s+(\d+)>",
    "gem_vlan":         r"Mapping VLAN.*\n.*\n\s+\d+\s+(\d+)",
    "ont_model":        r"ONT Type\s*: *(.+)",
    "ont_model_alt":    r"Equipment-ID\s*: *(\w+)",
    "soft_version":     r"Main Software Version\s*: *(\S+)",
    "ont_rx_power":     r"Rx\s+optical power\(dBm\)\s*: *(-?[\d.]+)",
    "olt_rx_power":     r"OLT Rx ONT optical power\(dBm\)\s*: *(-?[\d.]+)",
    "ont_tx_power":     r"Tx optical power\(dBm\)\s*: *(-?[\d.]+)",
    "laser_bias":       r"Laser bias current\(mA\)\s*: *(\d+)",
    "ont_temperature":  r"Temperature\(C\)\s*: *(-?\d+)",
    "supply_voltage":   r"Voltage\(V\)\s*: *([\d.]+)",
    "catv_rx_power":    r"CATV Rx optical power\(dBm\)\s*: *(-?[\d.]+)",
    "module_subtype":   r"Module sub-type\s*: *(.+)",
    "vendor_pn":        r"Vendor PN\s*: *(.+)",
    "upstream_errors":  r"Upstream frame BIP error count\s*: *(\d+)",
    "downstream_errors": r"Downstream frame BIP error count\s*: *(\d+)",
    "lan_ports":        r"(\d+)\s+(\d+)\s+(GE|FE)\s+(\d+|-)\s+(full|half|-)\s+(up|down)",
    "mac_entry":        r"(?:(?:ETH|WLAN)\s+)?(\d+)\s+([\da-fA-F]{4}-[\da-fA-F]{4}-[\da-fA-F]{4})",
    "mac_only":         r"([\da-fA-F]{2}[-][\da-fA-F]{2}[-][\da-fA-F]{2}[-][\da-fA-F]{2}[-][\da-fA-F]{2}[-][\da-fA-F]{2})",
    "ip_output":        r"IP address\s*: *(\d+\.\d+\.\d+\.\d+)",
    "memory_usage":     r"Memory utilization[^:]*: *(\d+)",
    "cpu_temp":         r"CPU temperature[^:]*: *(\d+)",
    "cpu_usage":        r"CPU utilization[^:]*: *(\d+)",
    "eth_fcs":          r"Received FCS error frames\s+: *(\d+)",
    "eth_received_bad_bytes": r"Received bad bytes\s+: *(\d+)",
    "eth_sent_bad_bytes": r"Sent bad bytes\s+: *(\d+)",
    "register_status":  r"Status\s*: *(.+)",
    "register_age":     r"Age\(s\)\s*: *(\d+)",
    "register_downtime": r"DownTime\s*: *([\d-]+\s[\d:+-]+)",
    "register_uptime":   r"UpTime\s*: *([\d-]+\s[\d:+-]+)",
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
    m.line_profile_id = _search(raw, PATTERNS["line_profile_id"]) or ""
    m.service_profile_id = _search(raw, PATTERNS["service_profile_id"]) or ""
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
    model = _search(raw, PATTERNS["ont_model_alt"])
    if not model:
        model = _search(raw, PATTERNS["ont_model"])
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
    seen = set()
    for match in re.finditer(PATTERNS["mac_entry"], raw):
        mac = match.group(2)
        if mac.lower() in seen:
            continue
        seen.add(mac.lower())
        m.mac_devices.append(MacDevice(
            port_type="ETH", port_number=match.group(1), mac=mac,
        ))
    if not m.mac_devices:
        for match in re.finditer(PATTERNS["mac_only"], raw):
            mac = match.group(1)
            if mac.lower() in seen:
                continue
            seen.add(mac.lower())
            m.mac_devices.append(MacDevice(
                port_type="ETH", port_number="?", mac=mac,
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
    """Parse 'display ont register-info' output. Extracts register entries."""
    uptimes = re.findall(r"UpTime\s*:\s*([\d-]+\s[\d:+-]+)", raw)
    downtimes = re.findall(r"DownTime\s*:\s*([\d-]+\s[\d:+-]+)", raw)
    
    m.register_down_count = sum(1 for d in downtimes if d and d != "-")
    m.register_uptime = uptimes[0] if uptimes else ""
    m.register_downtime = downtimes[0] if downtimes else ""
    
    # Parse all downtimes and check frequency (last 24h, 7d)
    m.register_all_downtimes = []
    for d in downtimes:
        if d and d != "-":
            m.register_all_downtimes.append(d)
    
    # Calculate recent falls (within last 24h and 7d)
    now = datetime.datetime.now()
    m.register_falls_24h = 0
    m.register_falls_7d = 0
    
    for d in m.register_all_downtimes:
        try:
            dt = datetime.datetime.strptime(d, "%Y-%m-%d %H:%M:%S%z")
            dt_naive = dt.replace(tzinfo=None)
            days_ago = (now - dt_naive).total_seconds() / 86400
            if days_ago <= 1:
                m.register_falls_24h += 1
            if days_ago <= 7:
                m.register_falls_7d += 1
        except ValueError:
            pass


def parse_ping_result(raw: str, m: OntMetrics) -> None:
    transmit = re.search(r"Transmit packets?\s*:\s*(\d+)", raw)
    receive = re.search(r"Receive(?:d)? packets?\s*:\s*(\d+)", raw)
    lost = re.search(r"Lost packets?\s*:\s*(\d+)", raw)
    loss_pct = re.search(r"Loss ratio\s*:\s*(\d+)%", raw)
    avg_rtt = re.search(r"(?:Average|Round trip time)\s*\(ms\)\s*:\s*(\d+)", raw)
    m.ping_result = {
        "transmit": int(transmit.group(1)) if transmit else 0,
        "receive": int(receive.group(1)) if receive else 0,
        "lost": int(lost.group(1)) if lost else 0,
        "loss_pct": int(loss_pct.group(1)) if loss_pct else -1,
        "avg_rtt": int(avg_rtt.group(1)) if avg_rtt else -1,
    }