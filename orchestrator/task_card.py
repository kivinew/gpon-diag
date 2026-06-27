# -*- coding: utf-8 -*-
"""
Task Card System - manages task cards for AI agents.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TASKS_BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".mimocode", "tasks")


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    VERIFICATION_PENDING = "verification_pending"
    REVISION_REQUIRED = "revision_required"
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass
class TaskCard:
    task_id: str
    title: str
    description: str
    zone: str
    agent_id: str = ""
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    verification_criteria: List[str] = field(default_factory=list)
    result: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    revision_count: int = 0
    max_revisions: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    def save(self) -> None:
        path = self._path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

    def _path(self) -> str:
        path = os.path.join(TASKS_BASE_DIR, self.task_id, "card.json")
        return os.path.abspath(path)


def create_task_card(title: str, description: str, zone: str,
                     verification_criteria: List[str],
                     metadata: Optional[Dict[str, Any]] = None) -> TaskCard:
    task_id = f"T{str(uuid.uuid4())[:8]}"
    card = TaskCard(
        task_id=task_id,
        title=title,
        description=description,
        zone=zone,
        verification_criteria=verification_criteria,
        metadata=metadata or {},
    )
    card.save()
    return card


def load_task_card(task_id: str) -> Optional[TaskCard]:
    path = os.path.join(TASKS_BASE_DIR, task_id, "card.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # При загрузке статус может быть уже объектом Enum (если файл был
    # записан с помощью .to_dict()) или строкой. Приводим к Enum только в
    # случае строкового значения, иначе оставляем как есть.
    # Приведение поля "status" к Enum.
    # Возможные варианты в файле:
    #   * "pending" (обычная строка) – обычный случай.
    #   * "TaskStatus.PENDING" (строка, полученная при прямой сериализации Enum).
    #   * уже объект Enum – тогда ничего не делаем.
    status_val = data.get("status")
    if isinstance(status_val, str):
        # Если в строке присутствует точка, берём часть после неё.
        if "." in status_val:
            status_val = status_val.split(".")[-1].lower()
        data["status"] = TaskStatus(status_val)
    # иначе оставляем как есть (Enum уже).

    return TaskCard(**data)


def list_task_cards() -> List[TaskCard]:
    base_path = TASKS_BASE_DIR
    cards = []
    if not os.path.exists(base_path):
        return cards
    for item in os.listdir(base_path):
        card = load_task_card(item)
        if card:
            cards.append(card)
    return cards