"""
SQLAlchemy models for SQLite database.
Based on SQL.md normalized schema proposal.
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, CheckConstraint
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


class Diagnosis(Base):
    """Diagnosis report (legacy - will be replaced by structured tables)."""
    __tablename__ = "diagnoses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String, nullable=False)  # ISO8601
    olt_host = Column(String, nullable=False)
    olt_name = Column(String, nullable=False, default="")
    ont_address = Column(String, nullable=False)
    input_type = Column(String, nullable=False)  # address, serial, description
    input_value = Column(String, nullable=False)
    report_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index("idx_diagnoses_ont_ts", "ont_address", "created_at"),
        Index("idx_diagnoses_olt", "olt_host"),
    )


class PortSnapshot(Base):
    """Snapshot of all ONTs on a GPON port."""
    __tablename__ = "port_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String, nullable=False)
    olt_name = Column(String, nullable=False)
    olt_host = Column(String, nullable=False)
    frame = Column(String, nullable=False)
    slot = Column(String, nullable=False)
    port = Column(String, nullable=False)
    ont_count = Column(Integer, default=0)
    data_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index("idx_port_snapshots_olt_port_ts", "olt_host", "frame", "slot", "port", "created_at"),
    )


# ──────────────────────────────────────────────
# NEW STRUCTURED TABLES (from SQL.md)
# ──────────────────────────────────────────────

class DiagnosisReport(Base):
    """Structured diagnosis report (replaces JSON blob)."""
    __tablename__ = "diagnosis_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String, nullable=False)  # ISO8601
    olt_name = Column(String, nullable=False)
    olt_host = Column(String, nullable=False)
    ont_address = Column(String, nullable=False)  # F/S/P/ONT
    ont_serial = Column(String)
    description = Column(String)  # лицевой счёт
    model = Column(String)
    version = Column(String)
    distance_m = Column(Integer)
    is_online = Column(Boolean, default=False)
    status = Column(String)

    # Optics (nullable, sentinel-safe)
    ont_rx_power = Column(Integer)  # stored as dBm * 100 for precision
    olt_rx_power = Column(Integer)
    ont_tx_power = Column(Integer)
    laser_bias = Column(Integer)
    ont_temperature = Column(Integer)
    supply_voltage = Column(Integer)

    # Errors
    upstream_errors = Column(Integer, default=0)
    downstream_errors = Column(Integer, default=0)

    # System
    cpu_usage = Column(Integer)  # -1 = unknown
    memory_usage = Column(Integer)
    cpu_temp = Column(Integer)
    online_duration = Column(String)
    last_down_cause = Column(String)
    last_up_time = Column(String)
    last_down_time = Column(String)
    last_dying_gasp = Column(String)

    # Meta
    ping_status = Column(String)
    ping_target = Column(String, default="1.1.1.1")
    match_state = Column(String)
    config_state = Column(String)

    created_at = Column(DateTime, default=datetime.now)

    # Relationships
    optics_snapshots = relationship("OpticsSnapshot", back_populates="report", cascade="all, delete-orphan")
    rule_firings = relationship("RuleFiring", back_populates="report", cascade="all, delete-orphan")
    mac_devices = relationship("MacDevice", back_populates="report", cascade="all, delete-orphan")
    lan_port_states = relationship("LanPortState", back_populates="report", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_diag_reports_ont_ts", "ont_address", "timestamp"),
        Index("idx_diag_reports_online", "is_online", "timestamp"),
        Index("idx_diag_reports_olt", "olt_host", "timestamp"),
    )


class OpticsSnapshot(Base):
    """Optics time-series for trending."""
    __tablename__ = "optics_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("diagnosis_reports.id", ondelete="CASCADE"), nullable=False)
    ont_rx_power = Column(Integer)  # dBm * 100
    olt_rx_power = Column(Integer)
    ont_tx_power = Column(Integer)
    ont_temperature = Column(Integer)
    supply_voltage = Column(Integer)
    upstream_errors = Column(Integer, default=0)
    downstream_errors = Column(Integer, default=0)
    sampled_at = Column(DateTime, default=datetime.now)

    report = relationship("DiagnosisReport", back_populates="optics_snapshots")

    __table_args__ = (
        Index("idx_optics_report", "report_id", "sampled_at"),
    )


class RuleFiring(Base):
    """Rule execution log for audit."""
    __tablename__ = "rule_firings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("diagnosis_reports.id", ondelete="CASCADE"), nullable=False)
    rule_name = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    category = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=False)

    report = relationship("DiagnosisReport", back_populates="rule_firings")

    __table_args__ = (
        CheckConstraint("severity IN ('critical', 'warning', 'info')", name="ck_severity"),
        Index("idx_rules_severity_cat", "severity", "category"),
    )


class MacDevice(Base):
    """MAC devices behind ONT."""
    __tablename__ = "mac_devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("diagnosis_reports.id", ondelete="CASCADE"), nullable=False)
    port_type = Column(String)  # ETH/WLAN
    port_number = Column(String)
    mac_address = Column(String, nullable=False)
    vendor = Column(String)

    report = relationship("DiagnosisReport", back_populates="mac_devices")

    __table_args__ = (
        Index("idx_mac_report", "report_id"),
    )


class LanPortState(Base):
    """LAN port state history."""
    __tablename__ = "lan_port_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("diagnosis_reports.id", ondelete="CASCADE"), nullable=False)
    lan_id = Column(String, nullable=False)
    port_type = Column(String)
    speed = Column(String)
    duplex = Column(String)
    link_state = Column(String, nullable=False)
    fcs_errors = Column(Integer, default=0)
    rx_bad_bytes = Column(Integer, default=0)
    tx_bad_bytes = Column(Integer, default=0)

    report = relationship("DiagnosisReport", back_populates="lan_port_states")

    __table_args__ = (
        Index("idx_lan_report", "report_id"),
    )


class Olt(Base):
    """OLT inventory (replaces YAML config)."""
    __tablename__ = "olts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    host = Column(String, nullable=False, unique=True)
    port = Column(Integer, default=23)
    credential_key = Column(String, default="RADIUS")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    onts = relationship("Ont", back_populates="olt", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_olts_active", "is_active"),
    )


class Ont(Base):
    """ONT registry (master data)."""
    __tablename__ = "onts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    olt_id = Column(Integer, ForeignKey("olts.id"), nullable=False)
    ont_address = Column(String, nullable=False)  # F/S/P/ONT
    serial = Column(String)
    description = Column(String)
    model = Column(String)
    version = Column(String)
    frame = Column(String)
    slot = Column(String)
    port = Column(String)
    ont_id = Column(String)
    first_seen = Column(DateTime, default=datetime.now)
    last_seen = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    olt = relationship("Olt", back_populates="onts")

    __table_args__ = (
        Index("idx_onts_address", "olt_id", "ont_address", unique=True),
    )


class ConfigVersion(Base):
    """Configuration history (thresholds, rules, bad_versions)."""
    __tablename__ = "config_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_type = Column(String, nullable=False)  # thresholds, rules, bad_versions
    config_yaml = Column(Text, nullable=False)
    applied_at = Column(DateTime, default=datetime.now)
    applied_by = Column(String)  # operator name / agent id

    __table_args__ = (
        CheckConstraint("config_type IN ('thresholds', 'rules', 'bad_versions')", name="ck_config_type"),
    )


class AuditLog(Base):
    """Action audit log (compliance)."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.now)
    agent_id = Column(String)  # cline/qwen/claude or operator
    action = Column(String, nullable=False)  # diagnose, clear_errors, reset_port
    ont_address = Column(String)
    olt_host = Column(String)
    parameters = Column(Text)  # JSON
    result = Column(String)  # success/error
    duration_ms = Column(Integer)

    __table_args__ = (
        Index("idx_audit_ont_ts", "ont_address", "timestamp"),
        Index("idx_audit_agent_ts", "agent_id", "timestamp"),
    )