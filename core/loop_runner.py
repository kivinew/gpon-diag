"""
Loop Runner — циклическое выполнение задач диагностики.

Принцип: большой объем работы (сотни ONT) разбивается на атомарные задачи,
каждая выполняется независимым запуском с чистым контекстом.
"""

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class LoopTask:
    """Одна атомарная задача в очереди."""
    id: str
    type: str  # "diagnose", "generate_rules", "batch_process"
    payload: dict
    status: str = "pending"  # pending, running, done, failed, skipped
    result: Optional[dict] = None
    error: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LoopTask":
        return cls(**data)


class TaskQueue:
    """Управление очередью задач с персистентностью в JSON."""

    def __init__(self, path: str = "data/loop_tasks.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.tasks: list[LoopTask] = []
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.tasks = [LoopTask.from_dict(t) for t in data]
            except Exception as e:
                logger.warning(f"Failed to load task queue: {e}")
                self.tasks = []

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump([t.to_dict() for t in self.tasks], f, ensure_ascii=False, indent=2)

    def add(self, task: LoopTask) -> LoopTask:
        self.tasks.append(task)
        self.save()
        return task

    def add_batch(self, tasks: list[LoopTask]):
        self.tasks.extend(tasks)
        self.save()

    def get_pending(self) -> list[LoopTask]:
        return [t for t in self.tasks if t.status == "pending"]

    def get_next(self) -> Optional[LoopTask]:
        for t in self.tasks:
            if t.status == "pending":
                return t
        return None

    def mark_running(self, task_id: str):
        for t in self.tasks:
            if t.id == task_id:
                t.status = "running"
                t.started_at = datetime.now().isoformat()
                t.attempts += 1
                break
        self.save()

    def mark_done(self, task_id: str, result: dict):
        for t in self.tasks:
            if t.id == task_id:
                t.status = "done"
                t.result = result
                t.completed_at = datetime.now().isoformat()
                break
        self.save()

    def mark_failed(self, task_id: str, error: str):
        for t in self.tasks:
            if t.id == task_id:
                t.status = "failed"
                t.error = error
                t.completed_at = datetime.now().isoformat()
                break
        self.save()

    def retry_failed(self):
        for t in self.tasks:
            if t.status == "failed" and t.attempts < t.max_attempts:
                t.status = "pending"
                t.error = None
        self.save()

    def stats(self) -> dict:
        total = len(self.tasks)
        if total == 0:
            return {"total": 0, "pending": 0, "running": 0, "done": 0, "failed": 0}
        return {
            "total": total,
            "pending": sum(1 for t in self.tasks if t.status == "pending"),
            "running": sum(1 for t in self.tasks if t.status == "running"),
            "done": sum(1 for t in self.tasks if t.status == "done"),
            "failed": sum(1 for t in self.tasks if t.status == "failed"),
        }


class LoopRunner:
    """
    Основной цикл выполнения задач.

    Использование:
        runner = LoopRunner(max_loops=50)
        runner.add_task(LoopTask(...))
        runner.run()
    """

    def __init__(
        self,
        max_loops: int = 10,
        queue_path: str = "data/loop_tasks.json",
        diagnose_script: str = "diagnose.py",
        workdir: Optional[str] = None,
    ):
        self.max_loops = max_loops
        self.queue = TaskQueue(queue_path)
        self.diagnose_script = diagnose_script
        self.workdir = Path(workdir) if workdir else Path.cwd()
        self.current_loop = 0

    def add_task(self, task: LoopTask):
        self.queue.add(task)

    def add_tasks(self, tasks: list[LoopTask]):
        self.queue.add_batch(tasks)

    def run(self) -> dict:
        """Запускает цикл выполнения до max_loops или пока есть задачи."""
        logger.info(f"Starting loop runner: max_loops={self.max_loops}")
        print(f"[Loop] Starting — max loops: {self.max_loops}")

        while self.current_loop < self.max_loops:
            self.current_loop += 1
            stats = self.queue.stats()

            if stats["pending"] == 0:
                print(f"[Loop {self.current_loop}] No pending tasks. Done.")
                break

            task = self.queue.get_next()
            if not task:
                print(f"[Loop {self.current_loop}] No next task. Done.")
                break

            print(f"\n[Loop {self.current_loop}/{self.max_loops}] Task {task.id} ({task.type}) — {stats['pending']} pending, {stats['done']} done")
            self.queue.mark_running(task.id)

            try:
                result = self._execute_task(task)
                self.queue.mark_done(task.id, result)
                print(f"  ✓ Done: {result.get('summary', 'ok')}")
            except Exception as e:
                logger.exception(f"Task {task.id} failed")
                self.queue.mark_failed(task.id, str(e))
                print(f"  ✗ Failed: {e}")

        final_stats = self.queue.stats()
        print(f"\n[Loop] Finished after {self.current_loop} loops: {final_stats['done']} done, {final_stats['failed']} failed")
        return final_stats

    def _execute_task(self, task: LoopTask) -> dict:
        """Выполняет одну задачу через отдельный процесс (чистый контекст)."""
        if task.type == "diagnose":
            return self._run_diagnose_task(task)
        elif task.type == "batch_diagnose":
            return self._run_batch_diagnose(task)
        elif task.type == "generate_rules":
            return self._run_generate_rules(task)
        else:
            raise ValueError(f"Unknown task type: {task.type}")

    def _run_diagnose_task(self, task: LoopTask) -> dict:
        """Запуск диагностики одной ONT через subprocess."""
        payload = task.payload
        ont_id = payload.get("ont_id") or payload.get("address") or payload.get("serial") or payload.get("description")
        olt = payload.get("olt", "")
        no_actions = payload.get("no_actions", False)
        json_output = payload.get("json", True)

        cmd = [
            sys.executable, self.diagnose_script,
            str(ont_id),
        ]
        if olt:
            cmd.extend(["--olt", olt])
        if no_actions:
            cmd.append("--no-actions")
        if json_output:
            cmd.append("--json")
        cmd.append("--no-save")

        result = subprocess.run(
            cmd,
            cwd=self.workdir,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Diagnose failed: {result.stderr[:500]}")

        # Parse JSON output
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError:
            # Fallback: just return raw output
            report = {"raw_output": result.stdout[:2000]}

        return {
            "summary": f"ONT {ont_id} diagnosed",
            "report": report,
            "stdout": result.stdout[-500:] if len(result.stdout) > 500 else result.stdout,
        }

    def _run_batch_diagnose(self, task: LoopTask) -> dict:
        """Пакетная диагностика списка ONT."""
        payload = task.payload
        onts = payload.get("onts", [])
        olt = payload.get("olt", "")
        no_actions = payload.get("no_actions", False)

        results = []
        for i, ont in enumerate(onts):
            print(f"    [{i+1}/{len(onts)}] {ont}")
            try:
                subtask = LoopTask(
                    id=f"{task.id}_sub_{i}",
                    type="diagnose",
                    payload={"ont_id": ont, "olt": olt, "no_actions": no_actions},
                    max_attempts=1,
                )
                result = self._run_diagnose_task(subtask)
                results.append({"ont": ont, "status": "done", "report": result.get("report")})
            except Exception as e:
                results.append({"ont": ont, "status": "failed", "error": str(e)})

        done = sum(1 for r in results if r["status"] == "done")
        return {
            "summary": f"Batch: {done}/{len(onts)} completed",
            "results": results,
        }

    def _run_generate_rules(self, task: LoopTask) -> dict:
        """Генерация новых правил диагностики на основе собранных отчетов."""
        # Это заглушка — реализация будет добавлять правила в engine.py
        payload = task.payload
        reports_dir = payload.get("reports_dir", "data/reports")

        # Здесь логика анализа отчетов и предложения новых правил
        # Пока возвращаем заглушку
        return {
            "summary": "Rule generation not yet implemented",
            "suggested_rules": [],
        }


def create_diagnose_tasks(
    onts: list[str],
    olt: str = "",
    no_actions: bool = False,
) -> list[LoopTask]:
    """Создает задачи диагностики для списка ONT."""
    tasks = []
    for i, ont in enumerate(onts):
        task = LoopTask(
            id=f"diag_{i:04d}_{ont.replace('/', '_')}",
            type="diagnose",
            payload={
                "ont_id": ont,
                "olt": olt,
                "no_actions": no_actions,
                "json": True,
            },
        )
        tasks.append(task)
    return tasks


def load_onts_from_csv(csv_path: str, column: str = "ont") -> list[str]:
    """Загружает список ONT из CSV файла."""
    import csv
    onts = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            val = row.get(column) or row.get("address") or row.get("serial") or row.get("description")
            if val:
                onts.append(val.strip())
    return onts


def load_onts_from_file(txt_path: str) -> list[str]:
    """Загружает список ONT из текстового файла (по одной в строке)."""
    with open(txt_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]