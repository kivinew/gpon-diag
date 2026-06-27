# -*- coding: utf-8 -*-
"""
Agent Registry — регистрация и отслеживание ИИ-агентов.
"""

from __future__ import annotations
import enum
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)



class AgentStatus(enum.Enum):
    REGISTERED = "registered"
    ACTIVE = "active"
    IDLE = "idle"
    ERROR = "error"
    COMPLETED = "completed"
    TIMEOUT = "timeout"


ZONE_PARSER = "parser"
ZONE_ENGINE = "engine"
ZONE_MODEL = "model"
ZONE_CONNECTION = "connection"
ZONE_REPORT = "report"
ZONE_WEB = "web"
ZONE_CLI = "cli"

ZONE_FILE_MAP: Dict[str, List[str]] = {
    ZONE_PARSER: ["core/parser.py"],
    ZONE_ENGINE: ["core/engine.py"],
    ZONE_MODEL: ["core/models.py"],
    ZONE_CONNECTION: ["core/olt.py"],
    ZONE_REPORT: ["core/report.py", "core/reporter.py"],
    ZONE_WEB: ["web/app.py", "web/templates", "web/static"],
    ZONE_CLI: ["diagnose.py"],
}

PROTECTED_FILES: Dict[str, str] = {
    "core/models.py": "Единый контракт. Поле только field(default=...) в конец.",
    "core/engine.py": "Движок правил. Новое правило - в конец EXTENDED_RULES.",
    "core/olt.py": "Singleton-реестр. Не менять без тестирования.",
    "core/parser.py": "Регулярки Huawei CLI. Тестировать с реальным выводом.",
    "diagnose.py": "Основной конвейер. Не менять run_diagnosis().",
    ".env": "Секреты. Не создавать новые переменные.",
    ".gitignore": "Не расширять.",
    "config.yaml": "Конфигурация деплоя.",
}

HEARTBEAT_TIMEOUT_SECONDS = 120
MAX_AGENTS_PER_ZONE = 2


@dataclass
class AgentInfo:
    agent_id: str
    zone: str
    created_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    status: AgentStatus = AgentStatus.REGISTERED
    files_intended: List[str] = field(default_factory=list)
    error_message: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)



class AgentRegistry:
    """Потокобезопасный реестр агентов."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._agents: Dict[str, AgentInfo] = {}

    def register(self, agent_id: str, zone: str, files_intended=None, metadata=None) -> str:
        if zone not in ZONE_FILE_MAP:
            raise ValueError(f"Unknown zone '{zone}'. Available: {list(ZONE_FILE_MAP.keys())}")
        with self._lock:
            if agent_id in self._agents:
                raise ValueError(f"Agent '{agent_id}' already registered")
            active_in_zone = sum(1 for a in self._agents.values()
                if a.zone == zone and a.status in (AgentStatus.ACTIVE, AgentStatus.REGISTERED))
            if active_in_zone >= MAX_AGENTS_PER_ZONE:
                raise ValueError(f"Zone '{zone}' has {active_in_zone} agents. Max: {MAX_AGENTS_PER_ZONE}.")
            intended = files_intended or []
            for oid, o in self._agents.items():
                if o.status in (AgentStatus.ACTIVE, AgentStatus.REGISTERED):
                    cfl = set(intended) & set(o.files_intended)
                    if cfl:
                        logger.warning(f"File conflict '{agent_id}' vs '{oid}': {cfl}")
            info = AgentInfo(agent_id=agent_id, zone=zone, files_intended=intended, metadata=metadata or {})
            self._agents[agent_id] = info
            logger.info(f"Agent '{agent_id}' registered in zone '{zone}'")
            return f"Agent '{agent_id}' registered in zone '{zone}'"

    def deregister(self, agent_id: str) -> None:
        with self._lock:
            self._agents.pop(agent_id, None)

    def heartbeat(self, agent_id: str, status=None) -> None:
        with self._lock:
            if agent_id not in self._agents:
                return
            self._agents[agent_id].last_heartbeat = time.time()
            if status:
                self._agents[agent_id].status = status

    def set_status(self, agent_id: str, status: AgentStatus, message: str = "") -> None:
        with self._lock:
            if agent_id not in self._agents:
                return
            self._agents[agent_id].status = status
            self._agents[agent_id].last_heartbeat = time.time()
            if message:
                self._agents[agent_id].error_message = message

    def get_agent(self, agent_id: str) -> Optional[AgentInfo]:
        with self._lock:
            return self._agents.get(agent_id)

    def get_agents_by_zone(self, zone: str) -> List[AgentInfo]:
        with self._lock:
            return [a for a in self._agents.values() if a.zone == zone]

    def list_active(self) -> Dict[str, AgentInfo]:
        with self._lock:
            return {aid: info for aid, info in self._agents.items()
                if info.status in (AgentStatus.ACTIVE, AgentStatus.REGISTERED)}

    def list_all(self) -> Dict[str, AgentInfo]:
        with self._lock:
            return dict(self._agents)

    def reap_stale_agents(self) -> List[str]:
        now = time.time()
        reaped = []
        with self._lock:
            for aid, info in self._agents.items():
                if info.status in (AgentStatus.ACTIVE, AgentStatus.REGISTERED, AgentStatus.IDLE):
                    if now - info.last_heartbeat > HEARTBEAT_TIMEOUT_SECONDS:
                        info.status = AgentStatus.TIMEOUT
                        info.error_message = f"No heartbeat >{HEARTBEAT_TIMEOUT_SECONDS}s"
                        reaped.append(aid)
        return reaped

    def get_conflicts(self) -> List[Dict]:
        conflicts = []
        with self._lock:
            active = [a for a in self._agents.values()
                if a.status in (AgentStatus.ACTIVE, AgentStatus.REGISTERED)]
            for i, a in enumerate(active):
                for b in active[i + 1:]:
                    if a.zone == b.zone:
                        conflicts.append({"type": "zone_conflict", "agent_a": a.agent_id,
                            "agent_b": b.agent_id, "zone": a.zone,
                            "files": list(set(a.files_intended) & set(b.files_intended))})
                    common = set(a.files_intended) & set(b.files_intended)
                    if common:
                        conflicts.append({"type": "file_conflict", "agent_a": a.agent_id,
                            "agent_b": b.agent_id, "zone": f"{a.zone}/{b.zone}", "files": list(common)})
        return conflicts

    @staticmethod
    def resolve_zone(file_path: str) -> Optional[str]:
        for zone, files in ZONE_FILE_MAP.items():
            for f in files:
                if file_path == f or file_path.startswith(f):
                    return zone
        return None

    @staticmethod
    def is_protected(file_path: str) -> Optional[str]:
        return PROTECTED_FILES.get(file_path)

    def count_active_in_zone(self, zone: str) -> int:
        with self._lock:
            return sum(1 for a in self._agents.values()
                if a.zone == zone and a.status in (AgentStatus.ACTIVE, AgentStatus.REGISTERED))

