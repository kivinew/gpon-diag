"""File Locking — atomic directory-based locks to prevent race conditions.

Uses mkdir for atomic locking on both POSIX and Windows filesystems.
"""

import os
import time
import errno

LOCK_TIMEOUT = 30
LOCK_RETRY_INTERVAL = 0.1
LOCK_MAX_RETRIES = 300


class FileLockError(Exception):
    """Raised when unable to acquire file lock."""
    pass


def lock_file(filepath: str, timeout: float = None) -> None:
    """Acquire exclusive lock on a file using atomic directory creation.

    Args:
        filepath: Path to the file to lock
        timeout: Max seconds to wait (default: LOCK_TIMEOUT)

    Raises:
        FileLockError: If lock cannot be acquired within timeout
    """
    lock_path = f"{filepath}.lock"
    timeout = timeout or LOCK_TIMEOUT
    start_time = time.time()

    while True:
        try:
            os.mkdir(lock_path)
            return
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise FileLockError(f"Failed to create lock directory: {e}")

        if time.time() - start_time >= timeout:
            raise FileLockError(f"Timeout waiting for lock on {filepath} ( waited {timeout}s )")

        time.sleep(LOCK_RETRY_INTERVAL)


def unlock_file(filepath: str) -> None:
    """Release lock on a file by removing the lock directory.

    Args:
        filepath: Path to the file to unlock
    """
    lock_path = f"{filepath}.lock"
    try:
        os.rmdir(lock_path)
    except OSError:
        pass  # Lock may not exist


def is_locked(filepath: str) -> bool:
    """Check if a file is currently locked.

    Args:
        filepath: Path to check

    Returns:
        True if locked, False otherwise
    """
    lock_path = f"{filepath}.lock"
    return os.path.exists(lock_path)