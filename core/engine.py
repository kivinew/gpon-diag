"""Diagnostic engine — rule-based ONT diagnosis."""

import logging
from core.models import OntMetrics
from core.report import DiagnosisProblem
from core.thresholds import Thresholds

logger = logging.getLogger(__name__)


class Rule:
    def __init__(self, name, check_fn, category=""):
        self.name = name
        self.check_fn = check_fn
        self.category = category or "general"

    def check(self, metrics, thresholds):
        return self.check_fn(metrics, thresholds)


class DiagnosticEngine:
    def __init__(self, thresholds: Thresholds):
        self.thresholds = thresholds
        self._rules = []

    def add_rule(self, rule: Rule) -> None:
        self._rules.append(rule)

    def add_rules(self, rules) -> None:
        self._rules.extend(rules)

    def diagnose(self, metrics: OntMetrics) -> list:
        problems = []
        for rule in self._rules:
            try:
                result = rule.check(metrics, self.thresholds)
                if result:
                    if isinstance(result, list):
                        problems.extend(result)
                    else:
                        problems.append(result)
            except Exception as e:
                logger.warning(f"Rule '{rule.name}' failed: {e}")
        return sorted(problems, key=lambda p: p.sort_key)


# ── Rules ──

def rule_offline(metrics, t):
    if metrics.is_online:
        return None
    cause = metrics.last_down_cause.lower() if metrics.last_down_cause else ""
    if not cause or cause == "-":
        return DiagnosisProblem("critical", "unknown", "ONT offline, cause unknown", "Необходимо проверить оптическую линию и подключение ONT вручную")
    if "los" in cause or "losi" in cause or "lobi" in cause:
        return DiagnosisProblem("critical", "optic", f"Loss of signal: {metrics.last_down_cause}", "Необходимо проверить оптическую линию — возможно отключение волокна или повреждение кабеля")
    if "lofi" in cause:
        return DiagnosisProblem("warning", "optic", f"Low signal: {metrics.last_down_cause}", "Необходимо проверить оптическую линию — снижение уровня сигнала")
    if "wire-down" in cause:
        return DiagnosisProblem("critical", "optic", f"Wire-down: {metrics.last_down_cause}", "Необходимо проверить магистральный кабель — возможна массовая проблема")
    if "dying-gasp" in cause:
        return DiagnosisProblem("critical", "power", f"Power loss: {metrics.last_down_cause}", "Необходимо проверить электропитание терминала, исправность БП.")
    if "loki" in cause:
        return DiagnosisProblem("warning", "optic", f"Loss of key: {metrics.last_down_cause}", "ONT lost authentication key — re-registration may be needed")
    return DiagnosisProblem("warning", "config", f"Offline: {metrics.last_down_cause}", "Уточнить причину отключения, проверить лог на OLT")


def rule_low_ont_rx(metrics, t):
    if not metrics.is_online or metrics.ont_rx_power >= 900:
        return None
    if metrics.ont_rx_power < t.ont_rx_power_crit:
        return DiagnosisProblem("critical", "optic", f"Критически низкий ONT Rx: {metrics.ont_rx_power} dBm",
            "Проверить оптическую линию — возможно отключение или повреждение кабеля")
    if metrics.ont_rx_power < t.ont_rx_power_warn:
        return DiagnosisProblem("warning", "optic", f"Низкий ONT Rx: {metrics.ont_rx_power} dBm",
            "Низкий уровень оптического сигнала, необходима проверка оптической линии.")
    return None


def rule_low_olt_rx(metrics, t):
    if not metrics.is_online or metrics.olt_rx_power >= 900:
        return None
    if metrics.olt_rx_power < t.olt_rx_power_crit:
        return DiagnosisProblem("critical", "optic", f"Критически низкий OLT Rx: {metrics.olt_rx_power} dBm", "Необходимо проверить лазер терминала, оптическую линию")
    if metrics.olt_rx_power < t.olt_rx_power_warn:
        return DiagnosisProblem("warning", "optic", f"Низкий OLT Rx: {metrics.olt_rx_power} dBm", "Возможна деградация линии или оптического терминала")
    return None


