---
name: flask-server-fix
description: Procedure for fixing Flask/Waitress import errors and missing dotenv in the GPON diagnostic web server
source: auto-skill
extracted_at: '2026-06-24T23:09:30.636Z'
---

## Problem
The production server (`scripts/run_server.py` launched via `scripts/check_and_start_server.py`) repeatedly crashed with:
- `ModuleNotFoundError: No module named 'flask'`
- `ModuleNotFoundError: No module named 'dotenv'`
- `TypeError: 'module' object is not callable` from Waitress, indicating that a module was passed instead of the Flask app instance.

## Root causes
1. **Incorrect import** – `run_server.py` used `from web import app`, which imported the *module* `web.app` rather than the Flask instance defined inside it.
2. **Missing PYTHONPATH entries** – the launched process only had the virtual‑env `site‑packages` directory on `PYTHONPATH`, so the project root (where `web` lives) was not discoverable for imports.
3. **Unprotected `dotenv` import** – `diagnose.py` unconditionally imports `load_dotenv`, causing a `ModuleNotFoundError` when the package is unavailable.

## Fixes applied
1. **Add project root to PYTHONPATH** in `scripts/check_and_start_server.py` before spawning the server, ensuring local modules can be imported.
2. **Correct Flask import** in `scripts/run_server.py`:
   ```python
   from web.app import app as flask_app
   app = flask_app
   ```
   This guarantees the WSGI callable is a Flask `app` object, not a module.
3. **Guard dotenv import** – wrap the `load_dotenv` import in `run_server.py` (and optionally in `diagnose.py`) so the server can start even when `python-dotenv` is not installed.
4. **Guard missing Flask** – the server now fails gracefully if Flask is not installed, allowing the script to report the error without crashing the whole process.
5. **Start server with Waitress** – unchanged, but now the WSGI callable is correct, preventing `TypeError: 'module' object is not callable`.

## Verification steps
1. Run `python scripts/check_and_start_server.py`.
2. Observe the log (`data/logs/server.log`) – it should show the Flask dev server starting without import errors and handling requests (`GET /`, `POST /api/diagnose`).
3. Ensure no `ModuleNotFoundError` for `flask` or `dotenv` appears.
4. Confirm Waitress receives a proper callable (`app`) and does not raise `TypeError`.

## When to reuse
Whenever the project adds new entry‑point scripts or changes the module layout, repeat steps 1‑3 to keep the PYTHONPATH and imports consistent. If `dotenv` is later required, reinstall the package or add a guarded import.
