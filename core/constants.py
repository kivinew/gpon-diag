"""Centralized constants and configuration defaults."""

from datetime import timezone, timedelta

# ──────────────────────────────────────────────
# Timezone
# ──────────────────────────────────────────────
TZ_LOCAL = timezone(timedelta(hours=7))

# ──────────────────────────────────────────────
# Telnet timeouts and sleep durations (seconds)
# ──────────────────────────────────────────────
DEFAULT_CONNECT_TIMEOUT = 15
DEFAULT_COMMAND_TIMEOUT = 5
DEFAULT_COLLECT_TIMEOUT = 30
IDLE_TIMEOUT = 120

# Connection stabilization delays
LOGIN_STABILIZE_DELAY = 1.0
COMMAND_DELAY = 0.5
ENABLE_DELAY = 1.5
CONFIG_DELAY = 1.5
GPON_CTX_DELAY = 1.0
QUIT_GPON_DELAY = 1.0
DRAIN_SOCKET_DELAY = 0.3
MORE_PROMPT_DELAY = 0.3
PING_DELAY = 8.0
PING_READ_DELAY = 5.0

# Retry/backoff
MAX_CONNECT_ATTEMPTS = 3
CONNECT_RETRY_BASE_DELAY = 3  # seconds, multiplied by attempt number
MAX_CONNECT_RETRY_DELAY = 30

# ──────────────────────────────────────────────
# OLT connection limits
# ──────────────────────────────────────────────
MAX_CONNECTIONS_PER_OLT = 2

# ──────────────────────────────────────────────
# Default diagnostic thresholds
# ──────────────────────────────────────────────
DEFAULT_THRESHOLDS = {
    "ont_rx_power_warn": -26.5,
    "ont_rx_power_crit": -30.0,
    "olt_rx_power_warn": -33.0,
    "olt_rx_power_crit": -35.0,
    "bip_error_warn": 10000,
    "bip_error_crit": 100000,
    "cpu_temp_warn": 75,
    "cpu_temp_crit": 90,
    "cpu_usage_warn": 90,
    "ont_temperature_warn": 65,
    "ont_temperature_crit": 75,
    "memory_usage_warn": 85,
    "distance_warn": 19000,
    "distance_crit": 20000,
    "bad_versions": [
        "V1R003C00S108",
        "V1R006C00S130",
        "V1R006C00S205",
        "V1R006C00S201",
        "V1R006C01S201",
    ],
    "no_ping_models": [],
}

# ──────────────────────────────────────────────
# Bad firmware versions (for version checking)
# ──────────────────────────────────────────────
BAD_VERSIONS = {
    "V1R003C00S108",
    "V1R006C00S130",
    "V1R006C00S205",
    "V1R006C00S201",
    "V1R006C01S201",
}

# ──────────────────────────────────────────────
# Bad firmware versions
# ──────────────────────────────────────────────
BAD_VERSIONS = {
    "V1R003C00S108",
    "V1R006C00S130",
    "V1R006C00S205",
    "V1R006C00S201",
    "V1R006C01S201",
}

# ──────────────────────────────────────────────
# Ping and network
# ──────────────────────────────────────────────
DEFAULT_PING_TARGET = "1.1.1.1"
DEFAULT_TELNET_PORT = 23

# ──────────────────────────────────────────────
# Status strings
# ──────────────────────────────────────────────
ONLINE_STATUSES = {"online", "working"}
OFFLINE_STATUSES = {"offline", "initial"}

# ──────────────────────────────────────────────
# Report paths
# ──────────────────────────────────────────────
DEFAULT_REPORTS_DIR = "data/reports"
DEFAULT_DB_PATH = "data/diagnoses.db"
MAC_DB_PATH = "data/oui.txt"

# ──────────────────────────────────────────────
# Input parsing
# ──────────────────────────────────────────────
ONT_ADDRESS_PATTERN = r"^\d+/\d+/\d+/\d+$"
SERIAL_PATTERN = r"(?i)^(48575443|hwtc)[\da-f]{8}$"
DESCRIPTION_PATTERN = r"^(fl_|kes)?\d{5,16}$"
DESCRIPTION_DIGITS_PATTERN = r"^\d{5,16}$"

# ──────────────────────────────────────────────
# OLT credential env var prefix
# ──────────────────────────────────────────────
CREDENTIAL_ENV_PREFIX = "GPON_OLT_"