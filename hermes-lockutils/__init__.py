"""Hermes Lock Utilities — atomic file locking for concurrent access."""

from .file_lock import lock_file, unlock_file, is_locked, FileLockError

__all__ = ["lock_file", "unlock_file", "is_locked", "FileLockError"]