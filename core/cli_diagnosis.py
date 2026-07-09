#!/usr/bin/env python3
"""GPON Diagnostic Tool — CLI entry point.

Usage:
    uv run diagnose.py 0/1/3/9
    uv run diagnose.py 4857544312E0E379 --olt "OLT-17.232"
    uv run diagnose.py fl_12345 --clipboard
    uv run diagnose.py 0/1/3/9 --json --no-save
    uv run diagnose.py 0/1/3/9 --no-actions
    uv run diagnose.py 0/1/3/9 --only-optics
    uv run diagnose.py --batch onts.csv --olt "OLT-17.232"
"""

import argparse
import csv
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core.config_parser import load_config, _build_thresholds
from core.utils import parse_input
from core.diagnose_logic import run_diagnosis
from core.connection_diagnosis import find_available_olt, find_olt_parallel
from core.olt import OntNotFoundError, close_all
from core.reporter import save_text_report

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def run_single_diagnosis(input_data, olt_config, thresholds, allow_actions, ping_target, use_ssh):
    """Run diagnosis for a single ONT and return result tuple."""
    try:
        report = run_diagnosis(input_data, olt_config, thresholds,
                               allow_actions=allow_actions,
                               ping_target=ping_target,
                               use_ssh=use_ssh)
        return True, report, None
    except OntNotFoundError as e:
        return False, None, str(e)
    except Exception as e:
        logger.exception("Diagnosis failed")
        return False, None, str(e)


def process_batch_file(batch_file: str, olt_config, thresholds, allow_actions, ping_target, use_ssh, max_workers: int = 4):
    """Process a batch CSV file with ONT addresses."""
    results = []
    
    with open(batch_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        # Support columns: address, olt_host (optional), or just address
        rows = list(reader)
    
    if not rows:
        print("Batch file is empty", file=sys.stderr)
        return results
    
    # Check required column
    if 'address' not in rows[0]:
        print("Error: CSV must have 'address' column", file=sys.stderr)
        return results
    
    print(f"Processing {len(rows)} ONTs from {batch_file}...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_row = {}
        for i, row in enumerate(rows):
            address = row['address'].strip()
            if not address:
                continue
            
            # Per-row OLT override
            row_olt = olt_config
            if 'olt_host' in row and row['olt_host'].strip():
                # Find OLT by host
                config = load_config("config.yaml")
                for olt in config.get("olts", []):
                    if olt.get("host") == row['olt_host'].strip():
                        row_olt = olt
                        break
            
            try:
                input_data = parse_input(address)
            except ValueError as e:
                results.append({
                    'address': address,
                    'success': False,
                    'error': f"Invalid input: {e}",
                    'report': None
                })
                continue
            
            future = executor.submit(
                run_single_diagnosis,
                input_data, row_olt, thresholds, allow_actions, ping_target, use_ssh
            )
            future_to_row[future] = (i, address, row)
        
        # Collect results as they complete
        for future in as_completed(future_to_row):
            i, address, row = future_to_row[future]
            try:
                success, report, error = future.result()
                results.append({
                    'address': address,
                    'success': success,
                    'error': error,
                    'report': report
                })
                
                if success:
                    status = "OK" if not report.has_problems else f"{len(report.problems)} problems"
                    print(f"  [{i+1}/{len(rows)}] {address}: {status}")
                else:
                    print(f"  [{i+1}/{len(rows)}] {address}: FAILED - {error}")
            except Exception as e:
                results.append({
                    'address': address,
                    'success': False,
                    'error': str(e),
                    'report': None
                })
                print(f"  [{i+1}/{len(rows)}] {address}: FAILED - {e}")
    
    return results


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
                        help="Only check optics (Rx/Tx, BIP errors)")
    parser.add_argument("--ssh", action="store_true",
                        help="Use SSH instead of telnet for connection")
    parser.add_argument("--batch", help="Batch diagnosis from CSV file (columns: address, olt_host)")
    parser.add_argument("--batch-workers", type=int, default=4, help="Max parallel workers for batch (default: 4)")
    args = parser.parse_args()

    if args.input is None and args.batch is None:
        try:
            args.input = input("ONT (адрес F/S/P/ONT, серийный номер или описание): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)

    if args.batch and args.input:
        print("Error: Cannot use both positional input and --batch", file=sys.stderr)
        sys.exit(1)

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Batch mode
    if args.batch:
        thresholds = _build_thresholds(config)
        
        # Determine OLT for batch
        olt_config = None
        if args.olt:
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
                print("Error: No OLT available for batch. Use --olt or check .env credentials.", file=sys.stderr)
                sys.exit(1)
        
        print(f"Using OLT: {olt_config.get('name', olt_config['host'])}")
        
        results = process_batch_file(
            args.batch, olt_config, thresholds,
            allow_actions=not args.no_actions,
            ping_target=config.get("ping_target", "1.1.1.1"),
            use_ssh=args.ssh,
            max_workers=args.batch_workers
        )
        
        # Summary
        success_count = sum(1 for r in results if r['success'])
        fail_count = len(results) - success_count
        print(f"\n=== Batch Summary ===")
        print(f"Total: {len(results)}, Success: {success_count}, Failed: {fail_count}")
        
        # Save reports
        if not args.no_save:
            for r in results:
                if r['success'] and r['report']:
                    try:
                        filepath = save_text_report(r['report'], config.get("report", {}).get("reports_dir", "data/reports"))
                        print(f"  Report saved: {filepath}")
                    except Exception as e:
                        logger.error(f"Failed to save report for {r['address']}: {e}")
        
        if args.json:
            output = {
                'results': [
                    {
                        'address': r['address'],
                        'success': r['success'],
                        'error': r['error'],
                        'report': r['report'].to_dict() if r['success'] and r['report'] else None
                    }
                    for r in results
                ],
                'summary': {
                    'total': len(results),
                    'success': success_count,
                    'failed': fail_count
                }
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
        
        sys.exit(0 if fail_count == 0 else 1)

    # Single ONT mode (existing logic)
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