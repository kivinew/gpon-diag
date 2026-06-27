# -*- coding: utf-8 -*-
"""
GPON Diagnostic Framework — Agent Orchestration & File Locking System.

Components:
- agent_registry: регистрация и отслеживание ИИ-агентов
- lock_manager: блокировка файлов и зон
- validator: валидация структуры кода
- outer_loop: внешний цикл контроля за работой агентов
"""

from .agent_registry import (
    AgentRegistry,
    AgentStatus,
    AgentInfo,
    ZONE_FILE_MAP,
    ZONE_PARSER,
    ZONE_ENGINE,
    ZONE_MODEL,
    ZONE_CONNECTION,
    ZONE_REPORT,
    "ZONE_WEB",
    ZONE_CLI,
    PROTECTED_FILES,
)

from .lock_manager import (
    ZoneLockManager,
    LockError,
    LockTimeoutError,
    LockHeldByOtherError,
    file_lock,
)

from .validator import (
    SentinelValidator,
    RuleValidator,
    StructureValidator,
)

from .outer_loop import (
    OuterLoopController,
    TaskSpec,
    TaskExecution,
    TaskAttempt,
    TaskStatus,
    ValidationResult,
    ValidationLevel,
    create_outer_loop_controller,
    run_task_with_outer_loop,
)

__all__ = [
    # agent_registry
    "AgentRegistry",
    "AgentStatus",
    "AgentInfo",
    "ZONE_FILE_MAP",
    "ZONE_PARSER",
    "ZONE_ENGINE",
    "ZONE_MODEL",
    "ZONE_CONNECTION",
    "ZONE_REPORT",
    "ZONE_WEB",
    "ZONE_CLI",
    "PROTECTED_FILES",
    # lock_manager
    "ZoneLockManager",
    "LockError",
    "LockTimeoutError",
    "LockHeldByOtherError",
    "file_lock",
    # validator
    "SentinelValidator",
    "RuleValidator",
    "StructureValidator",
    # outer_loop
    "OuterLoopController",
    "TaskSpec",
    "TaskExecution",
    "TaskAttempt",
    "TaskStatus",
    "ValidationResult",
    "ValidationLevel",
    "create_outer_loop_controller",
    "run_task_with_outer_loop",
]
