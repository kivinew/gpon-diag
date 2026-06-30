"""
WebSocket message models for real-time communication.
"""
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# Base message
# ──────────────────────────────────────────────
class WSMessageBase(BaseModel):
    type: str
    timestamp: str = Field(default_factory=lambda: __import__('datetime').datetime.now().isoformat())


# ──────────────────────────────────────────────
# Port Summary WebSocket
# ──────────────────────────────────────────────
class PortSummarySnapshot(BaseModel):
    type: Literal["snapshot"] = "snapshot"
    summaries: List[Dict[str, Any]]
    count: int


class PortSummaryUpdate(BaseModel):
    type: Literal["update"] = "update"
    summaries: List[Dict[str, Any]]
    count: int


class PortSummaryError(BaseModel):
    type: Literal["error"] = "error"
    message: str


PortSummaryWSMessage = PortSummarySnapshot | PortSummaryUpdate | PortSummaryError


# ──────────────────────────────────────────────
# Optics WebSocket
# ──────────────────────────────────────────────
class OpticsData(BaseModel):
    type: Literal["optics"] = "optics"
    data: Dict[str, Any]


class OpticsError(BaseModel):
    type: Literal["error"] = "error"
    message: str


OpticsWSMessage = OpticsData | OpticsError


# ──────────────────────────────────────────────
# Diagnosis Progress WebSocket
# ──────────────────────────────────────────────
class DiagnosisProgress(BaseModel):
    type: Literal["progress"] = "progress"
    step: str
    message: str
    percent: Optional[int] = None


class DiagnosisComplete(BaseModel):
    type: Literal["complete"] = "complete"
    report: Dict[str, Any]


class DiagnosisError(BaseModel):
    type: Literal["error"] = "error"
    message: str


class DiagnosisHistory(BaseModel):
    type: Literal["history"] = "history"
    history: List[Dict[str, Any]]


DiagnosisWSMessage = DiagnosisProgress | DiagnosisComplete | DiagnosisError | DiagnosisHistory


# ──────────────────────────────────────────────
# All WS message types
# ────────────────────────────────────────────__
WSMessage = PortSummaryWSMessage | OpticsWSMessage | DiagnosisWSMessage