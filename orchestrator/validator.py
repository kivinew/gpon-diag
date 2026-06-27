# -*- coding: utf-8 -*-
"""
Validator — валидация структуры кода на соответствие AGENTS.md §3.5 и §4.

Проверяет:
  - sentinel-значения в OntMetrics (не заменять на None/0)
  - структуру правил (is_online guard, сигнатура)
  - консистентность DEFAULT_RULES / EXTENDED_RULES
  - наличие обязательных полей в файлах
"""

from __future__ import annotations

import logging
import os
import re
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


SENTINEL_RULES: Dict[str, Tuple[str, str, str]] = {
    "ont_rx_power": ("999.0", ">= 900", "if not metrics.ont_rx_power"),
    "olt_rx_power": ("999.0", ">= 900", "if not metrics.olt_rx_power"),
    "ont_tx_power": ("999.0", ">= 900", "if not metrics.ont_tx_power"),
    "distance_m": ("-1", "< 0", "if not metrics.distance_m"),
    "cpu_temp": ("-999", "<= -900", "if not metrics.cpu_temp"),
    "ont_temperature": ("-999", "<= -900", "if not metrics.ont_temperature"),
    "cpu_usage": ("-1", "< 0", "if not metrics.cpu_usage"),
    "memory_usage": ("-1", "< 0", "if not metrics.memory_usage"),
    "supply_voltage": ("-1.0", "< 0", "if not metrics.supply_voltage"),
}

ONLINE_GUARD_EXEMPT: Set[str] = {
    "offline", "rule_offline", "match_state", "rule_match_state",
    "config_state", "rule_config_state", "wan_disconnected", "rule_wan_disconnected",
    "frequent_falls", "rule_frequent_falls",
}



class SentinelValidator:
    """Проверка sentinel-значений в OntMetrics и правилах.

    Предотвращает замену sentinel-проверки на 'if not metrics.xxx'.
    """

    @staticmethod
    def check_engine_file(file_path: str) -> List[str]:
        """Проверить engine.py на неправильные sentinel-проверки."""
        errors: List[str] = []
        if not os.path.exists(file_path):
            return ["File not found"]

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        for field, (sentinel, good_pattern, bad_pattern) in SENTINEL_RULES.items():
            if re.search(re.escape(bad_pattern), content):
                errors.append(
                    f"Found: '{bad_pattern}' — BAD: use '{good_pattern}' "
                    f"(sentinel={sentinel}, 0 is valid)"
                )

        return errors

    @staticmethod
    def check_sentinel_defaults(models_path: str) -> List[str]:
        """Проверить, что sentinel-дефолты в OntMetrics не изменены."""
        errors: List[str] = []
        if not os.path.exists(models_path):
            return ["File not found"]

        with open(models_path, "r", encoding="utf-8") as f:
            content = f.read()

        expected_defaults = [
            "ont_rx_power: float = 999.0",
            "olt_rx_power: float = 999.0",
            "ont_tx_power: float = 999.0",
            "distance_m: int = -1",
            "cpu_temp: int = -999",
            "ont_temperature: int = -999",
            "cpu_usage: int = -1",
            "memory_usage: int = -1",
            "supply_voltage: float = -1.0",
        ]

        for expected in expected_defaults:
            if expected not in content:
                errors.append(f"Missing or changed sentinel default: '{expected}'")

        return errors



class RuleValidator:
    """Проверка структуры правил в engine.py."""

    @staticmethod
    def check_online_guard(file_path: str) -> List[str]:
        """Проверить, что online-правила имеют is_online guard."""
        errors: List[str] = []
        if not os.path.exists(file_path):
            return ["File not found"]

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        rule_funcs = re.findall(r"def (rule_\w+)\(metrics, t\):", content)

        for func_name in rule_funcs:
            if func_name in ONLINE_GUARD_EXEMPT:
                continue

            func_match = re.search(
                rf"def {func_name}\(metrics, t\):(.*?)(?=\ndef |\Z)",
                content,
                re.DOTALL,
            )
            if func_match:
                body = func_match.group(1)
                if "not metrics.is_online" not in body:
                    errors.append(
                        f"Rule '{func_name}' missing is_online guard"
                    )

        return errors

    @staticmethod
    def check_default_rules_order(file_path: str) -> List[str]:
        """Проверить, что DEFAULT_RULES содержат обязательные правила."""
        errors: List[str] = []
        if not os.path.exists(file_path):
            return ["File not found"]

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        required_rules = [
            "offline", "low_ont_rx", "low_olt_rx", "low_tx_power",
            "bip_errors", "bad_firmware", "no_lan", "overheating",
            "high_temperature", "low_voltage", "long_distance",
            "match_state", "config_state",
        ]

        for rule_name in required_rules:
            if not re.search(rf'Rule\("{rule_name}"', content):
                errors.append(f"Missing required rule: '{rule_name}'")

        return errors

    @staticmethod
    def check_categories(file_path: str) -> Dict[str, List[str]]:
        """Проверить покрытие категорий."""
        categories: Dict[str, List[str]] = {}
        if not os.path.exists(file_path):
            return {}

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        for rule_name, _, category in re.findall(
            r'Rule\("(\w+)",\s*(\w+),\s*"(\w+)"', content,
        ):
            categories.setdefault(category, []).append(rule_name)

        return categories

    @staticmethod
    def check_rule_signatures(file_path: str) -> List[str]:
        """Проверить сигнатуры правил (metrics, t)."""
        errors: List[str] = []
        if not os.path.exists(file_path):
            return ["File not found"]

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        for match in re.finditer(r"def (rule_\w+)\((.*?)\):", content):
            func_name = match.group(1)
            params = match.group(2).strip()
            if params not in ("metrics, t", "metrics, thresholds", "metrics, t: Thresholds"):
                errors.append(
                    f"Rule '{func_name}' signature ({params}) — expected (metrics, t)"
                )

        return errors


class StructureValidator:
    """Проверка общей структуры проекта."""

    REQUIRED_FILES: List[str] = [
        "core/__init__.py", "core/models.py", "core/parser.py",
        "core/engine.py", "core/thresholds.py", "core/report.py",
        "core/reporter.py", "core/olt.py",
        "diagnose.py", "config.yaml",
    ]

    REQUIRED_CLASSES: Dict[str, List[str]] = {
        "core/models.py": ["OntMetrics", "LanPort", "MacDevice"],
        "core/engine.py": ["Rule", "DiagnosticEngine"],
        "core/thresholds.py": ["Thresholds"],
        "core/report.py": ["DiagnosisProblem", "DiagnosisReport"],
        "core/olt.py": ["OltConnection"],
    }

    @classmethod
    def check_file_exists(cls, project_root: str) -> List[str]:
        missing = []
        for rel_path in cls.REQUIRED_FILES:
            if not os.path.exists(os.path.join(project_root, rel_path)):
                missing.append(rel_path)
        return missing

    @classmethod
    def check_classes_exist(cls, project_root: str) -> List[str]:
        errors = []
        for file_path, class_names in cls.REQUIRED_CLASSES.items():
            abs_path = os.path.join(project_root, file_path)
            if not os.path.exists(abs_path):
                errors.append(f"File '{file_path}' not found")
                continue
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
            for cls_name in class_names:
                if f"class {cls_name}" not in content:
                    errors.append(f"Missing class '{cls_name}' in '{file_path}'")
        return errors
