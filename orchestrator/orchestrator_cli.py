#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Orchestrator CLI — передача задач ИИ-агентам через CLI.

Использование:
1. Запуск задачи:
   uv run orchestrator/orchestrator_cli.py --execute my_agent --zone parser --description "Fix regex" --files core/parser.py

2. Получение задач (polling):
   uv run orchestrator/orchestrator_cli.py --poll my_agent --zone parser --orchestrator-url http://host:5000

3. Отчёт о выполнении:
   uv run orchestrator/orchestrator_cli.py --complete Txxxxx --agent my_agent --success true
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import List

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from orchestrator.agent_registry import AgentRegistry, AgentStatus, ZONE_FILE_MAP
from orchestrator.task_card import create_task_card, load_task_card, TaskStatus, list_task_cards
from orchestrator.outer_loop import (
    OuterLoopController,
    TaskSpec,
    ValidationLevel,
    create_outer_loop_controller,
)

logger = logging.getLogger(__name__)


def cmd_execute(args: argparse.Namespace) -> int:
    """Создать и сразу выполнить задачу."""
    registry = AgentRegistry()

    # Check zone
    zone = args.zone
    if zone not in ZONE_FILE_MAP:
        print(f"Unknown zone '{zone}'. Available: {list(ZONE_FILE_MAP.keys())}")
        return 1

    # Register agent
    try:
        registry.register(
            agent_id=args.agent_id,
            zone=zone,
            files_intended=args.files or ZONE_FILE_MAP[zone],
            metadata={"description": args.description},
        )
    except ValueError as e:
        print(f"Agent registration warning: {e}")

    registry.set_status(args.agent_id, AgentStatus.ACTIVE)

    # Create task
    task_id = f"T{time.strftime('%Y%m%d%H%M%S')}"

    # Create task card
    card = create_task_card(
        title=args.title or args.description[:50],
        description=args.description,
        zone=zone,
        verification_criteria=args.criteria or ["check_code"],
        metadata={"files_intended": args.files or ZONE_FILE_MAP[zone]},
    )

    print(f"Task created: {card.task_id}")
    print(f"Zone: {zone}")
    print(f"Files: {args.files or ZONE_FILE_MAP[zone]}")
    print(f"Status: {card.status.value}")
    print()
    print("Task JSON:")
    print(json.dumps({
        "task_id": card.task_id,
        "zone": zone,
        "description": args.description,
        "files": args.files or ZONE_FILE_MAP[zone],
    }, indent=2, ensure_ascii=False))

    # Output task for agent to consume (can be piped to another process)
    if args.output:
        print(f"\nTask output written to: {args.output}")
        # Caller can read and process this file

    return 0


def cmd_poll(args: argparse.Namespace) -> int:
    """Опрос задач (для внешних агентов)."""
    import requests

    poll_interval = args.poll_interval
    orchestrator_url = args.orchestrator_url

    print(f"Polling agent '{args.agent_id}' for zone '{args.zone}' from {orchestrator_url}")

    while True:
        try:
            resp = requests.post(
                f"{orchestrator_url}/orchestrator/api/agent/tasks",
                json={"agent_id": args.agent_id, "zone": args.zone},
                timeout=30,
            )
            if resp.status_code == 200:
                tasks = resp.json().get("tasks", [])
                if tasks:
                    for task in tasks:
                        print(json.dumps(task, ensure_ascii=False))

                        # Mark as started
                        requests.post(
                            f"{orchestrator_url}/orchestrator/api/agent/complete",
                            json={"task_id": task["task_id"], "agent_id": args.agent_id},
                            timeout=30,
                        )
                else:
                    print("No tasks")

                # Heartbeat
                requests.post(
                    f"{orchestrator_url}/orchestrator/api/agent/heartbeat",
                    json={"agent_id": args.agent_id, "status": "idle"},
                    timeout=30,
                )

        except Exception as e:
            print(f"Error: {e}")

        if args.single_run:
            break

        time.sleep(poll_interval)

    return 0


