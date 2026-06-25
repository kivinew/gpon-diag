---
name: server-monitor-procedure
description: Procedure to monitor, diagnose, and restart the GPON web server if it stops responding.
source: auto-skill
extracted_at: '2026-06-25T08:45:00.000Z'
---

## Overview
This skill provides a reusable procedure for ensuring that the Flask/Waitress based GPON diagnostic web server is always running and responsive. It combines port checking, log inspection, cleanup of stale processes, and background startup.

## Steps
1. **Check if the server is listening**
   - Run `netstat -ano` and look for a line containing `0.0.0.0:5000` (or `[::]:5000`) with the state `LISTENING`.
   - If such a line is found, the server is considered *running*.
2. **If not running, inspect the log**
   - Read the last 20 lines of `data/logs/server.log`.
   - Extract any lines containing `ERROR` or `Traceback` and report them as the cause of the failure.
3. **Terminate stale processes**
   - Kill any leftover Flask development server processes:
     ```
     taskkill /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq Flask*" /F
     ```
   - Kill any process still bound to port 5000 (excluding the current script):
     ```python
     out = subprocess.check_output(["netstat", "-ano"], text=True)
     for line in out.splitlines():
         if ("0.0.0.0:5000" in line or "[::]:5000" in line) and "LISTENING" in line:
             pid = line.split()[-1]
             if pid != str(os.getpid()):
                 subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
     ```
4. **Start the server in background**
   - Build an environment with the correct `PYTHONPATH` (project root + virtual‑env `site‑packages`).
   - Use the virtual‑env python interpreter to run the server module:
     ```
     subprocess.Popen([
         "<project>/.venv/Scripts/python.exe",
         "-u", "-m", "scripts.run_server"
     ], env=env, creationflags=0x08000000,
        stdout=open(os.path.join("data", "logs", "server.log"), "a", encoding="utf-8"),
        stderr=subprocess.STDOUT)
     ```
   - Acquire a file lock (`gpon_server.lock`) before spawning to avoid race conditions.
5. **Report outcome**
   - If the server was already running, output `Server already running`.
   - If the server was started, output `Start command issued` after launching.

## Reuse
- Call this procedure from any automation loop (`/loop`) that needs to guarantee the web UI is up.
- Integrate it into CI/CD pipelines to verify the service starts after deployment.
- Adjust the port number in the netstat checks if the configuration changes.

## Dependencies
- Windows `netstat` and `taskkill` utilities.
- Python `subprocess`, `os`, and optional `file_lock` for atomic startup.
- A functional virtual environment with Flask, Waitress, and python‑dotenv installed.

## Notes
- The check uses a *single* listening socket as sufficient; multiple entries indicate stray processes and will be cleaned up.
- Guard the `dotenv` import in both `diagnose.py` and `run_server.py` to prevent crashes when the package is missing.
- Ensure the lock file is released even if the server fails to start, using a `finally` block.
