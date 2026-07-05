# -*- coding: utf-8 -*-
"""
Agent Client — polling-based клиент для ИИ-агентов.

Позволяет агенту получать задачи из оркестратора и отчитываться о результате.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class AgentClient:
    """Polling-based клиент для работы с оркестратором."""

    def __init__(
        self,
        orchestrator_url: str,
        agent_id: str,
        zone: str,
        poll_interval: int = 5,
        timeout: int = 30,
    ):
        self.orchestrator_url = orchestrator_url.rstrip("/")
        self.agent_id = agent_id
        self.zone = zone
        self.poll_interval = poll_interval
        self.timeout = timeout

    def poll_tasks(self) -> List[Dict[str, Any]]:
        """Запросить список назначенных задач."""
        try:
            resp = requests.post(
                f"{self.orchestrator_url}/orchestrator/api/agent/tasks",
                json={"agent_id": self.agent_id},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json().get("tasks", [])
        except Exception as e:
            logger.error(f"Failed to poll tasks: {e}")
            return []

    def send_heartbeat(self, status: str = "idle") -> bool:
        """Отправить heartbeat со статусом."""
        try:
            requests.post(
                f"{self.orchestrator_url}/orchestrator/api/agent/heartbeat",
                json={"agent_id": self.agent_id, "status": status},
                timeout=self.timeout,
            )
            return True
        except Exception as e:
            logger.error(f"Heartbeat failed: {e}")
            return False

    def report_result(
        self,
        task_id: str,
        success: bool,
        output: str = "",
        errors: List[str] = None,
    ) -> bool:
        """Отправить результат выполнения задачи."""
        try:
            requests.post(
                f"{self.orchestrator_url}/orchestrator/api/agent/result",
                json={
                    "task_id": task_id,
                    "agent_id": self.agent_id,
                    "success": success,
                    "output": output,
                    "errors": errors or [],
                },
                timeout=self.timeout,
            )
            return True
        except Exception as e:
            logger.error(f"Report result failed: {e}")
            return False

    def do_work(self, task: Dict[str, Any]) -> bool:
        """Выполнить работу по задаче. Переопределить в наследниках."""
        task_id = task["task_id"]
        logger.info(f"Processing task {task_id}: {task.get('title', '')}")

        self.send_heartbeat("active")

        try:
            # Basic implementation - just log and mark complete
            # Override this method for actual work
            output = f"Task {task_id} processed by {self.agent_id}"
            self.report_result(task_id, success=True, output=output)
            return True
        except Exception as e:
            self.report_result(task_id, success=False, output=str(e))
            return False

    def work(self, single_run: bool = False) -> None:
        """Основной цикл опроса задач."""
        logger.info(f"Agent {self.agent_id} started, zone={self.zone}")

        while True:
            try:
                tasks = self.poll_tasks()

                if tasks:
                    for task in tasks:
                        self.do_work(task)
                else:
                    self.send_heartbeat("idle")

                if single_run:
                    break

                time.sleep(self.poll_interval)

            except KeyboardInterrupt:
                logger.info("Agent stopped by user")
                break
            except Exception as e:
                logger.error(f"Work loop error: {e}")
                time.sleep(self.poll_interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Orchestrator Agent Client")
    parser.add_argument("--orchestrator-url", default="http://localhost:5000", help="URL оркестратора")
    parser.add_argument("--agent-id", required=True, help="ID агента")
    parser.add_argument("--zone", required=True, help="Зона работы (parser, engine, model, etc)")
    parser.add_argument("--poll-interval", type=int, default=5, help="Интервал опроса в секундах")
    parser.add_argument("--single-run", action="store_true", help="Выполнить один раз и выйти")
    parser.add_argument("--verbose", "-v", action="store_true", help="Подробный вывод")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    client = AgentClient(
        orchestrator_url=args.orchestrator_url,
        agent_id=args.agent_id,
        zone=args.zone,
        poll_interval=args.poll_interval,
    )

    client.work(single_run=args.single_run)


if __name__ == "__main__":
    main()