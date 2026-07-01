# GPON Diagnostic Framework — core package

from core.models import OntMetrics, LanPort, MacDevice, OntSummary
from core.engine import DiagnosticEngine, Rule, create_default_engine, create_extended_engine
from core.parser import PATTERNS, parse_ont_info, parse_optical_info
from core.olt import OltConnection, get_olt_connection, OntNotFoundError, close_all
from core.thresholds import Thresholds
from core.report import DiagnosisProblem, DiagnosisReport
from core.reporter import save_text_report
from core.config_parser import _build_thresholds, load_config
from core.constants import (
    TZ_LOCAL,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_COMMAND_TIMEOUT,
    IDLE_TIMEOUT,
    MAX_CONNECTIONS_PER_OLT,
    DEFAULT_THRESHOLDS,
    DEFAULT_PING_TARGET,
    DEFAULT_TELNET_PORT,
    ONLINE_STATUSES,
    DEFAULT_REPORTS_DIR,
    DEFAULT_DB_PATH,
    MAC_DB_PATH,
    CREDENTIAL_ENV_PREFIX,
    BAD_VERSIONS,
)
from core.utils import (
    get_mac_database,
    get_vendor,
    load_olt_credentials,
    parse_input,
    sanitize_ont_param,
    is_online_status,
    is_offline_status,
)
from core.threshold_evaluator import (
    evaluate_ont_rx_power,
    evaluate_olt_rx_power,
    evaluate_ont_temperature,
    evaluate_cpu_temperature,
    evaluate_distance,
    evaluate_bip_errors,
    is_bad_version,
    should_skip_ping,
)

__all__ = [
    # Models
    'OntMetrics', 'LanPort', 'MacDevice', 'OntSummary',
    # Engine
    'DiagnosticEngine', 'Rule', 'create_default_engine', 'create_extended_engine',
    # Parser
    'PATTERNS', 'parse_ont_info', 'parse_optical_info',
    # OLT
    'OltConnection', 'get_olt_connection', 'OntNotFoundError', 'close_all',
    # Thresholds & Report
    'Thresholds', 'DiagnosisProblem', 'DiagnosisReport', 'save_text_report',
    # Config
    '_build_thresholds', 'load_config',
    # Constants
    'TZ_LOCAL',
    'DEFAULT_CONNECT_TIMEOUT',
    'DEFAULT_COMMAND_TIMEOUT',
    'IDLE_TIMEOUT',
    'MAX_CONNECTIONS_PER_OLT',
    'DEFAULT_THRESHOLDS',
    'DEFAULT_PING_TARGET',
    'DEFAULT_TELNET_PORT',
    'ONLINE_STATUSES',
    'DEFAULT_REPORTS_DIR',
    'DEFAULT_DB_PATH',
    'MAC_DB_PATH',
    'CREDENTIAL_ENV_PREFIX',
    'BAD_VERSIONS',
    # Utils
    'get_mac_database',
    'get_vendor',
    'load_olt_credentials',
    'parse_input',
    'sanitize_ont_param',
    'is_online_status',
    'is_offline_status',
    # Threshold evaluator
    'evaluate_ont_rx_power',
    'evaluate_olt_rx_power',
    'evaluate_ont_temperature',
    'evaluate_cpu_temperature',
    'evaluate_distance',
    'evaluate_bip_errors',
    'is_bad_version',
    'should_skip_ping',
]