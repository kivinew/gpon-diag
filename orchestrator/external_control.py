# -*- coding: utf-8 -*-
"""
External Control Loop - verifies AI agent task completion.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List

from orchestrator.task_card import TaskCard, TaskStatus, load_task_card, list_task_cards
from orchestrator.validator import SentinelValidator, RuleValidator, StructureValidator
from orchestrator.agent_registry import AgentRegistry, AgentStatus

logger = logging.getLogger(__name__)


@dataclass
class TaskVerificationResult:
    success: bool
    errors: List[str]
    warnings: List[str]
    metrics: Dict[str, Any]


class ExternalControlLoop:
    """External control loop for task verification."""

    def __init__(self, project_root: str, registry: AgentRegistry) -> None:
        self.project_root = project_root
        self.registry = registry

    def verify_task_completion(self, task_card: TaskCard) -> TaskVerificationResult:
        errors: List[str] = []
        warnings: List[str] = []
        metrics: Dict[str, Any] = {"checks_passed": 0, "checks_failed": 0}

        # Check structure validation
        missing_files = StructureValidator.check_file_exists(self.project_root)
        if missing_files:
            errors.append(f"Missing files: {missing_files}")
        metrics["checks_passed"] += len(missing_files) == 0

        missing_classes = StructureValidator.check_classes_exist(self.project_root)
        if missing_classes:
            errors.append(f"Missing classes: {missing_classes}")
        metrics["checks_passed"] += len(missing_classes) == 0

        # Check sentinel values in models
        engine_errors = SentinelValidator.check_engine_file(
            os.path.join(self.project_root, "core", "engine.py")
        )
        if engine_errors:
            errors.extend(engine_errors)
            metrics["checks_failed"] += len(engine_errors)
        else:
            metrics["checks_passed"] += 1

        models_errors = SentinelValidator.check_sentinel_defaults(
            os.path.join(self.project_root, "core", "models.py")
        )
        if models_errors:
            errors.extend(models_errors)
            metrics["checks_failed"] += len(models_errors)
        else:
            metrics["checks_passed"] += 1

        # Check rule signatures and online guards
        rule_errors = RuleValidator.check_rule_signatures(
            os.path.join(self.project_root, "core", "engine.py")
        )
        online_errors = RuleValidator.check_online_guard(
            os.path.join(self.project_root, "core", "engine.py")
        )
        if rule_errors or online_errors:
            errors.extend(rule_errors)
            errors.extend(online_errors)
            metrics["checks_failed"] += len(rule_errors) + len(online_errors)
        else:
            metrics["checks_passed"] += 2

        success = len(errors) == 0
        return TaskVerificationResult(success, errors, warnings, metrics)

    def request_revision(self, task_card: TaskCard, errors: List[str]) -> None:
        task_card.status = TaskStatus.REVISION_REQUIRED
        task_card.errors = errors
        task_card.revision_count += 1
        task_card.save()
        logger.warning(f"Task {task_card.task_id} requires revision: {errors}")

    def approve_completion(self, task_card: TaskCard) -> None:
        task_card.status = TaskStatus.COMPLETED
        task_card.save()
        logger.info(f"Task {task_card.task_id} approved")

    def verify_and_update(self, task_id: str) -> TaskVerificationResult:
        task_card = load_task_card(task_id)
        if not task_card:
            return TaskVerificationResult(False, ["Task not found"], [], {})

        result = self.verify_task_completion(task_card)

        if result.success:
            self.approve_completion(task_card)
        else:
            if task_card.revision_count >= task_card.max_revisions:
                task_card.status = TaskStatus.BLOCKED
                logger.error(f"Task {task_id} exceeded max revisions")
            else:
                self.request_revision(task_card, result.errors)

        return result


def run_verification_for_agent(agent_id: str, project_root: str) -> Dict[str, Any]:
    registry = AgentRegistry()
    loop = ExternalControlLoop(project_root, registry)

    agent_tasks = [
        tc for tc in list_task_cards()
        if tc.agent_id == agent_id and tc.status in (TaskStatus.IN_PROGRESS, TaskStatus.VERIFICATION_PENDING)
    ]

    results = {}
    for tc in agent_tasks:
        result = loop.verify_and_update(tc.task_id)
        results[tc.task_id] = {
            "success": result.success,
            "errors": result.errors,
            "status": tc.status.value,
        }

    return results