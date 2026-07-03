---
name: refactoring_plan
description: Refactoring plan for GPON diagnostic framework - architecture improvements, technical debt, and modernization
metadata:
  type: project
---

# Refactoring Plan — GPON Diagnostic Framework

## Context
This project has grown organically with multiple overlapping components (Flask + FastAPI, sync telnet, agent orchestration). The refactoring plan prioritizes stability, maintainability, and modernization while preserving critical telnet protocol logic.

---

## Phase 1: Foundation & Stability (High Priority)

### 1.1 Consolidate Web Stack
**Problem**: Two web frameworks coexist — Flask (`web/app.py`) with SSE and FastAPI (`web/api/`) with WebSocket. Both share SQLite history but have different routing, templates, and deployment paths.

**Plan**:
- **Migrate Flask SSE endpoints to FastAPI WebSocket** — SSE is unidirectional; WebSocket provides bidirectional real-time logs
- **Unify history models** — FastAPI uses Pydantic + SQLAlchemy async; Flask uses sync SQLAlchemy. Choose async SQLAlchemy 2.0
- **Deprecate `web/app.py`** — Keep templates for reference, serve React SPA from FastAPI static files
- **Single entry point** → `uv run python -m web.api.main` (port 8000)

**Files to modify**:
- `web/api/main.py` — add WebSocket log streaming endpoint
- `web/api/routes/ws.py` — new WebSocket route for diagnosis logs
- `web/api/routes/diagnose.py` — adapt to WebSocket streaming
- `scripts/check_and_start_server.py` — update to launch FastAPI + Waitress/Uvicorn

### 1.2 Connection Pool Hardening
**Problem**: `core/connection_pool.py` uses global `_olt_registry` dict with thread lock. Issues:
- No health checks on pooled connections
- `OltConnection` wraps `TelnetSession` via delegation properties — fragile
- `_skip_disconnect` circuit breaker not fully integrated with pool

**Plan**:
- Add `health_check()` method to `TelnetSession` (send `display version`, verify prompt)
- Pool should validate connections before handoff
- Implement connection lifecycle: `acquire()` → `validate()` → `release()` / `discard()`
- Add metrics: connection age, command count, error rate

**Files**: `core/telnet_session.py`, `core/connection_pool.py`, `core/olt.py`

### 1.3 Eliminate Delegation Anti-pattern in `OltConnection`
**Problem**: `OltConnection` (in `core/olt.py`) exposes 20+ property delegations to `TelnetSession` (`_sock`, `_connected`, `_last_used`, etc.) — violates encapsulation, makes testing hard.

**Plan**:
- Make `OltConnection` a proper facade: compose `TelnetSession` + `OntDataCollector` internally
- Expose only high-level methods: `connect()`, `disconnect()`, `collect_ont()`, `send_command()`, `get_olt_info()`
- Remove all `_sock`, `_connected`, `_banner` property delegations
- `TelnetSession` becomes private implementation detail

---

## Phase 2: Architecture & Separation of Concerns (Medium Priority)

### 2.1 Split `OntDataCollector` from Telnet Layer
**Problem**: `OntDataCollector` (in `core/data_collector.py`) directly calls `session.send_command()` and `session._gpon_ctx()` — tightly coupled to telnet protocol.

**Plan**:
- Define `OLTProtocol` interface (abstract base class) with methods:
  - `send_command(cmd: str, max_more: int) -> str`
  - `enter_gpon_context(frame: str, slot: str) -> None`
  - `exit_gpon_context() -> None`
  - `drain_socket() -> None`
- `TelnetSession` implements `OLTProtocol`
- `OntDataCollector` depends on `OLTProtocol`, not concrete `TelnetSession`
- Enables: SSH implementation, mock protocol for testing, future gNMI/NETCONF

**Files**: New `core/protocol.py`, modify `core/telnet_session.py`, `core/data_collector.py`

### 2.2 Modernize Configuration System
**Problem**: Config scattered across `config.yaml`, `constants.py` (`DEFAULT_THRESHOLDS`), `thresholds.py` dataclass, `config_parser.py` mapping.

**Plan**:
- Single source of truth: Pydantic Settings (`pydantic-settings`)
- `Settings` class loads from `config.yaml` + environment variables
- Thresholds become nested Pydantic model with validation
- Remove `THRESHOLD_KEY_MAP` and `_build_thresholds()` — direct mapping
- Type-safe access: `settings.thresholds.ont_rx_power_warn_dbm`

**Files**: New `core/config.py`, deprecate `constants.py` defaults, `thresholds.py`, `config_parser.py`

### 2.3 Async-First Core (Long-term)
**Problem**: Entire stack is synchronous (telnet, diagnosis, loop runner). Blocks event loop in FastAPI.

**Plan**:
- Wrap telnet operations in `asyncio.to_thread()` for FastAPI endpoints
- `LoopRunner` → use `asyncio.Subprocess` instead of `subprocess.run()`
- `DiagnosticEngine.diagnose()` is CPU-bound — keep sync but run in thread pool
- Gradual migration: endpoints first, then collector, then diagnosis flow

---