def cmd_complete(args: argparse.Namespace) -> int:
    """Отчёт о выполнении задачи."""
    import requests

    registry = AgentRegistry()

    # Load and update task card
    card = load_task_card(args.task_id)
    if not card:
        print(f"Task {args.task_id} not found")
        return 1

    card.status = TaskStatus.VALIDATION_PENDING
    card.result = {"output": args.output, "success": args.success}
    card.save()

    if args.orchestrator_url:
        requests.post(
            f"{args.orchestrator_url}/orchestrator/api/agent/result",
            json={
                "task_id": args.task_id,
                "agent_id": args.agent_id,
                "success": args.success,
                "output": args.output,
                "errors": args.errors or [],
            },
            timeout=30,
        )

    registry.set_status(args.agent_id, AgentStatus.COMPLETED if args.success else AgentStatus.ERROR)
    print(f"Task {args.task_id} marked as {'completed' if args.success else 'failed'}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Запустить внешний цикл + валидацию."""
    controller = create_outer_loop_controller(PROJECT_ROOT)

    spec = TaskSpec(
        task_id=args.task_id or f"T{int(time.time())}",
        zone=args.zone,
        description=args.description,
        files_intended=args.files.split(",") if args.files else ZONE_FILE_MAP.get(args.zone, []),
        validation_level=ValidationLevel[args.level.upper()] if args.level else ValidationLevel.STRICT,
        max_retries=args.retries,
    )

    controller.register_task(spec)
    result = controller.run_task(spec.task_id)

    print(f"Validation: {'PASSED' if result.passed else 'FAILED'}")
    if result.errors:
        for err in result.errors:
            print(f"  ERROR: {err}")
    if result.warnings:
        for warn in result.warnings:
            print(f"  WARNING: {warn}")

    return 0 if result.passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Orchestrator CLI for agent task management"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # execute: create and output task
    p_exec = subparsers.add_parser("execute", help="Create and execute a task")
    p_exec.add_argument("--agent-id", required=True, help="Agent ID")
    p_exec.add_argument("--zone", required=True, help="Zone (parser, engine, model, etc)")
    p_exec.add_argument("--title", help="Task title")
    p_exec.add_argument("--description", required=True, help="Task description")
    p_exec.add_argument("--files", nargs="*", help="Files to modify")
    p_exec.add_argument("--criteria", nargs="*", help="Verification criteria")
    p_exec.add_argument("--output", help="Output file for task JSON")
    p_exec.add_argument("--orchestrator-url", default="http://localhost:5000", help="Orchestrator URL")

    # poll: poll for tasks
    p_poll = subparsers.add_parser("poll", help="Poll for tasks")
    p_poll.add_argument("--agent-id", required=True, help="Agent ID")
    p_poll.add_argument("--zone", required=True, help="Zone to poll tasks for")
    p_poll.add_argument("--orchestrator-url", required=True, help="Orchestrator URL")
    p_poll.add_argument("--poll-interval", type=int, default=5, help="Poll interval")
    p_poll.add_argument("--single-run", action="store_true", help="Single poll then exit")

    # complete: mark task complete
    p_complete = subparsers.add_parser("complete", help="Mark task complete")
    p_complete.add_argument("--task-id", required=True, help="Task ID")
    p_complete.add_argument("--agent-id", required=True, help="Agent ID")
    p_complete.add_argument("--success", action="store_true", help="Success flag")
    p_complete.add_argument("--output", default="", help="Output message")
    p_complete.add_argument("--errors", nargs="*", help="Error messages")
    p_complete.add_argument("--orchestrator-url", help="Orchestrator URL")

    # validate: run outer loop validation
    p_validate = subparsers.add_parser("validate", help="Run validation")
    p_validate.add_argument("--task-id", help="Task ID")
    p_validate.add_argument("--zone", required=True, help="Zone")
    p_validate.add_argument("--description", required=True, help="Task description")
    p_validate.add_argument("--files", help="Comma-separated files")
    p_validate.add_argument("--level", choices=["none", "basic", "strict", "full"], default="strict", help="Validation level")
    p_validate.add_argument("--retries", type=int, default=3, help="Max retries")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "execute":
        return cmd_execute(args)
    elif args.command == "poll":
        return cmd_poll(args)
    elif args.command == "complete":
        return cmd_complete(args)
    elif args.command == "validate":
        return cmd_validate(args)

    return 1


if __name__ == "__main__":
    sys.exit(main())