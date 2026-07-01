"""Threshold evaluation — business logic for checking thresholds, separate from data models."""

from typing import Optional

from core.constants import DEFAULT_THRESHOLDS
from core.thresholds import Thresholds


def evaluate_ont_rx_power(rx_power: float, thresholds: Optional[Thresholds] = None) -> str:
    """
    Evaluate ONT Rx power status based on thresholds.

    Args:
        rx_power: The ONT Rx power in dBm
        thresholds: Optional Thresholds object. Uses defaults if not provided.

    Returns:
        "ok", "warn", or "crit"
    """
    if thresholds is None:
        warn = DEFAULT_THRESHOLDS["ont_rx_power_warn"]
        crit = DEFAULT_THRESHOLDS["ont_rx_power_crit"]
    else:
        warn = thresholds.ont_rx_power_warn
        crit = thresholds.ont_rx_power_crit

    if rx_power <= crit:
        return "crit"
    if rx_power <= warn:
        return "warn"
    return "ok"


def evaluate_olt_rx_power(rx_power: float, thresholds: Optional[Thresholds] = None) -> str:
    """Evaluate OLT Rx power status based on thresholds."""
    if thresholds is None:
        warn = DEFAULT_THRESHOLDS["olt_rx_power_warn"]
        crit = DEFAULT_THRESHOLDS["olt_rx_power_crit"]
    else:
        warn = thresholds.olt_rx_power_warn
        crit = thresholds.olt_rx_power_crit

    if rx_power <= crit:
        return "crit"
    if rx_power <= warn:
        return "warn"
    return "ok"


def evaluate_ont_temperature(temp: int, thresholds: Optional[Thresholds] = None) -> str:
    """Evaluate ONT temperature status."""
    if thresholds is None:
        warn = DEFAULT_THRESHOLDS["ont_temperature_warn"]
        crit = DEFAULT_THRESHOLDS["ont_temperature_crit"]
    else:
        warn = thresholds.ont_temperature_warn
        crit = thresholds.ont_temperature_crit

    if temp >= crit:
        return "crit"
    if temp >= warn:
        return "warn"
    return "ok"


def evaluate_cpu_temperature(temp: int, thresholds: Optional[Thresholds] = None) -> str:
    """Evaluate CPU temperature status."""
    if thresholds is None:
        warn = DEFAULT_THRESHOLDS["cpu_temp_warn"]
        crit = DEFAULT_THRESHOLDS["cpu_temp_crit"]
    else:
        warn = thresholds.cpu_temp_warn
        crit = thresholds.cpu_temp_crit

    if temp >= crit:
        return "crit"
    if temp >= warn:
        return "warn"
    return "ok"


def evaluate_distance(distance_m: int, thresholds: Optional[Thresholds] = None) -> str:
    """Evaluate ONT distance status."""
    if thresholds is None:
        warn = DEFAULT_THRESHOLDS["distance_warn"]
        crit = DEFAULT_THRESHOLDS["distance_crit"]
    else:
        warn = thresholds.distance_warn
        crit = thresholds.distance_crit

    if distance_m >= crit:
        return "crit"
    if distance_m >= warn:
        return "warn"
    return "ok"


def evaluate_bip_errors(total_errors: int, thresholds: Optional[Thresholds] = None) -> str:
    """Evaluate BIP error status."""
    if thresholds is None:
        warn = DEFAULT_THRESHOLDS["bip_error_warn"]
        crit = DEFAULT_THRESHOLDS["bip_error_crit"]
    else:
        warn = thresholds.bip_error_warn
        crit = thresholds.bip_error_crit

    if total_errors >= crit:
        return "crit"
    if total_errors >= warn:
        return "warn"
    return "ok"


def is_bad_version(version: str, thresholds: Optional[Thresholds] = None) -> bool:
    """Check if firmware version is in bad versions list."""
    if thresholds is None:
        bad_versions = DEFAULT_THRESHOLDS["bad_versions"]
    else:
        bad_versions = thresholds.bad_versions

    return version.upper() in [v.upper() for v in bad_versions]


def should_skip_ping(model: str, thresholds: Optional[Thresholds] = None) -> bool:
    """Check if ping should be skipped for this model."""
    if thresholds is None:
        no_ping_models = DEFAULT_THRESHOLDS["no_ping_models"]
    else:
        no_ping_models = thresholds.no_ping_models

    return model in no_ping_models