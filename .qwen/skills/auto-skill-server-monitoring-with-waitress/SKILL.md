---
name: server-monitoring-with-waitress
description: Monitor Flask server, diagnose startup failures, and launch it in background using Waitress and file locking.
source: auto-skill
extracted_at: '2026-06-24T20:16:17.822Z'
---

## Overview
This skill describes how to reliably monitor a Flask web server for the GPON diagnostic project, detect when it is not running, analyse the log for startup errors, and start the server in the background using the **Waitress** WSGI server and a file‑lock to avoid race conditions.

## Steps
1. **Create a wrapper script** (`scripts/run_server.py`) that:
   * Adds the virtual‑environment `site‑packages` directory to `sys.path`.
   * Imports the Flask `app` from `web/app.py`.
   * Serves the app with `waitress.serve(app, host="0.0.0.0", port=5000)`.
2. **Install required packages** in the project's virtual environment:
   * `pip install waitress python-dotenv` (ensure `dotenv` is available).
3. **Update the monitor script** (`scripts/check_and_start_server.py`):
   * Replace the previous `subprocess.Popen` that invoked `-m web.app` with a call to the wrapper script:
   ```python
   env = os.environ.copy()
   venv_bin = r"E:/DOWNLOADS/CREATIVE/PYTHON/GitHub/gpon-diag/.venv/Scripts"
   env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
   subprocess.Popen(
       [
           "E:/DOWNLOADS/CREATIVE/PYTHON/GitHub/gpon-diag/.venv/Scripts/python.exe",
           "scripts/run_server.py",
       ],
       env=env,
       stdout=open(os.path.join("data", "logs", "server.log"), "a", encoding="utf-8"),
       stderr=subprocess.STDOUT,
   )
   ```
   * **Do not** use the `creationflags=0x08000000` flag, because it prevents the child process from inheriting the virtual‑environment variables, leading to `ModuleNotFoundError`.
4. **Add file‑locking** around the server start to avoid concurrent launches:
   ```python
   lock_path = os.path.join(os.getenv("TEMP", "."), "gpon_server.lock")
   lock_file(lock_path)
   try:
       # launch subprocess as shown above
   finally:
       unlock_file(lock_path)
   ```
5. **Check if the server is running** before launching:
   * Use `tasklist` to look for `python.exe` processes.
   * Optionally filter by window title if the server is started with a console title.
6. **Diagnose failures** when the server is not running:
   * Read the last 20 lines of `data/logs/server.log` (ignore UTF‑8 errors with `errors="ignore"`).
   * Return any lines containing `ERROR` or `Traceback`.
7. **Verify the server is alive** after launch:
   * Re‑run the `tasklist` check.
   * Confirm the log contains a line similar to `Serving on http://0.0.0.0:5000`.

## Result
Running `python scripts/check_and_start_server.py` now reliably ensures the Flask server is up, automatically fixes missing dependencies, and keeps the process running in the background without debug reloads or missing‑module errors.
