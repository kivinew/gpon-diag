# -*- coding: utf-8 -*-
"""
GPON Diagnostic Framework — Agent Orchestration & File Locking System.

Components:
- agent_registry: регистрация и отслеживание ИИ-агентов
- lock_manager: блокировка файлов и зон
- validator: валидация структуры кода
- outer_loop: внешний цикл контроля за работой агентов

Utility:
- register_builtin_agents(): registers default AI agents (claude, qwen, cline).
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
    ZONE_WEB,
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

from .agent_client import AgentClient

# ---------------------------------------------------------------------------

# Helper to ensure a single global registry is created and agents registered
def _ensure_global_registry() -> AgentRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = AgentRegistry()
        # Register default agents once
        register_builtin_agents(_global_registry)
    return _global_registry

# Public wrapper for listing agents
def list_agents() -> dict:
    """Return a dictionary of all registered agents (id → AgentInfo)."""
    return _ensure_global_registry().list_all()

# ---------------------------------------------------------------------------
# Built‑in AI agent registration helper
# ---------------------------------------------------------------------------
def register_builtin_agents(registry: AgentRegistry) -> None:
    """Register the default AI agents used by the framework.

    The three agents are identified by a short name and are assigned to
    logical zones that reflect their typical responsibilities:

    * ``claude`` – analysis & code‑review zone (``ZONE_PARSER``)
    * ``qwen``   – rule‑engine / diagnostics zone (``ZONE_ENGINE``)
    * ``cline``  – CLI orchestration zone (``ZONE_CLI``)

    Each registration includes a short ``metadata`` map that can be used by
    external monitoring tools.
    """
    agents = [
        ("claude", ZONE_PARSER, ["core/parser.py"], {"role": "code_review"}),
        ("qwen", ZONE_ENGINE, ["core/engine.py"], {"role": "diagnostics"}),
        ("cline", ZONE_CLI, ["diagnose.py"], {"role": "cli_orchestrator"}),
    ]
    for aid, zone, files, meta in agents:
        try:
            registry.register(agent_id=aid, zone=zone, files_intended=files, metadata=meta)
        except Exception as exc:  # pragma: no cover – defensive, should not happen in normal flow
            # Log but do not raise – registration is idempotent per process run.
            import logging

            logging.getLogger(__name__).warning("Failed to register agent %s: %s", aid, exc)

def delete_task_from_queue(controller: OuterLoopController, task_id: str) -> None:
    """Remove a task from the orchestrator's queue.

    This is a thin wrapper around ``OuterLoopController.remove_task``.
    It raises the same ``ValueError`` if the task cannot be removed.
    """
    controller.remove_task(task_id)


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
    "delete_task_from_queue",
    "register_builtin_agents",
    "list_agents",
    # agent_client
    "AgentClient",
]

