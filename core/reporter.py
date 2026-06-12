"""Reporter — formats and saves diagnosis reports."""

import json
import logging
import os
from datetime import datetime
from core.report import DiagnosisReport

logger = logging.getLogger(__name__)


def save_report(report: DiagnosisReport, reports_dir: str = "data/reports") -> str:
    try:
        os.makedirs(reports_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ont_safe = report.metrics.address.replace("/", "_")
        filename = f"{timestamp}_{ont_safe}.json"
        filepath = os.path.join(reports_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"Report saved: {filepath}")
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
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report.to_text())
            f.write(f"\n\n---\nSaved: {datetime.now().isoformat()}\n")
        logger.info(f"Report saved: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Failed to save report: {e}")
        raise
