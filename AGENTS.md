# AGENTS.md

Instructions for agents working with the GPON Diagnostic Framework codebase.
Only repo-specific facts that are easy to get wrong.

---

## Commands

```bash
# Install
uv sync

# Diagnose one ONT
uv run diagnose.py 0/1/3/9
uv run diagnose.py 4857544312E0E379          # by serial
uv run diagnose.py fl_12345                  # by description
uv run diagnose.py 0/1/3/9 --olt "OLT-17.232"  # specific OLT

# Flags: --json --no-save --clipboard --no-actions --only-optics -v

# Batch diagnosis
uv run loop_run.py --file onts.txt --olt "OLT-17.232" --loops 50
uv run loop_run.py --csv subscribers.csv --olt "OLT-40.111" --column address
uv run loop_run.py --status     # show queue

# Smoke tests (no OLT required)
uv run python -m tests.test_smoke

# Web interface (dev)
uv run python -m web.app        # http://localhost:5000

# Web interface (production via Waitress)
uv run python scripts/check_and_start_server.py
```

---

## Credentials

Three-tier resolution in `diagnose.py:_load_olt_credentials`:
1. `credential_key` from `config.yaml` (all OLTs use `RADIUS`) → `GPON_OLT_RADIUS_USERNAME` / `GPON_OLT_RADIUS_PASSWORD`
2. Sanitized OLT name → `GPON_OLT_<NAME>_USERNAME`
3. Sanitized host IP → `GPON_OLT_<HOST>_USERNAME`

`.env` is loaded at startup if present. Never commit it to git.

---

## Architecture

```
diagnose.py              → CLI entry, orchestrates diagnosis flow
├── core/olt.py          → OltConnection: synchronous socket telnet (pool of 2 per host:port)
├── core/parser.py       → Huawei CLI output → OntMetrics (PATTERNS dict)
├── core/models.py       → OntMetrics, LanPort, MacDevice dataclasses
├── core/engine.py       → Rule engine (13 DEFAULT_RULES + 8 EXTENDED_RULES)
├── core/thresholds.py   → Thresholds dataclass from config.yaml sections
├── core/report.py       → DiagnosisProblem, DiagnosisReport + to_text()/to_dict()
├── core/reporter.py     → save_text_report / save_report (uses file locking)
├── core/collector.py    → Data collection wrapper over OltConnection
├── core/loop_runner.py  → Batch/loop task runner (used by loop_run.py)
├── core/adapter.py      → Adapter for GPON_class.py (legacy SecureCRT)
├── core/crt_stub.py     → SecureCRT API stub for testing
│
├── web/app.py           → Flask + SSE + SQLAlchemy (port 5000)
├── scripts/             → run_server.py (Waitress), check_and_start_server.py
│
├── orchestrator/        → Agent management: agent_registry, lock_manager, validator, task_card, external_control
├── hermes-lockutils/    → Local directory, NOT a pip package. Atomic mkdir-based file locking
│
├── loop_run.py          → CLI for batch diagnosis
├── securecrt_adapter.py → Runs diagnosis from SecureCRT, copies result to clipboard
├── probe_all.py         → Debug script (dumps all OLT commands, requires credentials)
├── open-browser.ps1     → browser-act wrapper for persistent browser sessions
├── watchdog.py          → Keeps server alive (checks port 5000, restarts if down)
├── GPON_class.py        → Legacy SecureCRT integration class
│
├── config.yaml          → OLT list, thresholds, bad_versions, report settings
├── data/reports/        → Generated reports (gitignored)
└── tests/test_smoke.py  → All smoke tests (single file)
```

---

## Hard Rules (DO NOT TOUCH without asking)

