"""SQLAlchemy models for FastAPI web API."""

from sqlalchemy import Column, Integer, String, Text, DateTime, func
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class Diagnosis(Base):
    """Diagnosis report history."""
    __tablename__ = "diagnoses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String, nullable=False)
    olt_host = Column(String, nullable=False)
    olt_name = Column(String, nullable=False, default="")
    ont_address = Column(String, nullable=False)
    input_type = Column(String, nullable=False)
    input_value = Column(String, nullable=False)
    report_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


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
    created_at = Column(DateTime, default=datetime.utcnow)