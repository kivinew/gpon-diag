# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Run smoke tests (no OLT connection required)
uv run python -m tests.test_smoke

# Run diagnosis on an ONT
uv run diagnose.py 0/1/3/9                    # Auto-detect OLT
uv run diagnose.py 0/1/3/9 --olt "OLT-17.232" # Specific OLT
uv run diagnose.py 4857544312E0E379            # By serial number
uv run diagnose.py fl_12345                  # By description

# Output options
uv run diagnose.py 0/1/3/9 --json         # JSON output
uv run diagnose.py 0/1/3/9 --no-save     # Skip saving report
uv run diagnose.py 0/1/3/9 --no-actions  # Diagnostics without resets/clears
uv run diagnose.py 0/1/3/9 --only-optics # Only check optics (powers + BIP)

# Run loop runner for batch diagnosis
uv run loop_run.py --file onts.txt --olt "OLT-17.232" --loops 50
uv run loop_run.py --csv subscribers.csv --olt "OLT-40.111" --column address

# Run web interface (Flask + SSE)
uv run python -m web.app

# Test telnet connection
uv run python test_telnet.py
```

## Architecture

This is a GPON diagnostic framework for Huawei MA5600 series OLTs. The architecture separates concerns:

```
diagnose.py           → CLI entry point, orchestrates diagnosis flow
├── core/olt.py       → OltConnection: telnet-based OLT connection manager (singleton)
├── core/parser.py    → CLI output parsers → OntMetrics
├── core/models.py    → OntMetrics, LanPort, MacDevice dataclasses
├── core/engine.py    → Rule-based diagnostic engine (21 rules: 13 default + 8 extended)
├── core/thresholds.py → Diagnostic thresholds configuration
├── core/report.py    → DiagnosisProblem, DiagnosisReport models
├── core/reporter.py  → save_report(), save_text_report()
├── core/collector.py → Data collection from OLT
├── core/adapter.py   → Adapter for GPON_class.py (legacy)
├── core/loop_runner.py → Batch/loop task runner
└── core/crt_stub.py  → SecureCRT API emulation for testing
```

**Web Interface (Flask + SSE):**
```
web/app.py            → Main Flask app with SSE endpoints
web/templates/        → HTML templates (index.html, dashboard.html, result.html)
web/static/js/        → dashboard.js, orchestrator.js
web/static/css/       → Stylesheets
```

**Orchestrator (Agent Management):**
```
orchestrator/agent_registry.py → Agent registration & zone locking
orchestrator/lock_manager.py   → File/zone locking
orchestrator/validator.py      → Code validation
orchestrator/outer_loop.py     → External control loop
orchestrator/task_card.py      → Task management
```

## Key Design Decisions

1. **Synchronous sockets in `olt.py`** — Uses `select` and raw sockets for telnet control.

2. **Rule-based engine** — Each rule is a `(metrics, thresholds) -> DiagnosisProblem|None` function.

3. **SecureCRT integration** — `crt_stub.py` emulates SecureCRT's API; `GPON_class.py` integrates with real SecureCRT.

4. **Credentials via env vars** — `GPON_OLT_<OLT_NAME>_USERNAME/PASSWORD` (e.g., `GPON_OLT_40_111_USERNAME`).

5. **Three lookup modes** — F/S/P/ONT address, serial number, or description.

6. **File Locking Integration** — `hermes-lockutils/file_lock.py` integrated in `core/reporter.py` for thread-safe concurrent report writes using atomic directory-based locks.

7. **Batch Processing** — `loop_run.py` + `core/loop_runner.py` for cyclic diagnosis of ONT lists.

8. **Web Real-time Logs** — Server-Sent Events (SSE) for live diagnosis progress in browser.

9. **SQLite History** — Persistent diagnosis history in `data/diagnoses.db` with SQLAlchemy.

## Project Structure

```
gpon-diag/
├── config.yaml           # OLT list, thresholds, report settings
├── diagnose.py           # Main CLI entry point
├── loop_run.py           # Batch/loop runner CLI
├── securecrt_adapter.py  # SecureCRT adapter
├── probe_all.py          # Debug script (requires credentials)
├── GPON_class.py         # SecureCRT integration class
├── core/
│   ├── __init__.py
│   ├── olt.py            # Telnet connection manager
│   ├── parser.py         # CLI output parsers
│   ├── models.py         # Data models (dataclasses)
│   ├── engine.py         # Diagnostic rule engine
│   ├── thresholds.py     # Threshold configuration
│   ├── report.py         # Report models
│   ├── reporter.py       # Report persistence
│   ├── collector.py      # Data collection
│   ├── adapter.py        # Legacy adapter
│   ├── crt_stub.py       # SecureCRT stub
│   └── loop_runner.py    # Batch task runner
├── web/
│   ├── app.py            # Flask app with SSE
│   ├── static/
│   │   ├── css/
│   │   └── js/
│   └── templates/
│       ├── index.html
│       ├── dashboard.html
│       └── result.html
├── orchestrator/
│   ├── __init__.py
│   ├── agent_registry.py
│   ├── lock_manager.py
│   ├── validator.py
│   ├── outer_loop.py
│   └── task_card.py
├── data/
│   ├── reports/          # Generated reports
│   ├── incidents/        # Incident storage (reserved)
│   ├── logs/             # Server logs
│   ├── diagnoses.db      # SQLite history
│   ├── oui.txt           # MAC OUI database
│   └── loop_tasks.json   # Loop runner queue
├── hermes-lockutils/
│   ├── file_lock.py      # Atomic file locking
│   └── file_lock.sh      # Shell wrapper
├── tests/
│   └── test_smoke.py     # Engine smoke tests
├── scripts/
│   ├── check_and_start_server.py  # Server health check + start
│   └── run_server.py              # Waitress production server
├── .env.example          # Env template
├── pyproject.toml
└── uv.lock
```

## Configuration

Main config: `config.yaml`

```yaml
olts:
  - name: "OLT-17.232"
    host: "172.16.17.232"
    port: 23
    credential_key: "RADIUS"

