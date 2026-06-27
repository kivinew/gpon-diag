#!/usr/bin/env python3
"""
Rule Generator — анализирует отчеты и предлагает новые правила диагностики.

Использование:
    uv run rule_gen.py --analyze-reports --suggest-rules
"""

import json
import os
import re
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv(".env")
except ImportError:
    pass


def analyze_reports(reports_dir: str = "data/reports") -> list[dict]:
    """Анализирует JSON-отчеты и выявляет повторяющиеся паттерны проблем."""
    patterns = {}
    path = Path(reports_dir)
    
    if not path.exists():
        return []

    for report_file in path.glob("*.json"):
        try:
            with open(report_file, "r", encoding="utf-8") as f:
                report = json.load(f)
            
            metrics = report.get("metrics", {})
            problems = report.get("problems", [])
            
            # Анализируем каждую проблему
            for p in problems:
                key = f"{p.get('category')}:{p.get('severity')}"
                if key not in patterns:
                    patterns[key] = {"count": 0, "samples": []}
                patterns[key]["count"] += 1
                if len(patterns[key]["samples"]) < 3:
                    patterns[key]["samples"].append(p.get("message", "")[:100])
                    
        except Exception as e:
            continue

    return [{"code": k, "count": v["count"], "samples": v["samples"]} for k, v in patterns.items()]


def suggest_rules_from_patterns(patterns: list[dict]) -> list[str]:
    """Генерирует предложения правил на основе найденных паттернов."""
    suggestions = []

    for p in patterns:
        code, count = p["code"], p["count"]
        
        if count < 2:
            continue
            
        category, severity = code.split(":", 1)
        samples = p["samples"]
        
        suggestion = f"""
# Автопредложение: {category} (встречается {count} раз)
# Примеры: {samples[0][:50]}

def rule_auto_{category}(metrics, t):
    if not metrics.is_online:
        return None
    # TODO: реализовать проверку для {category}
    return None
"""
        suggestions.append(suggestion)

    return suggestions


def main():
    import argparse
    parser = argparse.ArgumentParser(description="GPON Rule Generator")
    parser.add_argument("--analyze-reports", action="store_true", help="Analyze reports in data/reports/")
    parser.add_argument("--suggest-rules", action="store_true", help="Output suggested rules")
    parser.add_argument("--reports-dir", default="data/reports", help="Reports directory")
    args = parser.parse_args()

    if args.analyze_reports:
        patterns = analyze_reports(args.reports_dir)
        print(f"Found {len(patterns)} problem patterns:")
        for p in sorted(patterns, key=lambda x: -x["count"]):
            print(f"  {p['code']}: {p['count']} occurrences")
            for s in p["samples"][:2]:
                print(f"    - {s}")

    if args.suggest_rules:
        patterns = analyze_reports(args.reports_dir)
        suggestions = suggest_rules_from_patterns(patterns)
        for s in suggestions:
            print(s)


if __name__ == "__main__":
    main()