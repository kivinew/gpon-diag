"""Reporter — formats and saves diagnosis reports."""

import importlib.util
import json
import logging
import os
from datetime import datetime
from core.report import DiagnosisReport

logger = logging.getLogger(__name__)


def _get_lock_functions():
    """Lazy-load file_lock functions to avoid import issues."""
    _spec = importlib.util.spec_from_file_location("file_lock", "hermes-lockutils/file_lock.py")
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    return _mod.lock_file, _mod.unlock_file


def save_report(report: DiagnosisReport, reports_dir: str = "data/reports") -> str:
    try:
        os.makedirs(reports_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ont_safe = report.metrics.address.replace("/", "_")
        filename = f"{timestamp}_{ont_safe}.json"
        filepath = os.path.join(reports_dir, filename)
        lock_file, unlock_file = _get_lock_functions()
        lock_file(reports_dir)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
            logger.info(f"Report saved: {filepath}")
        finally:
            unlock_file(reports_dir)
        return filepath
    except Exception as e:
        logger.error(f"Failed to save report: {e}")
        raise


def save_text_report(report: DiagnosisReport, reports_dir: str = "data/reports") -> str:
    try:
        os.makedirs(reports_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ont_safe = report.metrics.address.replace("/", "_")
        filename = f"{timestamp}_{ont_safe}.txt"
        filepath = os.path.join(reports_dir, filename)
        lock_file, unlock_file = _get_lock_functions()
        lock_file(reports_dir)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(report.to_text())
                f.write(f"\n\n---\nSaved: {datetime.now().isoformat()}\n")
            logger.info(f"Report saved: {filepath}")
        finally:
            unlock_file(reports_dir)
        return filepath
    except Exception as e:
        logger.error(f"Failed to save report: {e}")
        raise