def rule_bip_errors(metrics, t):
    if not metrics.is_online:
        return None
    total = metrics.total_bip_errors
    if total == 0:
        return None
    if total >= t.bip_error_crit:
        return DiagnosisProblem("critical", "optic", f"Критические ошибки оптики: Up={metrics.upstream_errors}, Down={metrics.downstream_errors}", "Проверить чистоту коннекторов, затухание линии")
    if total >= t.bip_error_warn:
        return DiagnosisProblem("warning", "optic", f"Ошибки оптики: Up={metrics.upstream_errors}, Down={metrics.downstream_errors}", "Мониторинг рекомендуется — проверить линию при ухудшении")
    return None


def rule_bad_firmware(metrics, t):
    if not metrics.is_online or not metrics.version:
        return None
    if metrics.version.upper() in [v.upper() for v in t.bad_versions]:
        return DiagnosisProblem("warning", "firmware", f"Устаревшее ПО: {metrics.version}", "Необходимо обновление ПО терминала")
    return None


def rule_no_lan(metrics, t):
    if not metrics.is_online:
        return None
    if not metrics.has_lan_activity and metrics.lan_ports:
        return DiagnosisProblem("warning", "ethernet", "Нет активных LAN-портов", "Проверить кабель Ethernet, подключение устройства абонента")
    return None


def rule_overheating(metrics, t):
    if not metrics.is_online or metrics.cpu_temp < -900:
        return None
    if metrics.cpu_temp >= t.cpu_temp_crit:
        return DiagnosisProblem("critical", "hardware", f"Перегрев ONT: {metrics.cpu_temp}°C", "Проверить вентиляцию, расположение терминала")
    if metrics.cpu_temp >= t.cpu_temp_warn:
        return DiagnosisProblem("warning", "hardware", f"Повышенная температура: {metrics.cpu_temp}°C", "Рекомендуется проверить условия размещения")
    return None


def rule_long_distance(metrics, t):
    # Guard: выполнять только для online‑ONT
    if not metrics.is_online:
        return None
    if metrics.distance_m < 0:
        return None
    if metrics.distance_m >= t.distance_crit:
        return DiagnosisProblem("warning", "optic", f"Критическое расстояние: {metrics.distance_m} м (предел 20000 м)", "Проверить оптический бюджет")
    return None


def rule_match_state(metrics, t):
    return None


def rule_config_state(metrics, t):
    if not metrics.is_online:
        return None
    if not metrics.config_state:
        return None
    if metrics.config_state.lower() != "normal":
        return DiagnosisProblem("warning", "config",
            f"Config state: {metrics.config_state}",
            "Конфигурация ONT не применена — проверить совместимость профиля")
    return None


def rule_low_tx_power(metrics, t):
    """Check for low/abnormal Tx power from ONT."""
    if not metrics.is_online or metrics.ont_tx_power >= 900:
        return None
    if metrics.ont_tx_power < 0.0:
        return DiagnosisProblem("critical", "optic",
            f"Критически низкий ONT Tx: {metrics.ont_tx_power} dBm",
            "Лазер ONT деградирует — рекомендуется замена терминала")
    if metrics.ont_tx_power < 1.0:
        return DiagnosisProblem("warning", "optic",
            f"Низкий ONT Tx: {metrics.ont_tx_power} dBm",
            "Снижение мощности передатчика — мониторинг или замена")
    return None


def rule_high_temperature(metrics, t):
    """Check temperature from optical-info (more precise than CPU temp)."""
    if not metrics.is_online or metrics.ont_temperature <= -900:
        return None
    if metrics.ont_temperature >= 75:
        return DiagnosisProblem("critical", "hardware",
            f"Критическая температура: {metrics.ont_temperature}°C",
            "Перегрев терминала — проверить вентиляцию, условия размещения")
    if metrics.ont_temperature >= 65:
        return DiagnosisProblem("warning", "hardware",
            f"Повышенная температура: {metrics.ont_temperature}°C",
            "Рекомендуется проверить условия размещения терминала")
    return None


