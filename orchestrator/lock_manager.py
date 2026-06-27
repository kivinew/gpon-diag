# -*- coding: utf-8 -*-
"""
Lock Manager — блокировка файлов и зон для ИИ-агентов.

Предоставляет высокоуровневые блокировки поверх hermes-lockutils/file_lock.py
с отслеживанием владельца (agent_id), deadlock detection и timeout.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Dict, Generator, List, Optional

import importlib.util

logger = logging.getLogger(__name__)

_lock_module = None
try:
    _spec = importlib.util.spec_from_file_location("file_lock", "hermes-lockutils/file_lock.py")
    if _spec:
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _lock_module = _mod
except Exception:
    logger.warning("hermes-lockutils not available; using fallback locking")


class LockError(Exception):
    pass


class LockTimeoutError(LockError):
    pass


class LockHeldByOtherError(LockError):
    pass


_LOCK_TIMEOUT = 30.0
_ZONE_LOCK_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "orchestrator", ".zone_locks")


def _ensure_lock_dir():
    os.makedirs(_ZONE_LOCK_DIR, exist_ok=True)


def _lock(resource_id: str, timeout: float = _LOCK_TIMEOUT) -> bool:
    if _lock_module:
        try:
            _lock_module.lock_file(resource_id, timeout)
            return True
        except Exception:
            return False
    lock_path = os.path.join(_ZONE_LOCK_DIR, f"{resource_id}.lock")
    _ensure_lock_dir()
    start = time.time()
    while True:
        try:
            os.mkdir(lock_path)
            return True
        except FileExistsError:
            if time.time() - start >= timeout:
                return False
            time.sleep(0.05)
        except OSError:
            return False


def _unlock(resource_id: str):
    if _lock_module:
        try:
            _lock_module.unlock_file(resource_id)
            return
        except Exception:
            pass
    lock_path = os.path.join(_ZONE_LOCK_DIR, f"{resource_id}.lock")
    try:
        os.rmdir(lock_path)
    except OSError:
        pass
