#!/usr/bin/env python3
"""GPON Diagnostic Tool — CLI entry point.

Usage:
    uv run diagnose.py 0/1/3/9
    uv run diagnose.py 4857544312E0E379 --olt "OLT-17.232"
    uv run diagnose.py fl_12345 --clipboard
    uv run diagnose.py 0/1/3/9 --json --no-save
    uv run diagnose.py 0/1/3/9 --no-actions
    uv run diagnose.py 0/1/3/9 --only-optics
"""

import argparse
import json
import logging
import sys

from core.config_parser import load_config, _build_thresholds
from core.utils import parse_input
from core.diagnose_logic import run_diagnosis
from core.connection_diagnosis import find_available_olt, find_olt_parallel
from core.olt import OntNotFoundError, close_all
from core.reporter import save_text_report

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="GPON ONT Diagnostic Tool")
    parser.add_argument("input", nargs="?", default=None,
                        help="ONT address (F/S/P/ONT), serial, or description")
    parser.add_argument("--olt", help="OLT name or IP from config (default: auto-detect)")
    parser.add_argument("--auto-search", action="store_true",
                        help="Search across all OLTs in parallel (default: single OLT)")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    parser.add_argument("--no-save", action="store_true", help="Don't save report to file")
    parser.add_argument("--no-actions", action="store_true",
                        help="Full diagnostics without port resets and counter clears")
    parser.add_argument("--only-optics", action="store_true",
                        help="Only check optics (powers + BIP errors)")
    parser.add_argument("--ssh", action="store_true",
                        help="Use SSH instead of telnet for connection")
    args = parser.parse_args()

    if args.input is None:
        try:
            args.input = input("ONT (адрес F/S/P/ONT, серийный номер или описание): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        input_data = parse_input(args.input)
    except ValueError as e:
        print(f"Error: Invalid input format - {e}", file=sys.stderr)
        sys.exit(1)

    olt_config = None
    if args.auto_search:
        # Parallel search across all OLTs
        try:
            olt_config, input_data = find_olt_parallel(config, input_data)
        except OntNotFoundError as e:
            print(f"Ошибка: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.olt:
        for olt in config.get("olts", []):
            if olt.get("name") == args.olt or olt.get("host") == args.olt:
                olt_config = olt
                break
        if not olt_config:
            print(f"Error: OLT '{args.olt}' not found in config.", file=sys.stderr)
            sys.exit(1)
    else:
        olt_config = find_available_olt(config)
        if not olt_config:
            print("Error: No OLT available. Set --olt or check .env credentials.", file=sys.stderr)
            sys.exit(1)
        print(f"Using OLT: {olt_config.get('name', olt_config['host'])}")

    thresholds = _build_thresholds(config)

    try:
        report = run_diagnosis(input_data, olt_config, thresholds,
                               allow_actions=not args.no_actions,
                               ping_target=config.get("ping_target", "1.1.1.1"),
                               use_ssh=args.ssh)
    except OntNotFoundError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.exception("Diagnosis failed")
        print(f"Error: Diagnosis failed - {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        close_all()

    if args.json:
        output = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
    else:
        output = report.to_text()

    print(output)

    try:
        import pyperclip
        pyperclip.copy(output)
        print("\n[Copied to clipboard]")
    except ImportError:
        pass  # pyperclip not installed — clipboard copy skipped
    except Exception as e:
        logger.warning("Clipboard copy failed: %s", e)

    if not args.no_save:
        try:
            filepath = save_text_report(report, config.get("report", {}).get("reports_dir", "data/reports"))
            print(f"[Report saved: {filepath}]")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")


if __name__ == "__main__":
    main()