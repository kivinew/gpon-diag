# -*- coding: utf-8 -*-
"""
Outer Loop Controller — внешний цикл контроля за работой ИИ-агентов.

Архитектура:
1. Принимает задачу (TaskSpec) и назначает агента
2. Запускает агента через AgentRegistry + LockManager
3. После завершения — валидирует результат через существующие валидаторы
4. Если валидация не пройдена — возвращает задачу агенту с деталями ошибок
5. Повторяет до успеха или превышения max_retries

Интеграция с существующими компонентами:
- AgentRegistry: регистрация, heartbeat, статус, конфликты
- LockManager: блокировка зон/файлов, deadlock detection
- Validator: SentinelValidator, RuleValidator, StructureValidator
"""

from __future__ import annotations

import logging
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol

from orchestrator.agent_registry import AgentRegistry, AgentStatus, AgentInfo, ZONE_FILE_MAP
from orchestrator.lock_manager import ZoneLockManager, LockTimeoutError, LockHeldByOtherError
from orchestrator.validator import (
    SentinelValidator,
    RuleValidator,
    StructureValidator,
)

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY_EXHAUSTED = "retry_exhausted"


class ValidationLevel(Enum):
    """Уровни строгости валидации."""
    NONE = 0          # только базовая структура
    BASIC = 1         # sentinel + структуры
    STRICT = 2        # всё + правила онлайн-гарда + подписи
    FULL = 3          # всё вышеперечисленное + категории + порядок правил


@dataclass
class TaskSpec:
    """Спецификация задачи для внешнего цикла."""
    task_id: str
    zone: str
    description: str
    files_intended: List[str]
    validation_level: ValidationLevel = ValidationLevel.STRICT
    max_retries: int = 3
    timeout_seconds: int = 300
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Опционально: функция-фабрика агента (для тестов/интеграции)
    agent_factory: Optional[Callable[[str, str, List[str]], Any]] = None


@dataclass
class ValidationResult:
    """Результат валидации."""
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    validated_at: datetime = field(default_factory=datetime.now)
    validator_name: str = ""


@dataclass
class TaskAttempt:
    """Попытка выполнения задачи."""
    attempt_number: int
    agent_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    validation_result: Optional[ValidationResult] = None
    error_message: str = ""


@dataclass
class TaskExecution:
    """Полное состояние выполнения задачи во внешнем цикле."""
    spec: TaskSpec
    status: TaskStatus = TaskStatus.PENDING
    attempts: List[TaskAttempt] = field(default_factory=list)
    current_agent_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    final_result: Optional[ValidationResult] = None


class AgentExecutor(Protocol):
    """Протокол для исполнителя агента (можно подменить в тестах)."""
    def execute(self, agent_id: str, zone: str, files: List[str], task_description: str) -> bool:
        """Выполняет работу агента. Возвращает True если агент считает задачу выполненной."""
        ...


