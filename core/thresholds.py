"""Thresholds — loaded from config.yaml."""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Thresholds:
    ont_rx_power_warn: float = -26.0
    ont_rx_power_crit: float = -30.0
    olt_rx_power_warn: float = -32.0
    olt_rx_power_crit: float = -35.0
    bip_error_warn: int = 10000
    bip_error_crit: int = 100000
    cpu_temp_warn: int = 75
    cpu_temp_crit: int = 85
    cpu_usage_warn: int = 80
    memory_usage_warn: int = 85
    distance_warn: int = 15000
    distance_crit: int = 20000
    bad_versions: list = field(default_factory=list)