## Phase 3: Code Quality & Testing (Medium Priority)

### 3.1 Parser Test Suite with Real Huawei Output
**Problem**: `core/parser.py` regexes tested only via smoke tests. No corpus of real CLI output for regression testing.

**Plan**:
- Create `tests/fixtures/huawei_outputs/` with real (sanitized) CLI captures:
  - `display ont info`
  - `display ont optical-info`
  - `display statistics ont-line-quality`
  - `display ont port state`
  - `display ont wan-info`
  - `display ont register-info`
  - `display ont info summary`
  - `display version`, `display uptime`
- Add parametrized tests: `test_parser.py` with `@pytest.mark.parametrize` over fixtures
- CI: run parser tests on every change to `PATTERNS`

### 3.2 Type Hints & MyPy Strictness
**Current**: `disallow_untyped_defs = false` in `pyproject.toml`

**Plan**:
- Enable `disallow_untyped_defs = true` incrementally per module
- Add type stubs for `hermes-lockutils`
- Fix `OntMetrics` dataclass: many `dict`/`list` fields need `Dict[str, int]`, `List[LanPort]`
- Use `TypedDict` for `wan_connections`, `ping_result`, `eth_errors`

### 3.3 Rule Engine Extensibility
**Problem**: Rules are hardcoded functions in `engine.py`. Adding rules requires code change + rebuild.

**Plan**:
- Rule registry with entry points or config-driven registration
- Rules as dataclasses: `RuleConfig(name, check_fn_path, category, enabled, params)`
- Load from `config.yaml` under `diagnostic_rules:` section
- Hot-reload support for development

---

## Phase 4: Operational Excellence (Lower Priority)

### 4.1 Structured Logging & Observability
**Current**: `logging.basicConfig(level=WARNING)` in CLI, scattered `logger.debug/info/warning`

**Plan**:
- JSON structured logging with `structlog` or `python-json-logger`
- Correlation IDs for request tracing (CLI + Web)
- Metrics: Prometheus `/metrics` endpoint (diagnosis count, latency, errors, OLT health)
- Health checks: `/api/health` already exists, extend with OLT connectivity

### 4.2 Database Migrations
**Current**: `db.create_all()` in Flask + FastAPI — no migrations.

**Plan**:
- Add Alembic (already in `pyproject.toml`)
- Initial migration from current schema
- Versioned migrations for future schema changes
- Separate migration env for Flask vs FastAPI (same DB)

### 4.3 CI/CD Pipeline
**Current**: No CI configuration visible.

**Plan**:
- GitHub Actions workflow:
  - `ruff check .` + `ruff format --check .`
  - `mypy --strict core/`
  - `pytest tests/ -v`
  - Build Docker image
  - Deploy to staging on merge to main

---

## Risk Assessment

| Change | Risk | Mitigation |
|--------|------|------------|
| Web stack consolidation | High — SSE clients may break | Run both in parallel during transition; feature flag |
| Connection pool rewrite | High — telnet protocol fragile | Extensive integration tests with real OLT; canary deploy |
| Protocol abstraction | Medium — internal refactor | Keep `TelnetSession` unchanged; new interface only |
| Pydantic Settings | Low — config loading isolated | Dual-load during transition (old + new), compare results |
| Async migration | Medium — blocking calls | Thread pool executor; gradual per-endpoint |

---

## Quick Wins (Do First)

1. ✅ **Add parser test fixtures** — zero risk, high value
2. ✅ **Enable stricter MyPy per module** — incremental
3. ✅ **Add correlation IDs to logs** — minimal code change
4. ✅ **Document Huawei CLI output format** — in `parser.py` docstrings
5. ✅ **Remove duplicate `BAD_VERSIONS` in `constants.py`** (lines 71-77 and 82-88)

---

## Dependencies Between Phases

```
Phase 1.1 (Web consolidation) 
    → enables Phase 1.2 (Pool hardening for FastAPI)
    → enables Phase 2.1 (Protocol abstraction for testing)

Phase 2.2 (Pydantic config) 
    → independent, can start anytime
    → required for Phase 3.3 (Config-driven rules)

Phase 2.1 (Protocol abstraction)
    → enables Phase 2.3 (Async telnet)
    → enables SSH implementation
```

---

## File Ownership Map (for Agent Zone Locking)

```
ZONE_PARSER:     core/parser.py, tests/fixtures/huawei_outputs/
ZONE_ENGINE:     core/engine.py, core/threshold_evaluator.py
ZONE_MODEL:      core/models.py, core/report.py
ZONE_CONNECTION: core/telnet_session.py, core/connection_pool.py, core/olt.py, core/data_collector.py
ZONE_REPORT:     core/reporter.py, data/reports/
ZONE_WEB:        web/api/, web/templates/, web/static/
ZONE_CLI:        diagnose.py, loop_run.py, core/cli_diagnosis.py, core/connection_diagnosis.py
ZONE_CONFIG:     config.yaml, core/config.py (new), core/constants.py, core/thresholds.py, core/config_parser.py
```

> **Note**: This refactoring plan is a living document. Update as priorities shift. Link related memories: [[project_structure]]