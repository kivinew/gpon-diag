"""
Pydantic request models for FastAPI routes.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal, List
import re


# ──────────────────────────────────────────────
# Base validators
# ──────────────────────────────────────────────
def sanitize_ont_param(value: str) -> str:
    """Validate ONT parameter contains only digits."""
    if not re.fullmatch(r'\d+', value):
        raise ValueError(f"Invalid ONT parameter '{value}': must contain only digits")
    return value


def validate_address(value: str) -> str:
    """Validate F/S/P/ONT address format."""
    parts = value.split("/")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        raise ValueError("Address must be in format F/S/P/ONT (digits only)")
    return value


# ──────────────────────────────────────────────
# Diagnose
# ──────────────────────────────────────────────
class DiagnoseRequest(BaseModel):
    """Request to start ONT diagnosis."""
    address: str = Field(..., description="ONT address (F/S/P/ONT), serial number, or description (fl_...)")
    olt_host: Optional[str] = Field(None, description="Specific OLT host (optional, auto-detect if omitted)")
    allow_actions: bool = Field(True, description="Perform corrective actions (reset LAN, clear BIP, ping)")

    @field_validator("address")
    @classmethod
    def validate_address_or_serial(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Address cannot be empty")
        return v


class DiagnoseResponse(BaseModel):
    """Immediate response with task ID."""
    task_id: str
    status: Literal["pending", "running"]
    message: str = "Diagnosis started. Poll GET /api/diagnose/{task_id} for result."


class DiagnoseStatusResponse(BaseModel):
    """Polling response for diagnosis status."""
    task_id: str
    status: Literal["pending", "running", "completed", "failed"]
    progress: Optional[dict] = None  # {step: "collect|analyze|actions", message: "..."}
    result: Optional[dict] = None  # Full report when completed
    error: Optional[str] = None


# ──────────────────────────────────────────────
# Optics
# ──────────────────────────────────────────────
class OpticsRequest(BaseModel):
    """Request for real-time optics data."""
    address: str = Field(..., description="ONT address F/S/P/ONT")
    olt_host: Optional[str] = Field(None, description="OLT host (optional)")

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        return validate_address(v)


# ──────────────────────────────────────────────
# Search
# ──────────────────────────────────────────────
class SearchRequest(BaseModel):
    """Search ONT by serial, address, or description."""
    query: str = Field(..., description="Serial number, F/S/P/ONT, or description (fl_...)")
    olt_host: Optional[str] = Field(None, description="Specific OLT host (optional, search all if omitted)")


class SearchResultItem(BaseModel):
    ont_address: str
    olt_host: str
    olt_name: str
    serial: str
    description: str
    is_online: bool
    model: str
    ont_rx_power: Optional[float] = None
    olt_rx_power: Optional[float] = None
    distance_m: Optional[int] = None


class SearchResponse(BaseModel):
    results: List[SearchResultItem]
    total: int


# ──────────────────────────────────────────────
# Actions
# ──────────────────────────────────────────────
class ResetLanRequest(BaseModel):
    address: str = Field(..., description="ONT address F/S/P/ONT")
    lan_id: int = Field(..., ge=1, le=4, description="LAN port number (1-4)")
    olt_host: Optional[str] = None

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        return validate_address(v)


class ClearBipRequest(BaseModel):
    address: str = Field(..., description="ONT address F/S/P/ONT")
    olt_host: Optional[str] = None

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        return validate_address(v)


class RemotePingRequest(BaseModel):
    address: str = Field(..., description="ONT address F/S/P/ONT")
    target_ip: str = Field("1.1.1.1", description="Target IP for ping")
    olt_host: Optional[str] = None

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        return validate_address(v)


class ActionResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None


# ──────────────────────────────────────────────
# History
# ──────────────────────────────────────────────
class HistoryQueryParams(BaseModel):
    q: Optional[str] = Field(None, description="Search query (ONT address, serial, description)")
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)
    olt_host: Optional[str] = Field(None, description="Filter by OLT host")
    date_from: Optional[str] = Field(None, description="ISO date from")
    date_to: Optional[str] = Field(None, description="ISO date to")
    status: Optional[Literal["online", "offline"]] = Field(None, description="Filter by online status")


class HistoryItem(BaseModel):
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


class HistoryResponse(BaseModel):
    history: List[HistoryItem]
    total: int
    limit: int
    offset: int


# ──────────────────────────────────────────────
# Port Summary
# ──────────────────────────────────────────────
class PortSummaryRequest(BaseModel):
    frame: str
    slot: str
    port: str
    olt_host: Optional[str] = None

    @field_validator("frame", "slot", "port")
    @classmethod
    def validate_digits(cls, v: str) -> str:
        return sanitize_ont_param(v)


class OntSummaryItem(BaseModel):
    ont_id: str
    status: str
    rx_power: Optional[float] = None
    tx_power: Optional[float] = None
    distance: Optional[int] = None
    last_down_cause: Optional[str] = None
    description: Optional[str] = None
    collected_at: Optional[str] = None
    is_online: bool
    rx_power_status: Optional[Literal["ok", "warn", "crit"]] = None


class PortSummaryResponse(BaseModel):
    summaries: List[OntSummaryItem]
    count: int
    frame: str
    slot: str
    port: str
    olt_host: str
    olt_name: str


# ──────────────────────────────────────────────
# OLTs
# ──────────────────────────────────────────────
class OLTInfo(BaseModel):
    name: str
    host: str
    port: int
    credential_key: Optional[str] = None
    reachable: bool = False


class OLTsResponse(BaseModel):
    olts: List[OLTInfo]
    total: int


# ──────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────
class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    version: str
    uptime_seconds: float
    db_connected: bool
    olt_pool_active: int
    timestamp: str