"""Data models for GPON diagnostic framework."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class LanPort:
    lan_id: str
    port_type: str
    speed: str
    duplex: str
    link_state: str


@dataclass
class MacDevice:
    port_type: str
    port_number: str
    mac: str
    vendor: str = "n/a"


@dataclass
class OntMetrics:
    address: str = ""
    frame: str = ""
    slot: str = ""
    port: str = ""
    ont_id: str = ""
    status: str = ""
    serial: str = ""
    description: str = ""
    model: str = ""
    version: str = ""
    distance_m: int = -1
    ont_rx_power: float = 999.0
    olt_rx_power: float = 999.0
    ont_tx_power: float = 999.0
    laser_bias_current: int = -1
    ont_temperature: int = -999
    supply_voltage: float = -1.0
    module_subtype: str = ""
    vendor_pn: str = ""
    upstream_errors: int = 0
    downstream_errors: int = 0
    eth_errors: dict = field(default_factory=dict)   # {lan_id: {fcs: int, received_bad_bytes: int, sent_bad_bytes: int}}
    lan_ports: list = field(default_factory=list)
    mac_devices: list = field(default_factory=list)
    ip_address: str = ""
    cpu_usage: int = -1
    memory_usage: int = -1
    cpu_temp: int = -999
    last_down_cause: str = ""
    last_up_time: str = ""
    last_down_time: str = ""
    last_dying_gasp_time: str = ""
    fetch_timestamp: str = ""
    online_duration: str = ""
    match_state: str = ""
    config_state: str = ""
    power_reduction: str = ""
    service_profile: str = ""
    line_profile: str = ""
    service_profile_id: str = ""
    line_profile_id: str = ""
    eth_port_count: int = 0
    gem_vlans: dict = field(default_factory=dict)   # {gem_index: vlan}
    wan_connections: list = field(default_factory=list)
    register_status: str = ""
    register_age: int = -1
    register_down_count: int = 0
    register_uptime: str = ""
    register_downtime: str = ""
    register_all_downtimes: list = field(default_factory=list)
    register_falls_24h: int = 0
    register_falls_7d: int = 0
    troubleshooting: str = ""
    ping_status: str = ""
    ping_target: str = "1.1.1.1"
    ping_result: dict = field(default_factory=dict)  # {transmit, receive, lost, loss_pct, avg_rtt}

    @property
    def is_online(self) -> bool:
        return self.status.lower() in ("online", "working")

    @property
    def total_bip_errors(self) -> int:
        return self.upstream_errors + self.downstream_errors

    @property
    def has_lan_activity(self) -> bool:
        return any(p.link_state == "up" for p in self.lan_ports)