---
name: project_structure
description: GPON diagnostic framework project structure and architecture overview
metadata:
  type: project
---

# GPON Diagnostic Framework — Project Structure & Architecture

## Overview
GPON diagnostic framework for Huawei MA5600 series OLTs with CLI, Flask web UI (SSE), FastAPI backend (WebSocket), batch loop runner, and agent orchestration system.

## Project Structure

```
gpon-diag/
├── main.py                    # Thin wrapper → core.cli_diagnosis.main()
├── diagnose.py                # CLI entry point (thin wrapper → core.cli_diagnosis.main())
├── loop_run.py                # Batch/loop runner CLI
├── securecrt_adapter.py       # SecureCRT integration adapter
├── probe_all.py               # Debug script (requires credentials)
├── GPON_class.py              # SecureCRT integration class
├── config.yaml                # Main config: OLT list, thresholds, report settings
├── .env.example               # Env template: GPON_OLT_RADIUS_USERNAME/PASSWORD
├── pyproject.toml             # Python 3.12+, deps: fastapi, flask, sqlalchemy, telnetlib3, pyyaml, python-dotenv
├── uv.lock
│
├── core/                      # Core diagnostic engine
│   ├── __init__.py            # Re-exports all public API
│   ├── models.py              # OntMetrics, LanPort, MacDevice, OntSummary dataclasses
│   ├── engine.py              # Rule-based diagnostic engine (21 rules: 13 DEFAULT + 8 EXTENDED)
│   ├── parser.py              # Huawei CLI output parsers (regex-based)
│   ├── thresholds.py          # Thresholds dataclass from config.yaml
│   ├── report.py              # DiagnosisProblem, DiagnosisReport models
│   ├── reporter.py            # save_report(), save_text_report() with file locking
│   ├── constants.py           # Centralized constants, timeouts, defaults, BAD_VERSIONS
│   ├── utils.py               # Input parsing, credentials, MAC vendor lookup
│   ├── config_parser.py       # load_config(), _build_thresholds()
│   ├── cli_diagnosis.py       # CLI business logic (main entry point)
│   ├── connection_diagnosis.py # OLT connection management, parallel search
│   ├── diagnose_logic.py      # Core diagnosis flow (run_diagnosis())
│   ├── collector.py           # Backward-compat alias for OltConnection
│   ├── data_collector.py      # OntDataCollector: collects ONT data via telnet commands
│   ├── olt.py                 # OltConnection: connection pool + telnet session + data collection
│   ├── telnet_session.py      # TelnetSession: raw socket telnet communication
│   ├── connection_pool.py     # Connection pool (max 2 per OLT) with thread safety
│   ├── loop_runner.py         # LoopRunner, TaskQueue for batch processing
│   ├── threshold_evaluator.py # Threshold evaluation functions
│   ├── crt_stub.py            # SecureCRT API emulation for testing
│   └── adapter.py             # Legacy GPON_class.py adapter
│
├── web/                       # Flask web interface (legacy, SSE-based)
│   ├── app.py                 # Flask app with SSE endpoints, SQLite history
│   ├── templates/
│   │   ├── index.html         # Main diagnosis page
│   │   ├── dashboard.html     # History dashboard
│   │   └── result.html        # Result view
│   └── static/
│       ├── css/               # Stylesheets
│       └── js/                # dashboard.js
│
├── web/api/                   # FastAPI backend (new, WebSocket + REST)
│   ├── main.py                # FastAPI app with lifespan, CORS, static files
│   ├── deps.py                # Dependencies: config, DB, OLT pool
│   ├── exceptions.py          # Exception handlers
│   ├── models.py              # Pydantic request/response schemas
│   ├── schemas/               # Request/response/WS schemas
│   └── routes/                # API route modules:
│       ├── diagnose.py        # POST /api/diagnose
│       ├── optics.py          # GET /api/optics
│       ├── search.py          # POST /api/search
│       ├── actions.py         # POST /api/actions
│       ├── history.py         # GET /api/history
│       ├── port_summary.py    # POST /api/port-summary
│       ├── olts.py            # GET /api/olts
│       ├── health.py          # GET /api/health
│       └── ws.py              # WebSocket endpoints
│
├── data/                      # Runtime data (gitignored)
│
│
│   ├── reports/               # Generated diagnosis reports (JSON + text)
│   ├── incidents/             # Incident storage (reserved)
│   ├── logs/                  # Server logs
│   ├── diagnoses.db           # SQLite history (Flask + FastAPI)
│   ├── oui.txt                # MAC OUI database
│   └── loop_tasks.json        # Loop runner queue
│
├── hermes-lockutils/          # Local file locking library (not pip package)
│   ├── file_lock.py           # Atomic directory-based locking
│   └── file_lock.sh           # Shell wrapper
│
├── tests/
│   ├── test_smoke.py          # Engine smoke tests
│   └── test_loop_runner.py    # Loop runner tests
│
└── scripts/
    ├── check_and_start_server.py  # Health check + Waitress production server
    └── run_server.py              # Waitress server entry point
```

