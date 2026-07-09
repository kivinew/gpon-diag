"""Configuration validation using Pydantic for type safety and error reporting."""

from typing import Optional, List, Dict, Any
from pathlib import Path

# Try to import pydantic, but make it optional
try:
    from pydantic import BaseModel, Field, field_validator, model_validator
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    # Define dummy classes for type hints when pydantic is not available
    class BaseModel:
        pass
    def Field(*args, **kwargs):
        return None
    def field_validator(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    def model_validator(*args, **kwargs):
        def decorator(func):
            return func
        return decorator


class OLTConfig(BaseModel):
    """Single OLT configuration."""
    name: str = Field(..., description="Human-readable OLT name")
    host: str = Field(..., description="OLT IP address or hostname")
    port: int = Field(default=23, description="Telnet port")
    credential_key: Optional[str] = Field(default=None, description="Env var key suffix (e.g., RADIUS)")
    
    if PYDANTIC_AVAILABLE:
        @field_validator('host')
        @classmethod
        def validate_host(cls, v: str) -> str:
            if not v or not v.strip():
                raise ValueError("OLT host cannot be empty")
            return v.strip()
        
        @field_validator('port')
        @classmethod
        def validate_port(cls, v: int) -> int:
            if not 1 <= v <= 65535:
                raise ValueError("Port must be between 1 and 65535")
            return v


class ThresholdsConfig(BaseModel):
    """Diagnostic thresholds configuration."""
    ont_rx_power_warn_dbm: float = -26.5
    ont_rx_power_crit_dbm: float = -30.0
    olt_rx_power_warn_dbm: float = -33.0
    olt_rx_power_crit_dbm: float = -35.0
    bip_error_warn: int = 10000
    bip_error_crit: int = 100000
    cpu_temp_warn_c: int = 75
    cpu_temp_crit_c: int = 90
    cpu_usage_warn_pct: int = 90
    memory_usage_warn_pct: int = 85
    ont_temperature_warn_c: int = 65
    ont_temperature_crit_c: int = 75
    distance_warn_m: int = 19000
    distance_crit_m: int = 20000
    bad_versions: List[str] = []
    no_ping_models: List[str] = ["310"]
    
    if PYDANTIC_AVAILABLE:
        @field_validator('*')
        @classmethod
        def validate_numeric_thresholds(cls, v):
            # Allow any numeric values, just ensure they're valid
            return v


class ReportConfig(BaseModel):
    """Report output configuration."""
    format: str = "text"
    save_to_file: bool = True
    reports_dir: str = "data/reports"
    include_timestamp: bool = True
    
    if PYDANTIC_AVAILABLE:
        @field_validator('format')
        @classmethod
        def validate_format(cls, v: str) -> str:
            if v not in ("text", "json"):
                raise ValueError("Report format must be 'text' or 'json'")
            return v


class AppConfig(BaseModel):
    """Full application configuration."""
    olts: List[OLTConfig] = Field(default_factory=list, description="List of OLT configurations")
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
    ping_target: str = "1.1.1.1"
    oui_db_path: str = "data/oui.txt"
    
    if PYDANTIC_AVAILABLE:
        @model_validator(mode='after')
        def validate_olts(self):
            if not self.olts:
                raise ValueError("At least one OLT must be configured")
            # Check for duplicate hosts
            hosts = [olt.host for olt in self.olts]
            if len(hosts) != len(set(hosts)):
                raise ValueError("Duplicate OLT hosts found in config")
            return self


def validate_config_file(path: str = "config.yaml") -> "AppConfig":
    """Validate and parse config.yaml, raising ValidationError on failure."""
    import yaml
    
    if not Path(path).exists():
        raise FileNotFoundError(f"Config file '{path}' not found")
    
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    
    if raw is None:
        raise ValueError("Config file is empty")
    
    return AppConfig(**raw)


def load_and_validate_config(path: str = "config.yaml") -> Dict[str, Any]:
    """Load config, validate, and return as dict for backward compatibility."""
    config = validate_config_file(path)
    return config.model_dump()


def validate_config_manual(config: Dict[str, Any]) -> tuple[bool, List[str]]:
    """Manual validation fallback when pydantic is not available.
    
    Returns:
        (is_valid, list_of_errors)
    """
    errors = []
    
    # Check olts
    olts = config.get("olts", [])
    if not olts:
        errors.append("No OLTs configured (config.olts must have at least one entry)")
    else:
        seen_hosts = set()
        for i, olt in enumerate(olts):
            if not isinstance(olt, dict):
                errors.append(f"OLT {i}: must be an object")
                continue
            if "host" not in olt or not olt["host"]:
                errors.append(f"OLT {i}: missing or empty 'host'")
            elif olt["host"] in seen_hosts:
                errors.append(f"OLT {i}: duplicate host '{olt['host']}'")
            else:
                seen_hosts.add(olt["host"])
            if "port" in olt and (not isinstance(olt["port"], int) or not 1 <= olt["port"] <= 65535):
                errors.append(f"OLT {i}: invalid port '{olt['port']}' (must be 1-65535)")
    
    # Check thresholds
    thresholds = config.get("thresholds", {})
    if not isinstance(thresholds, dict):
        errors.append("thresholds must be an object")
    else:
        # Validate numeric thresholds
        numeric_fields = {
            "ont_rx_power_warn_dbm": (-50, 0),
            "ont_rx_power_crit_dbm": (-50, 0),
            "olt_rx_power_warn_dbm": (-50, 0),
            "olt_rx_power_crit_dbm": (-50, 0),
            "bip_error_warn": (0, 10000000),
            "bip_error_crit": (0, 10000000),
            "cpu_temp_warn_c": (-50, 150),
            "cpu_temp_crit_c": (-50, 150),
            "cpu_usage_warn_pct": (0, 100),
            "memory_usage_warn_pct": (0, 100),
            "ont_temperature_warn_c": (-50, 100),
            "ont_temperature_crit_c": (-50, 100),
            "distance_warn_m": (0, 50000),
            "distance_crit_m": (0, 50000),
        }
        for field, (min_v, max_v) in numeric_fields.items():
            if field in thresholds:
                val = thresholds[field]
                if not isinstance(val, (int, float)):
                    errors.append(f"thresholds.{field}: must be a number")
                elif not min_v <= val <= max_v:
                    errors.append(f"thresholds.{field}: value {val} out of range [{min_v}, {max_v}]")
        
        # Validate list fields
        for field in ["bad_versions", "no_ping_models"]:
            if field in thresholds and not isinstance(thresholds[field], list):
                errors.append(f"thresholds.{field}: must be a list")
    
    # Check report config
    report = config.get("report", {})
    if not isinstance(report, dict):
        errors.append("report must be an object")
    elif "format" in report and report["format"] not in ("text", "json"):
        errors.append("report.format must be 'text' or 'json'")
    
    # Check ping_target
    if "ping_target" in config and not isinstance(config["ping_target"], str):
        errors.append("ping_target must be a string")
    
    # Check oui_db_path
    if "oui_db_path" in config and not isinstance(config["oui_db_path"], str):
        errors.append("oui_db_path must be a string")
    
    return len(errors) == 0, errors


def load_config_with_validation(path: str = "config.yaml") -> Dict[str, Any]:
    """Load config.yaml with validation (pydantic if available, manual fallback)."""
    import yaml
    import os
    
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file '{path}' not found")
    
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    if config is None:
        raise ValueError("Config file is empty")
    
    if PYDANTIC_AVAILABLE:
        # Use pydantic for validation
        try:
            validated = AppConfig(**config)
            return validated.model_dump()
        except Exception as e:
            raise ValueError(f"Config validation failed: {e}")
    else:
        # Manual validation fallback
        valid, errors = validate_config_manual(config)
        if not valid:
            raise ValueError("Config validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
        return config