def rule_low_voltage(metrics, t):
    """Check supply voltage — below 3.0V is critical."""
    if not metrics.is_online or metrics.supply_voltage < 0 or metrics.supply_voltage >= 900:
        return None
    if metrics.supply_voltage < 3.0:
        return DiagnosisProblem("critical", "hardware",
            f"Низкое напряжение питания: {metrics.supply_voltage}V (норма 3.0-3.6V)",
            "Проблема с БП или кабелем питания — проверить источник")
    if metrics.supply_voltage > 3.6:
        return DiagnosisProblem("warning", "hardware",
            f"Высокое напряжение питания: {metrics.supply_voltage}V (норма 3.0-3.6V)",
            "Превышение напряжения — проверить БП")
    return None

# --------------------------------------------------------
# New rule: temperature check (ONT optical temperature)
def rule_ont_temperature(metrics, t):
    """Check ONT temperature from optical‑info.
    Uses thresholds ont_temperature_warn / ont_temperature_crit.
    """
    if not metrics.is_online or metrics.ont_temperature <= -900:
        return None
    if metrics.ont_temperature >= t.ont_temperature_crit:
        return DiagnosisProblem(
            "critical", "hardware",
            f"Критическая температура ONT: {metrics.ont_temperature}°C",
            "Перегрев терминала — проверить вентиляцию и условия размещения"
        )
    if metrics.ont_temperature >= t.ont_temperature_warn:
        return DiagnosisProblem(
            "warning", "hardware",
            f"Повышенная температура ONT: {metrics.ont_temperature}°C",
            "Рекомендуется проверить условия размещения терминала"
        )
    return None


DEFAULT_RULES = [
    Rule("offline", rule_offline, "optic"),
    Rule("low_ont_rx", rule_low_ont_rx, "optic"),
    Rule("low_olt_rx", rule_low_olt_rx, "optic"),
    Rule("low_tx_power", rule_low_tx_power, "optic"),
    Rule("bip_errors", rule_bip_errors, "optic"),
    Rule("bad_firmware", rule_bad_firmware, "firmware"),
    Rule("no_lan", rule_no_lan, "ethernet"),
    Rule("overheating", rule_overheating, "hardware"),
    Rule("high_temperature", rule_high_temperature, "hardware"),
    Rule("low_voltage", rule_low_voltage, "hardware"),
    Rule("low_voltage", rule_low_voltage, "hardware"),
    Rule("ont_temperature", rule_ont_temperature, "hardware"),
    Rule("long_distance", rule_long_distance, "optic"),
    Rule("match_state", rule_match_state, "config"),
    Rule("config_state", rule_config_state, "config"),
]


def create_default_engine(thresholds: Thresholds) -> DiagnosticEngine:
    engine = DiagnosticEngine(thresholds)
    engine.add_rules(DEFAULT_RULES)
    return engine


def rule_wan_disconnected(metrics, t):
    """Check for disconnected WAN connections."""
    if not metrics.is_online:
        return None
    problems = []
    if not hasattr(metrics, 'wan_connections') or not metrics.wan_connections:
        return None
    for conn in metrics.wan_connections:
        status = conn.get('ipv4_connection_status', '').lower()
        if status in ('disconnected', 'connecting', 'failed'):
            idx = conn.get('index', '?')
            svc = conn.get('service_type', 'Unknown')
            problems.append(DiagnosisProblem(
                "warning", "wan",
                f"WAN #{idx} ({svc}): статус {status}",
                f"Проверить #{idx} WAN-соединение ({svc})"
            ))
    return problems if problems else None


def rule_lan_no_link(metrics, t):
    """Check for LAN ports without link."""
    if not metrics.is_online or not metrics.lan_ports:
        return None
    down_ports = [p for p in metrics.lan_ports if p.link_state != 'up']
    if down_ports and len(down_ports) == len(metrics.lan_ports):
        return DiagnosisProblem(
            "info", "ethernet",
            "Нет активных LAN-портов",
            "Проверить кабель Ethernet, подключение устройства абонента"
        )
    return None


def rule_high_cpu(metrics, t):
    """Check for high CPU usage."""
    if not metrics.is_online or metrics.cpu_usage < 0:
        return None
    if metrics.cpu_usage >= t.cpu_usage_warn:
        return DiagnosisProblem(
            "warning", "hardware",
            f"Высокая загрузка CPU: {metrics.cpu_usage}%",
            "Проверить состояние терминала, возможен перегрев"
        )
    return None