## Key Architectural Decisions

1. **Synchronous sockets in `telnet_session.py`** — Uses `select` + raw sockets (not telnetlib3)
2. **Rule-based engine** — Each rule: `(metrics, thresholds) → DiagnosisProblem|list|None`
3. **Three lookup modes** — F/S/P/ONT address, serial number, or description
4. **Connection pooling** — Max 2 connections per OLT (`connection_pool.py`)
5. **File locking** — `hermes-lockutils/` for thread-safe concurrent report writes
6. **Dual web stack** — Flask (SSE, legacy) + FastAPI (WebSocket, new)
7. **Batch processing** — `loop_run.py` + `LoopRunner` for cyclic diagnosis
8. **SQLite history** — Persistent diagnosis history in `data/diagnoses.db`

## Credentials Setup (Three-tier resolution)

```
1. credential_key from config.yaml → GPON_OLT_<KEY>_USERNAME/PASSWORD
2. Sanitized OLT name → GPON_OLT_<OLT_NAME>_USERNAME/PASSWORD
3. Sanitized host IP → GPON_OLT_<HOST>_USERNAME/PASSWORD
```

Env vars (non-alphanumeric → underscores):
```
GPON_OLT_RADIUS_USERNAME=admin
GPON_OLT_RADIUS_PASSWORD=your_password
```

## Hard Rules (Must Preserve)

| Component | Constraint |
|-----------|------------|
| `core/models.py` → `OntMetrics` | Add fields only via `field(default=…)` at end. No deletions/renames. |
| `core/engine.py` → `DEFAULT_RULES`, `EXTENDED_RULES` | Rule order affects results. New rules only append to `EXTENDED_RULES`. |
| `core/olt.py` → `_olt_registry`, `_read_to_prompt`, `send_command` | Connection pool logic (max 2). Changes break telnet protocol. |
| `core/parser.py` → `PATTERNS` | Regexes parse live Huawei CLI. Must test against real output. |
| `core/diagnose_logic.py` → `run_diagnosis()` | Parser call order and actions are part of the protocol. |
| `.env`, `config.yaml` | Secrets and deploy config. Don't extend `.gitignore`. |

## Rule Engine Conventions

- Offline ONT: only `rule_offline` + `rule_match_state`/`rule_config_state` run
- All other rules guard with `if not metrics.is_online: return None`
- Rule signature: `def rule_*(metrics: OntMetrics, t: Thresholds) -> DiagnosisProblem|list|None`
- After adding a rule, run `uv run python -m tests.test_smoke`
- Diagnostic messages in **Russian**; code/comments in **English**

## Huawei Telnet Protocol Notes

- `display ont optical-info` requires `interface gpon F/S` context → `_gpon_ctx()` / `_quit_gpon()`
- Long output pagination (`---- More ----`) handled via `send_command(max_more=…)`
- Distance uses `ONT distance(m)`, fallback to `ONT last distance(m)` when value is `-`
- Optical params from `display ont optical-info` only: `ont_rx_power`, `olt_rx_power`, `ont_tx_power`, `laser_bias_current`, `ont_temperature`, `supply_voltage`, `module_subtype`