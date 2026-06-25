---
name: flask-server-monitor
description: Monitor Flask/Waitress server, diagnose failures from logs, clean up stale processes, and launch it in background with correct environment.
source: auto-skill
extracted_at: '2026-06-25T02:00:00Z'
---

## Overview
This skill automates the routine of ensuring that the Flask/Waitress server for the GPON diagnostic tool is running correctly.

### Steps
1. **Detect running server** – Use `netstat -ano` to look for any process listening on port **5000**. If a LISTENING entry is found, the server is considered running.
2. **If not running, inspect recent log entries** – Open `data/logs/server.log` and fetch the last 20 lines, filtering for lines containing `ERROR` or `Traceback`. This gives a quick diagnostic of why the previous run failed (e.g., missing dependencies, import errors).
3. **Terminate stale processes** –
   * Kill any lingering Flask development server processes by `taskkill` with a filter on `WINDOWTITLE eq Flask*`.
   * Scan `netstat -ano` for any other processes still bound to port 5000 and terminate them with `taskkill /PID <pid> /F` (excluding the current script’s PID).
4. **Prepare environment** – Build a clean `PYTHONPATH` that includes the project root and the virtual‑environment's `site‑packages` directory, preserving any existing `PYTHONPATH` entries.
5. **Start the server** – Launch `scripts.run_server.py` as a background process using the virtual‑environment interpreter:
   ```
   E:/.../gpon-diag/.venv/Scripts/python.exe -u -m scripts.run_server
   ```
   The process is started with `creationflags=0x08000000` to run without opening a console window, and its stdout/stderr are redirected to `data/logs/server.log`.
6. **File locking** – Before starting the server, acquire a lock file (`gpon_server.lock` in the system temp directory) via the Hermès `file_lock` utility to avoid race conditions when multiple agents attempt to start the server simultaneously. Release the lock after the subprocess is spawned.

### Result
After execution, the server will be running under Waitress, listening on port 5000, and ready to serve the API (`/ping`, `/api/diagnose`, etc.). Any previous errors are recorded in the log for later review.

---

## Usage
Invoke this skill whenever you need to guarantee that the diagnostic web service is up:
```bash
python scripts/check_and_start_server.py
```
The script will automatically handle detection, diagnostics, cleanup, and background launch.