class OuterLoopController:
    """
    Контроллер внешнего цикла для управления ИИ-агентами.

    Основной поток:
    1. register_task(task_spec) — регистрация задачи
    2. run_task(task_id) — запуск внешнего цикла
    3. get_task_status(task_id) — проверка статуса
    4. get_task_result(task_id) — получение результата
    """

    def __init__(
        self,
        project_root: str,
        agent_registry: Optional[AgentRegistry] = None,
        lock_manager: Optional[ZoneLockManager] = None,
        executor: Optional[AgentExecutor] = None,
    ):
        self.project_root = project_root
        self.registry = agent_registry or AgentRegistry()
        self.lock_manager = lock_manager or ZoneLockManager()
        self.executor = executor

        # Валидаторы
        self.sentinel_validator = SentinelValidator()
        self.rule_validator = RuleValidator()
        self.structure_validator = StructureValidator()

        # Хранилище задач
        self._tasks: Dict[str, TaskExecution] = {}
        self._tasks_lock = threading.RLock()

        # Коллбеки для уведомлений
        self._on_task_started: List[Callable[[str], None]] = []
        self._on_task_completed: List[Callable[[str, ValidationResult], None]] = []
        self._on_task_failed: List[Callable[[str, str], None]] = []
        self._on_retry: List[Callable[[str, int, List[str]], None]] = []

    # ===== Публичный API =====

    def register_task(self, spec: TaskSpec) -> str:
        """Регистрирует новую задачу во внешнем цикле."""
        with self._tasks_lock:
            if spec.task_id in self._tasks:
                raise ValueError(f"Task '{spec.task_id}' already registered")
            execution = TaskExecution(spec=spec)
            self._tasks[spec.task_id] = execution
            logger.info(f"Task '{spec.task_id}' registered for zone '{spec.zone}'")
            return spec.task_id

    def remove_task(self, task_id: str) -> None:
        """Удаляет задачу из очереди, если она ещё не завершена.

        Если задача уже находится в статусе COMPLETED, FAILED или
        RETRY_EXHAUSTED – будет выброшено исключение, чтобы избежать
        потери результатов.
        """
        with self._tasks_lock:
            execution = self._tasks.get(task_id)
            if not execution:
                raise ValueError(f"Task '{task_id}' not found")
            if execution.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.RETRY_EXHAUSTED):
                raise ValueError(f"Cannot remove completed task '{task_id}'")
            del self._tasks[task_id]
            logger.info(f"Task '{task_id}' removed from queue")

    def run_task(self, task_id: str, blocking: bool = True) -> ValidationResult:
        """
        Запускает внешний цикл для задачи.

        Args:
            task_id: ID задачи
            blocking: если True — ждёт завершения, иначе запускает в фоне

        Returns:
            ValidationResult — результат финальной валидации
        """
        execution = self._get_task(task_id)
        if not execution:
            raise ValueError(f"Task '{task_id}' not found")

        if execution.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.RETRY_EXHAUSTED):
            logger.warning(f"Task '{task_id}' already finished with status {execution.status}")
            return execution.final_result or ValidationResult(passed=False, errors=["Task already finished"])

        # Запускаем в отдельном потоке если non-blocking
        if not blocking:
            thread = threading.Thread(target=self._run_loop, args=(task_id,), daemon=True)
            thread.start()
            return ValidationResult(passed=False, errors=["Running in background"])

        return self._run_loop(task_id)

    def get_task_status(self, task_id: str) -> TaskStatus:
        """Возвращает текущий статус задачи."""
        execution = self._get_task(task_id)
        return execution.status if execution else TaskStatus.PENDING

    def get_task_result(self, task_id: str) -> Optional[ValidationResult]:
        """Возвращает финальный результат валидации."""
        execution = self._get_task(task_id)
        return execution.final_result if execution else None

    def get_task_execution(self, task_id: str) -> Optional[TaskExecution]:
        """Возвращает полное состояние выполнения задачи."""
        return self._get_task(task_id)

    def list_tasks(self) -> Dict[str, TaskExecution]:
        """Возвращает все задачи."""
        with self._tasks_lock:
            return dict(self._tasks)

    # ===== Callbacks =====

    def on_task_started(self, callback: Callable[[str], None]) -> None:
        self._on_task_started.append(callback)

    def on_task_completed(self, callback: Callable[[str, ValidationResult], None]) -> None:
        self._on_task_completed.append(callback)

    def on_task_failed(self, callback: Callable[[str, str], None]) -> None:
        self._on_task_failed.append(callback)

    def on_retry(self, callback: Callable[[str, int, List[str]], None]) -> None:
        self._on_retry.append(callback)

    # ===== Внутренний цикл =====

    def _run_loop(self, task_id: str) -> ValidationResult:
        """Основной внешний цикл: попытка -> валидация -> ретраи."""
        execution = self._get_task(task_id)
        if not execution:
            return ValidationResult(passed=False, errors=[f"Task '{task_id}' not found"])

        spec = execution.spec

        for attempt_num in range(1, spec.max_retries + 1):
            logger.info(f"Task '{task_id}': attempt {attempt_num}/{spec.max_retries}")

            # 1. Назначение агента
            agent_id = self._assign_agent(spec, attempt_num)
            if not agent_id:
                execution.status = TaskStatus.FAILED
                result = ValidationResult(
                    passed=False,
                    errors=[f"Could not assign agent for zone '{spec.zone}'"],
                    validator_name="outer_loop"
                )
                execution.final_result = result
                self._notify_failed(task_id, "No agent available")
                return result

            execution.current_agent_id = agent_id
            execution.status = TaskStatus.RUNNING

            attempt = TaskAttempt(
                attempt_number=attempt_num,
                agent_id=agent_id,
                started_at=datetime.now()
            )
            execution.attempts.append(attempt)

            self._notify_started(task_id)

            # 2. Выполнение агента
            success = self._execute_agent(agent_id, spec, attempt)
            attempt.completed_at = datetime.now()

            if not success:
                attempt.error_message = "Agent execution failed or timed out"
                logger.warning(f"Task '{task_id}': agent '{agent_id}' failed")
                if attempt_num < spec.max_retries:
                    self._notify_retry(task_id, attempt_num, [attempt.error_message])
                    continue
                break

            # 3. Валидация результата
            execution.status = TaskStatus.VALIDATING
            validation_result = self._validate_task(spec, attempt)
            attempt.validation_result = validation_result

            if validation_result.passed:
                # Успех!
                execution.status = TaskStatus.COMPLETED
                execution.completed_at = datetime.now()
                execution.final_result = validation_result
                self._release_agent(agent_id)
                self._notify_completed(task_id, validation_result)
                logger.info(f"Task '{task_id}' completed successfully on attempt {attempt_num}")
                return validation_result
            else:
                # Валидация не пройдена — ретрай
                logger.warning(f"Task '{task_id}': validation failed on attempt {attempt_num}: {validation_result.errors}")
                self._release_agent(agent_id)
                if attempt_num < spec.max_retries:
                    self._notify_retry(task_id, attempt_num, validation_result.errors)
                    continue

        # Все попытки исчерпаны
        execution.status = TaskStatus.RETRY_EXHAUSTED
        execution.completed_at = datetime.now()
        final_errors = execution.attempts[-1].validation_result.errors if execution.attempts else ["Max retries exceeded"]
        execution.final_result = ValidationResult(
            passed=False,
            errors=final_errors,
            validator_name="outer_loop"
        )
        self._notify_failed(task_id, "Max retries exceeded")
        return execution.final_result

    def _assign_agent(self, spec: TaskSpec, attempt_num: int) -> Optional[str]:
        """Назначает агента для задачи."""
        agent_id = f"{spec.zone}_agent_{spec.task_id}_{attempt_num}"

        try:
            # Пытаемся захватить зону
            if not self.lock_manager.acquire_zone(spec.zone, agent_id):
                logger.warning(f"Zone '{spec.zone}' is locked, cannot assign agent")
                return None

            # Регистрируем агента
            self.registry.register(
                agent_id=agent_id,
                zone=spec.zone,
                files_intended=spec.files_intended,
                metadata={"task_id": spec.task_id, "attempt": str(attempt_num)}
            )

            # Переводим в активный статус
            self.registry.set_status(agent_id, AgentStatus.ACTIVE)

            logger.info(f"Assigned agent '{agent_id}' to zone '{spec.zone}'")
            return agent_id

        except ValueError as e:
            logger.error(f"Failed to assign agent: {e}")
            self.lock_manager.release_zone(spec.zone, agent_id)
            return None

    def _release_agent(self, agent_id: str) -> None:
        """Освобождает ресурсы агента."""
        agent = self.registry.get_agent(agent_id)
        if agent:
            self.lock_manager.release_zone(agent.zone, agent_id)
            self.registry.set_status(agent_id, AgentStatus.COMPLETED)
            # Не deregister — оставляем для истории

    def _execute_agent(self, agent_id: str, spec: TaskSpec, attempt: TaskAttempt) -> bool:
        """Выполняет работу агента."""
        if self.executor:
            # Используем кастомный исполнитель
            try:
                return self.executor.execute(agent_id, spec.zone, spec.files_intended, spec.description)
            except Exception as e:
                logger.error(f"Executor error for agent '{agent_id}': {e}")
                attempt.error_message = str(e)
                return False

        # Стандартное поведение: ждём heartbeat от внешнего агента
        # (в реальном использовании сюда подключается интеграция с Claude Code / subagent)
        return self._wait_for_agent_completion(agent_id, spec.timeout_seconds)

    def _wait_for_agent_completion(self, agent_id: str, timeout: int) -> bool:
        """
        Ожидает завершения работы агента через heartbeat.
        В реальной интеграции здесь будет вызов subagent / CLI.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            agent = self.registry.get_agent(agent_id)
            if not agent:
                return False

            if agent.status == AgentStatus.COMPLETED:
                return True
            elif agent.status == AgentStatus.ERROR:
                return False
            elif agent.status == AgentStatus.TIMEOUT:
                return False

            time.sleep(1)

        # Таймаут
        self.registry.set_status(agent_id, AgentStatus.TIMEOUT, "Outer loop timeout")
        return False

    def _validate_task(self, spec: TaskSpec, attempt: TaskAttempt) -> ValidationResult:
        """Запускает все валидаторы согласно уровню строгости."""
        all_errors = []
        all_warnings = []
        validators_run = []

        # 1. StructureValidator — всегда
        if spec.validation_level.value >= ValidationLevel.NONE.value:
            errors = self.structure_validator.check_file_exists(self.project_root)
            if errors:
                all_errors.extend([f"Structure: {e}" for e in errors])
            errors = self.structure_validator.check_classes_exist(self.project_root)
            if errors:
                all_errors.extend([f"Structure: {e}" for e in errors])
            validators_run.append("StructureValidator")

        # 2. SentinelValidator — BASIC и выше
        if spec.validation_level.value >= ValidationLevel.BASIC.value:
            engine_path = f"{self.project_root}/core/engine.py"
            models_path = f"{self.project_root}/core/models.py"

            errors = self.sentinel_validator.check_engine_file(engine_path)
            if errors:
                all_errors.extend([f"Sentinel: {e}" for e in errors])

            errors = self.sentinel_validator.check_sentinel_defaults(models_path)
            if errors:
                all_errors.extend([f"Sentinel: {e}" for e in errors])
            validators_run.append("SentinelValidator")

        # 3. RuleValidator — STRICT и выше
        if spec.validation_level.value >= ValidationLevel.STRICT.value:
            engine_path = f"{self.project_root}/core/engine.py"

            errors = self.rule_validator.check_online_guard(engine_path)
            if errors:
                all_errors.extend([f"Rule: {e}" for e in errors])

            errors = self.rule_validator.check_rule_signatures(engine_path)
            if errors:
                all_errors.extend([f"Rule: {e}" for e in errors])

            errors = self.rule_validator.check_default_rules_order(engine_path)
            if errors:
                all_errors.extend([f"Rule: {e}" for e in errors])
            validators_run.append("RuleValidator")

        # 4. FULL — категории и дополнительные проверки
        if spec.validation_level.value >= ValidationLevel.FULL.value:
            engine_path = f"{self.project_root}/core/engine.py"
            categories = self.rule_validator.check_categories(engine_path)
            if not categories:
                all_warnings.append("RuleValidator: no categories found")
            validators_run.append("RuleValidator(categories)")

        passed = len(all_errors) == 0
        return ValidationResult(
            passed=passed,
            errors=all_errors,
            warnings=all_warnings,
            validator_name="+".join(validators_run)
        )

    def _get_task(self, task_id: str) -> Optional[TaskExecution]:
        with self._tasks_lock:
            return self._tasks.get(task_id)

    def _notify_started(self, task_id: str) -> None:
        for cb in self._on_task_started:
            try:
                cb(task_id)
            except Exception:
                pass

    def _notify_completed(self, task_id: str, result: ValidationResult) -> None:
        for cb in self._on_task_completed:
            try:
                cb(task_id, result)
            except Exception:
                pass

    def _notify_failed(self, task_id: str, reason: str) -> None:
        for cb in self._on_task_failed:
            try:
                cb(task_id, reason)
            except Exception:
                pass

    def _notify_retry(self, task_id: str, attempt: int, errors: List[str]) -> None:
        for cb in self._on_retry:
            try:
                cb(task_id, attempt, errors)
            except Exception:
                pass


# ===== Удобные функции для быстрого старта =====

def create_outer_loop_controller(project_root: str) -> OuterLoopController:
    """Фабрика для создания контроллера с дефолтными настройками."""
    return OuterLoopController(project_root=project_root)


def run_task_with_outer_loop(
    project_root: str,
    task_id: str,
    zone: str,
    description: str,
    files_intended: List[str],
    validation_level: ValidationLevel = ValidationLevel.STRICT,
    max_retries: int = 3,
) -> ValidationResult:
    """
    Быстрый запуск задачи во внешнем цикле.

    Пример:
        result = run_task_with_outer_loop(
            project_root="/path/to/gpon-diag",
            task_id="fix_parser_001",
            zone="parser",
            description="Fix regex for Huawei CLI output",
            files_intended=["core/parser.py"],
        )
    """
    controller = create_outer_loop_controller(project_root)
    spec = TaskSpec(
        task_id=task_id,
        zone=zone,
        description=description,
        files_intended=files_intended,
        validation_level=validation_level,
        max_retries=max_retries,
    )
    controller.register_task(spec)
    return controller.run_task(task_id)


# ===== CLI для тестирования =====

if __name__ == "__main__":
    import sys
    import os

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    controller = create_outer_loop_controller(project_root)

    spec = TaskSpec(
        task_id="validation_test_001",
        zone="engine",
        description="Validate current project state",
        files_intended=["core/engine.py", "core/models.py"],
        validation_level=ValidationLevel.FULL,
        max_retries=1,
    )

    controller.register_task(spec)
    result = controller.run_task("validation_test_001")

    print(f"\n=== Validation Result ===")
    print(f"Passed: {result.passed}")
    print(f"Validator: {result.validator_name}")
    print(f"Errors: {len(result.errors)}")
    for err in result.errors:
        print(f"  - {err}")
    print(f"Warnings: {len(result.warnings)}")
    for warn in result.warnings:
        print(f"  - {warn}")

    sys.exit(0 if result.passed else 1)