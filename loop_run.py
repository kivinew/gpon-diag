#!/usr/bin/env python3
"""
Loop Runner CLI — циклическая обработка задач диагностики.

Примеры:
    # Диагностика списка ONT из файла
    uv run loop_run.py --file onts.txt --olt "OLT-17.232" --loops 50

    # Диагностика из CSV
    uv run loop_run.py --csv subscribers.csv --olt "OLT-40.111" --column address

    # Показать статус очереди
    uv run loop_run.py --status

    # Продолжить прерванную очередь
    uv run loop_run.py --resume --loops 20
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(".env")
except ImportError:
    pass

from core.loop_runner import (
    LoopRunner,
    LoopTask,
    create_diagnose_tasks,
    load_onts_from_csv,
    load_onts_from_file,
)


def main():
    parser = argparse.ArgumentParser(description="GPON Loop Runner — cyclic batch diagnosis")
    parser.add_argument("--file", "-f", help="Text file with ONT list (one per line)")
    parser.add_argument("--csv", help="CSV file with ONT list")
    parser.add_argument("--column", default="ont", help="CSV column name (default: ont)")
    parser.add_argument("--ont", action="append", help="Single ONT (can repeat)")
    parser.add_argument("--olt", help="OLT name from config.yaml (default: auto-detect)")
    parser.add_argument("--auto-olt", action="store_true", help="Auto-detect OLT for each task (default if --olt not set)")
    parser.add_argument("--loops", "-n", type=int, default=10, help="Max loop iterations (default: 10)")
    parser.add_argument("--no-actions", action="store_true", help="Diagnostics without resets/clears")
    parser.add_argument("--queue", default="data/loop_tasks.json", help="Task queue file")
    parser.add_argument("--status", action="store_true", help="Show queue status and exit")
    parser.add_argument("--resume", action="store_true", help="Resume existing queue")
    parser.add_argument("--clear", action="store_true", help="Clear queue before adding tasks")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    workdir = Path.cwd()
    queue_path = workdir / args.queue

    # Initialize runner
    runner = LoopRunner(
        max_loops=args.loops,
        queue_path=str(queue_path),
        diagnose_script="diagnose.py",
        workdir=str(workdir),
    )

    # Show status and exit
    if args.status:
        stats = runner.queue.stats()
        print(json.dumps(stats, indent=2) if args.json else f"Queue: {stats}")
        if stats["total"] > 0:
            print("\nTasks:")
            for t in runner.queue.tasks:
                prefix = {"pending": "○", "running": "◐", "done": "✓", "failed": "✗"}.get(t.status, "?")
                print(f"  {prefix} {t.id} [{t.status}] {t.type}")
        return

    # Clear queue if requested
    if args.clear and queue_path.exists():
        queue_path.unlink()
        runner.queue.tasks = []
        runner.queue.save()
        print(f"Cleared queue: {queue_path}")

    # Add tasks if not resuming
    if not args.resume:
        onts = []

        if args.file:
            onts.extend(load_onts_from_file(args.file))
        if args.csv:
            onts.extend(load_onts_from_csv(args.csv, args.column))
        if args.ont:
            onts.extend(args.ont)

        if not onts:
            print("Error: No ONTs specified. Use --file, --csv, or --ont", file=sys.stderr)
            sys.exit(1)

        print(f"Loaded {len(onts)} ONTs")
        tasks = create_diagnose_tasks(onts, olt=args.olt or "", no_actions=args.no_actions)
        runner.add_tasks(tasks)
        print(f"Added {len(tasks)} tasks to queue")

    # Run loop
    stats = runner.run()

    if args.json:
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()