def rule_high_memory(metrics, t):
    """Check for high memory usage."""
    if not metrics.is_online or metrics.memory_usage < 0:
        return None
    if metrics.memory_usage >= t.memory_usage_warn:
        return DiagnosisProblem(
            "warning", "hardware",
            f"Высокая загрузка памяти: {metrics.memory_usage}%",
            "Проверить состояние терминала, рекомендуется перезагрузка"
        )
    return None


def rule_no_description(metrics, t):
    """Check for missing description on online ONTs."""
    if not metrics.is_online:
        return None
    if metrics.description == "ONT_NO_DESCRIPTION":
        return DiagnosisProblem(
            "warning", "accounting",
            "Дескрипшн (лицевой счёт) не установлен",
            "Установить ЛС абонента и исправить дескрипшен"
        )
    return None


def rule_frequent_falls(metrics, t):
    """Check if ONT falls frequently (2+ times within 1 hour)."""
    if not metrics.is_online:
        return None
    if not hasattr(metrics, 'register_all_downtimes') or not metrics.register_all_downtimes:
        return None
    import datetime as _dt
    now = _dt.datetime.now()
    recent = []
    for d in metrics.register_all_downtimes:
        try:
            dt = _dt.datetime.strptime(d, "%Y-%m-%d %H:%M:%S%z").replace(tzinfo=None)
            if (now - dt).total_seconds() <= 3600:
                recent.append(dt)
        except ValueError:
            pass
    if len(recent) >= 2:
        return DiagnosisProblem(
            "critical", "stability",
            f"Частые отключения ONT: {len(recent)} раз за последний час",
            "Проверить стабильность питания и оптической линии — возможна проблема с кабелем или БП"
        )
    return None


def rule_eth_port_errors(metrics, t):
    """Check for errors on ports with active links."""
    if not metrics.is_online or not metrics.eth_errors:
        return None
    problems = []
    for port in metrics.lan_ports:
        if port.link_state != "up":
            continue
        errs = metrics.eth_errors.get(port.lan_id, {})
        fcs = errs.get("fcs", 0)
        rx_bad = errs.get("received_bad_bytes", 0)
        tx_bad = errs.get("sent_bad_bytes", 0)
        total = fcs + rx_bad + tx_bad
        if total > 0:
            problems.append(DiagnosisProblem(
                "warning", "ethernet",
                f"LAN{port.lan_id}: ошибки — FCS={fcs}, RX bad={rx_bad}, TX bad={tx_bad}",
                f"Проверить кабель Ethernet LAN{port.lan_id}, разъём, порт абонентского устройства"
            ))
    return problems if problems else None


def rule_long_uptime(metrics, t):
    """Recommend reboot if uptime > 5 days."""
    if not metrics.is_online or not metrics.online_duration or metrics.online_duration == "-":
        return None
    import re as _re
    m = _re.search(r"(\d+)\s*day", metrics.online_duration)
    if m and int(m.group(1)) >= 5:
        return DiagnosisProblem(
            "info", "maintenance",
            f"Длительная работа без перезагрузки: {metrics.online_duration}",
            "Необходима перезагрузка терминала."
        )
    return None


# Extended ruleset including new rules
EXTENDED_RULES = DEFAULT_RULES + [
    Rule("wan_disconnected", rule_wan_disconnected, "wan"),
    Rule("lan_no_link", rule_lan_no_link, "ethernet"),
    Rule("high_cpu", rule_high_cpu, "hardware"),
    Rule("high_memory", rule_high_memory, "hardware"),
    Rule("no_description", rule_no_description, "accounting"),
    Rule("frequent_falls", rule_frequent_falls, "stability"),
    Rule("eth_port_errors", rule_eth_port_errors, "ethernet"),
    Rule("long_uptime", rule_long_uptime, "maintenance"),
]


def create_extended_engine(thresholds: Thresholds) -> DiagnosticEngine:
    """Factory — engine with all rules including WAN/LAN diagnostics."""
    engine = DiagnosticEngine(thresholds)
    engine.add_rules(EXTENDED_RULES)
    return engine
