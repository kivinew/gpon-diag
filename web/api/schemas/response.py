"""
Pydantic response models for FastAPI API.
These match the DiagnosisReport.to_dict() structure.
"""
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# Nested models
# ──────────────────────────────────────────────
class LanPortResponse(BaseModel):
    id: str
    type: str
    speed: str
    duplex: str
    link: str


class EthErrorsResponse(BaseModel):
    fcs: int = 0
    received_bad_bytes: int = 0
    sent_bad_bytes: int = 0


class MacDeviceResponse(BaseModel):
    mac: str
    port_type: str
    port_number: str


class WanConnectionResponse(BaseModel):
    index: str
    service_type: Optional[str] = None
    connection_type: Optional[str] = None
    ipv4_connection_status: Optional[str] = None
    ipv4_access_type: Optional[str] = None
    ipv4_address: Optional[str] = None
    subnet_mask: Optional[str] = None
    default_gateway: Optional[str] = None
    manage_vlan: Optional[str] = None
    manage_priority: Optional[str] = None


class DiagnosisProblemResponse(BaseModel):
    severity: Literal["critical", "warning", "info"]
    category: str
    description: str
    recommendation: str


class PingResultResponse(BaseModel):
    transmit: int = 0
    receive: int = 0
    lost: int = 0
    loss_pct: int = -1
    avg_rtt: int = -1


class GemVlanResponse(BaseModel):
    gem_index: str
    vlan: str


# ──────────────────────────────────────────────
# Main Diagnosis Report Response
# ──────────────────────────────────────────────
class DiagnosisReportResponse(BaseModel):
    """Full diagnosis report matching DiagnosisReport.to_dict()"""
    timestamp: str
    head_station: str
    ont: str
    is_online: bool
    status: str
    serial: str
    description: str
    model: Optional[str] = None
    version: Optional[str] = None
    distance_m: int = -1
    online_duration: Optional[str] = None
    olt_uptime: Optional[str] = None
    match_state: Optional[str] = None
    config_state: Optional[str] = None
    power_reduction: Optional[str] = None
    service_profile: Optional[str] = None
    service_profile_id: Optional[str] = None
    line_profile: Optional[str] = None
    line_profile_id: Optional[str] = None
    eth_port_count: int = 0
    gem_vlans: Dict[str, str] = {}
    last_down_cause: Optional[str] = None
    last_up_time: Optional[str] = None
    last_down_time: Optional[str] = None
    last_dying_gasp_time: Optional[str] = None
    ont_rx_power: float = 999.0
    olt_rx_power: float = 999.0
    ont_tx_power: float = 999.0
    laser_bias_current: int = -1
    ont_temperature: int = -999
    supply_voltage: float = -1.0
    module_subtype: Optional[str] = None
    upstream_errors: int = 0
    downstream_errors: int = 0
    lan_ports: List[LanPortResponse] = []
    eth_errors: Dict[str, EthErrorsResponse] = {}
    mac_devices: List[MacDeviceResponse] = []
    wan_connections: List[WanConnectionResponse] = []
    ping_status: Optional[str] = None
    ping_target: str = "1.1.1.1"
    ping_result: PingResultResponse = PingResultResponse()
    register_down_count: int = 0
    register_uptime: Optional[str] = None
    register_downtime: Optional[str] = None
    register_falls_24h: int = 0
    register_falls_7d: int = 0
    problems: List[DiagnosisProblemResponse] = []


# ──────────────────────────────────────────────
# Optics Response
# ──────────────────────────────────────────────
class OpticsResponse(BaseModel):
    ont_rx_power: float = 999.0
    olt_rx_power: float = 999.0
    ont_tx_power: float = 999.0
    laser_bias_current: int = -1
    ont_temperature: int = -999
    supply_voltage: float = -1.0
    distance_m: int = -1
    upstream_errors: int = 0
    downstream_errors: int = 0
    total_bip_errors: int = 0
    is_online: bool = False
    model: Optional[str] = None
    serial: Optional[str] = None
    description: Optional[str] = None


# ──────────────────────────────────────────────
# Port Summary Response
# ──────────────────────────────────────────────
class PortSummaryItemResponse(BaseModel):
    ont_id: str
    status: str
    rx_power: float = 999.0
    tx_power: float = 999.0
    distance: int = -1
    last_down_cause: str = ""
    description: str = ""
    collected_at: str
    is_online: bool
    rx_power_status: Literal["ok", "warn", "crit"]


class PortSummaryResponse(BaseModel):
    frame: str
    slot: str
    port: str
    olt_host: str
    ont_count: int
    summaries: List[PortSummaryItemResponse]


# ──────────────────────────────────────────────
# History Response
# ──────────────────────────────────────────────
class HistoryItemResponse(BaseModel):
    id: int
    timestamp: str
    created_at: str
    olt_name: str
    olt_host: str
    ont_address: str
    input_type: str
    input_value: str
    is_online: bool
    problems_count: int
    model: Optional[str] = None
    version: Optional[str] = None
    ont_rx_power: Optional[float] = None
    olt_rx_power: Optional[float] = None
    distance_m: Optional[int] = None
    ping_status: Optional[str] = None


class HistoryResponse(BaseModel):
    history: List[HistoryItemResponse]
    total: int
    limit: int
    offset: int


# ────────────────────────────────────────────────────────────
# OLT Response
# ──────────────────────────────────────────────
class OLTResponse(BaseModel):
    name: str
    host: str
    port: int
    credential_key: str
    reachable: Optional[bool] = None
    model: Optional[str] = None
    version: Optional[str] = None
    uptime: Optional[str] = None


class OLTsResponse(BaseModel):
    olts: List[OLTResponse]


# ──────────────────────────────────────────────
# Health Response
# ──────────────────────────────────────────────
class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"] = "ok"
    version: str = "0.2.0"
    uptime_seconds: float
    db_connected: bool
    olt_pool_size: int
    active_connections: int


# ──────────────────────────────────────────────
# Generic Responses
# ──────────────────────────────────────────────
class SuccessResponse(BaseModel):
    success: bool = True
    message: str
    data: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    error_code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None