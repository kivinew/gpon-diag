---
name: olt-file-lock
description: Apply hermes-lockutils file_lock to protect OLT info parsing and shared report writes
source: auto-skill
extracted_at: '2026-06-24T17:36:30.034Z'
---
## Purpose
Ensures that reading/parsing OLT model, version, and uptime, as well as writing diagnostic reports, are performed under an atomic file lock to avoid race conditions.

## Procedure
1. **Import utilities**
   ```python
   from hermes_lockutils.file_lock import lock_file, unlock_file
   import os
   ```
2. **Create a lock path** (use a temporary directory or a dedicated lock folder):
   ```python
   lock_path = os.path.join(os.getenv('TEMP', '.'), 'olt_info.lock')
   ```
3. **Acquire the lock** before any `send_command('display version')` call or before writing a report file:
   ```python
   lock_file(lock_path)
   ```
4. **Execute the critical section** (run the command, parse with regex, or write JSON to `data/reports/...`).
5. **Release the lock** in a `finally` block to guarantee cleanup:
   ```python
   finally:
       unlock_file(lock_path)
   ```

## Where to apply
- `core/olt.py::get_olt_info` – now wrapped with the lock (see updated code).
- Any function that writes to `data/reports/` should follow the same pattern (e.g., `core/reporter.py`).

## Benefits
- Prevents empty or truncated `uptime`, `model`, `version` fields caused by concurrent reads/writes.
- Guarantees consistent diagnostic results across CLI runs and the web UI.
- Aligns with the project‑wide feedback memory *always-use-file-lock-skill*.

## Example snippet (in `core/olt.py`)
```python
lock_path = os.path.join(os.getenv('TEMP', '.'), 'olt_info.lock')
lock_file(lock_path)
try:
    output = self.send_command('display version', max_more=-1)
    # parse model, version, uptime …
finally:
    unlock_file(lock_path)
```

---
*Auto‑generated skill for the GPON Diagnostic Framework.*