"""Configuration parsing and threshold building."""
"""Configuration parsing and threshold building with validation."""

from core.thresholds import Thresholds
from core.constants import DEFAULT_THRESHOLDS
from core.config_validator import load_config_with_validation, validate_config_file, PYDANTIC_AVAILABLE

# Map of Thresholds field names to config.yaml keys
# When a key is missing from config, the Thresholds dataclass default is used.
THRESHOLD_KEY_MAP = {
    "ont_rx_power_warn": "ont_rx_power_warn_dbm",
    "ont_rx_power_crit": "ont_rx_power_crit_dbm",
    "olt_rx_power_warn": "olt_rx_power_warn_dbm",
    "olt_rx_power_crit": "olt_rx_power_crit_dbm",
    "bip_error_warn": "bip_error_warn",
    "bip_error_crit": "bip_error_crit",
    "cpu_usage_warn": "cpu_usage_warn_pct",
    "memory_usage_warn": "memory_usage_warn_pct",
    "cpu_temp_warn": "cpu_temp_warn_c",
    "cpu_temp_crit": "cpu_temp_crit_c",
    "ont_temperature_warn": "ont_temperature_warn_c",
    "ont_temperature_crit": "ont_temperature_crit_c",
    "distance_warn": "distance_warn_m",
    "distance_crit": "distance_crit_m",
    "bad_versions": "bad_versions",
    "no_ping_models": "no_ping_models",
}


def _build_thresholds(config: dict) -> Thresholds:
    """Build Thresholds from config dict, falling back to dataclass defaults.
    
    Args:
        config: Configuration dictionary from config.yaml (already validated)
        
    Returns:
        Thresholds object with values from config or defaults
    """
    raw = config.get("thresholds", {})
    kwargs = {}
    
    for field_name, config_key in THRESHOLD_KEY_MAP.items():
        if config_key in raw:
            kwargs[field_name] = raw[config_key]
    
    # Apply defaults for missing values (Thresholds dataclass defaults)
    return Thresholds(**kwargs)


def load_config(path: str = "config.yaml"):
    """Load and validate YAML config file.
    
    Uses Pydantic validation if available, otherwise manual validation.
    Raises FileNotFoundError if config doesn't exist.
    Raises ValueError if validation fails.
    """
    return load_config_with_validation(path)