thresholds:
  ont_rx_power_warn_dbm: -26.5
  ont_rx_power_crit_dbm: -30.0
  # ... more thresholds

bad_versions:
  - "V1R003C00S108"
  - "V1R006C00S130"

report:
  format: "text"
  save_to_file: true
  reports_dir: "data/reports"
```

## Credentials Setup

Never store passwords in files. Use environment variables:

```powershell
# For OLT named "OLT-17.232" (non-alphanumeric → underscore)
$env:GPON_OLT_17_232_USERNAME="admin"
$env:GPON_OLT_17_232_PASSWORD="your_password"

# Or use .env file (auto-loaded):
GPON_OLT_RADIUS_USERNAME=admin
GPON_OLT_RADIUS_PASSWORD=your_password
```

## Development

### Running Tests
```bash
uv run python -m tests.test_smoke
```

### Adding Diagnostic Rules
Edit `core/engine.py` — add new rule functions and register in `create_default_engine()` or `create_extended_engine()`.

### Web Interface
```bash
uv run python -m web.app
# Opens http://localhost:5000
```

### Production Server
```bash
uv run python scripts/check_and_start_server.py
# Uses Waitress on port 5000, managed via file lock
```

## Security

- ✅ Environment variables for credentials
- ✅ Input validation (only digits for F/S/P/ONT)
- ✅ Error logging
- ✅ `.gitignore` excludes secrets and reports
- ⚠️ Telnet is unencrypted — use management VLAN

## Dependencies

- Python 3.12+
- pyyaml — configuration
- python-dotenv — environment variables
- telnetlib3 — telnet client (async)
- Flask + Flask-SQLAlchemy — web interface
- pyperclip — clipboard copy
- waitress — production WSGI server

## License

Private