| What | Why |
|------|-----|
| `core/models.py` → `OntMetrics` | Single data contract. Adding field — only via `field(default=…)` at end. Deletion/renaming forbidden until all consumers updated. |
| `core/engine.py` → `DEFAULT_RULES`, `EXTENDED_RULES` | Rule order affects results. New rule — only append to `EXTENDED_RULES`. Do not reorder, do not delete. |
| `core/olt.py` → `_olt_registry`, `_read_to_prompt`, `send_command`, `_gpon_ctx` | Connection pool logic (dict keyed by `host:port`, max 2 per OLT). Changing these breaks telnet protocol. |
| `core/parser.py` → `PATTERNS` | Regexes parse live Huawei CLI output. Minor change → silent break. Any change must be tested on real output. |
| `diagnose.py` → `run_diagnosis()` | Main pipeline. Parser call order and actions (error clear, ping) are part of the diagnostic protocol. |
| `.env`, `.gitignore`, `config.yaml` | Secrets and deploy config. Do not create new `.env` or extend `.gitignore` for files needed by other agents. |
| `hermes-lockutils/` | Local dir, not pip package. The only locking mechanism for `data/reports/` writes. |

### Mandatory Code Rules

1. **Imports**: stdlib → third-party → `core.*`. Blank line between groups.
2. **Typing**: all public functions/methods — type annotations.
3. **Logging**: `logging.getLogger(__name__)`, not `print()` in library code. `print` only in `diagnose.py:main()`.
4. **Exceptions**: no silent `except Exception: pass`. Minimum — `logger.warning()`. In engine rules — wrap, log, return `None` (`DiagnosticEngine.diagnose`).
5. **Sentinel values**: `"-"`, `""`, `-1`, `-999`, `999.0` — do NOT replace with `None`/`0`.

### Forbidden

- Cosmetic refactoring (rename vars, change indent, add "clean" type stubs).
- Delete code without checking if SecureCRT branch uses it (`GPON_class.py`, `crt_stub.py`).
- Merge/split files in `core/`.
- Add dependencies to `pyproject.toml` without agreement.
- Commit/push without explicit request.

---

## File Locking

`hermes-lockutils/` is a local directory (not pip package). Two import patterns used in codebase:

```python
# Option A: via sys.path (scripts/)
import sys
sys.path.append("hermes-lockutils")
from file_lock import lock_file, unlock_file

# Option B: via importlib (core/reporter.py, orchestrator/lock_manager.py)
import importlib.util
_spec = importlib.util.spec_from_file_location("file_lock", "hermes-lockutils/file_lock.py")
```
All concurrent writes to `data/reports/` MUST use these locks. Do NOT implement custom locking.

---

## Huawei Telnet Protocol

- `display ont optical-info` requires `interface gpon F/S` context → `_gpon_ctx()` / `_quit_gpon()`.
- Long output pagination (`---- More ----`) handled in `send_command(max_more=...)`.
- `_parse_fsp()` accumulates F/S/P and ONT-ID — key-value format.
- Distance: primary `ONT distance(m)`, fallback `ONT last distance(m)` when value is `-`.
- Optical params from `display ont optical-info` ONLY: `ont_rx_power`, `olt_rx_power`, `ont_tx_power`, `laser_bias_current`, `ont_temperature`, `supply_voltage`, `module_subtype`. **DO NOT** use `catv_rx_power`.

---

## Rule Engine Conventions

- Offline ONT: only `rule_offline` + `rule_match_state` / `rule_config_state`.
- All other rules: guard with `if not metrics.is_online: return None`.
- New rules: add to end of `EXTENDED_RULES` list in `core/engine.py`.
- Rule signature: `def rule_*(metrics: OntMetrics, t: Thresholds) -> DiagnosisProblem | list | None`.
- After adding a rule, run `uv run python -m tests.test_smoke`.

---

## Diagnostic Messages

Diagnostic messages in rules and reports: **Russian**. Code, comments, docstrings: **English**.
JSON keys in `to_dict()`: English `snake_case`.

---

## Web Production Server

- Dev: `uv run python -m web.app` (Flask, port 5000)
- Production: `scripts/check_and_start_server.py` (Waitress, port 5000, file-lock managed)
- `watchdog.py` monitors port 5000 and restarts if down (poll every 30s)
- `open-browser.ps1` manages persistent browser-act sessions
