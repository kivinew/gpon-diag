# File Locking Skill (Copy)

Provides atomic file locking via directory-based locks (`<file>.lock`) to prevent race conditions when multiple agents or processes access shared files concurrently.

## When to Use

Use this skill when:
- Two or more agents/processes need to read/write the same file
- You need to prevent data corruption from concurrent modifications
- Working with shared state files (JSON, YAML, databases, logs, etc.)

## Mechanism

The locking uses **atomic directory creation** (`mkdir` / `os.mkdir`) as the coordination primitive:
- Creating a directory is atomic on POSIX and Windows filesystems
- If `<file>.lock` already exists, the lock is held — retry with backoff
- Lock is released by removing the directory

## Usage

### Bash

```bash
#!/usr/bin/env bash
# Source the lock functions
source /path/to/hermes-lockutils/file_lock.sh

# Acquire lock (blocks with retry until acquired)
lock_file "/path/to/shared/data.json"

# Critical section — safe to modify the file
echo "processed" >> "/path/to/shared/data.json"

# Release lock
unlock_file "/path/to/shared/data.json"
```

**Always** use `trap` for safety:

```bash
#!/usr/bin/env bash
source /path/to/hermes-lockutils/file_lock.sh

TARGET="/path/to/shared/data.json"
lock_file "$TARGET"
trap 'unlock_file "$TARGET"' EXIT

echo "processed" >> "$TARGET"
```

### Python

```python
from file_lock import lock_file, unlock_file

lock_file("/path/to/shared/data.json")
try:
    with open("/path/to/shared/data.json", "a") as f:
        f.write("processed\n")
finally:
    unlock_file("/path/to/shared/data.json")
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `LOCK_TIMEOUT` | 30 (bash) / 30 (python) | Max seconds to wait for lock |
| `LOCK_RETRY_INTERVAL` | 0.1 | Seconds between retries |
| `LOCK_MAX_RETRIES` | 300 | Max retry attempts (python) |

## Pitfalls and Considerations

1. **Stale locks**: If a process crashes without releasing, the `.lock` directory persists. Add staleness detection (check lock age via `stat` / `os.stat` on the lock directory's mtime).
2. **Timeout**: Without a timeout, a dead process holding a lock blocks others forever. Always set reasonable timeouts.
3. **Nested locking**: Lock files in a consistent global order to prevent deadlocks.
4. **Cleanup on exit**: Always use `trap ... EXIT` (bash) or `try/finally` (python) to guarantee cleanup.
5. **NFS / network filesystems**: `mkdir` atomicity is NOT guaranteed on NFS v2/v3. Use local filesystems or a proper distributed lock (Redis, etcd).
6. **Lock directory naming**: The lock path is `<target_file>.lock`. Do NOT create files named `<target>.lock` manually.

## Shared Lock Directory

Place `file_lock.sh` and `file_lock.py` in a shared location accessible to all agents:

```
/path/to/hermes-lockutils/
  file_lock.sh
  file_lock.py
```

All agents should `source` (bash) or `import` (python) from this shared path.
