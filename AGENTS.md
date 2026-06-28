# AGENTS.md

Instructions for AI agents working with the GPON Diagnostic Framework codebase.
Goal: parallel work by multiple agents without breaking architecture or logic.

---

## 1. Hard Rules

### 1.1. DO NOT TOUCH without explicit user request

| What | Why |
|------|-----|
| `core/models.py` → `OntMetrics` | Single data contract for parser, engine, report. Adding field — only via `field(default=…)` at end of dataclass. Deletion/renaming — **forbidden** until all consumers updated. |
| `core/engine.py` → `DEFAULT_RULES`, `EXTENDED_RULES` | Rule order affects result. New rule — only append to end of list. Do not reorder, do not delete existing. |
| `core/olt.py` → `OltConnection`, `_olt_registry` | Singleton registry. Changing connection logic — **only** during refactor with full testing. Do not add parallel connections to one OLT. |
| `core/parser.py` → `PATTERNS` | Regexes parse live Huawei CLI output. Minor regexp change → silent parse break. Any change — test with real output. |
| `diagnose.py` → `run_diagnosis()` | Main pipeline. Order of parser calls and actions (error clear, ping) — part of diagnostic protocol. Do not change without understanding consequences. |
| `.env`, `.gitignore`, `config.yaml` | Secrets and deploy config. Do not create new `.env` files, do not extend `.gitignore` for files needed by other agents. |

### 1.2. Mandatory Code Requirements

1. **Import sorting**: stdlib → third-party → local (`core.*`). Blank line between groups.
2. **Typing**: all public functions and methods — with type annotations.
3. **UTF-8 encoding**: all files — with `# -*- coding: utf-8 -*-` header if Cyrillic present (optional if none).
4. **Logging**: via `logging.getLogger(__name__)`, not `print()` in library code. `print` allowed only in CLI entry (`diagnose.py:main()`).
5. **Exceptions**: no silent `except Exception: pass`. Minimum — `logger.warning()`. In engine rules — wrap in try/except, log, return `None` (see `DiagnosticEngine.diagnose`).
6. **Sentinel strings**: `"-"`, `""`, `-1`, `-999`, `999.0` — these are sentinel values in `OntMetrics`. Check strictly per existing logic, do not replace with `None`/`0`.

### 1.3. Forbidden Actions

- **Cosmetic refactoring**: do not rename variables, change indent style, add type stubs "for cleanliness".
- **Delete "dead" code** without answering: is it used in SecureCRT branch (`GPON_class.py`, `crt_stub.py`)?
- **Merge/split files** in `core/` — current structure works stably.
- **Add new dependencies** to `pyproject.toml` without agreement.
- **Commit and push** without explicit user request.
- **Write reports concurrently without file locking** — use `hermes-lockutils/file_lock.py` (see §4).

### 1.4. File Locking (Mandatory)

- **All concurrent writes to `data/reports/` MUST use `hermes-lockutils.file_lock`** (atomic directory-based lock).
- Import: `from hermes_lockutils.file_lock import lock_file, unlock_file`
- Pattern:
  ```python
  lock_path = "/tmp/gpon_report.lock"
  lock_file(lock_path)
  try:
      save_text_report(report, "data/reports")
  finally:
      unlock_file(lock_path)
  ```
- Do NOT implement custom locking (flock, fcntl, portalocker, etc.). The project uses `hermes-lockutils` — it is the single source of truth.
- This applies to: `core/reporter.py::save_text_report`, `core/reporter.py::save_report`, any script writing to `data/reports/`.

---

## 2. Architecture & Responsibility Zones

```
diagnose.py          → CLI + orchestration (entry point)
├── core/olt.py      → Telnet connection to OLT (singleton registry)
├── core/parser.py   → Huawei CLI output → OntMetrics
├── core/models.py   → Data structures (OntMetrics, LanPort, MacDevice)
├── core/engine.py   → Diagnostic engine (rules)
├── core/thresholds.py → Thresholds (dataclass from config.yaml)
├── core/report.py   → DiagnosisProblem, DiagnosisReport models + to_text()/to_dict()
├── core/reporter.py → Report file saving + file locking
├── core/crt_stub.py → SecureCRT API emulation (for tests)
├── core/adapter.py  → SecureCRT ↔ core adapter
├── core/collector.py → Data collection wrapper
├── web/app.py       → Flask web interface
└── GPON_class.py    → Legacy SecureCRT integration
```

### Rule: one agent — one zone

| Zone | Files | What you can do |
|------|-------|-----------------|
| **Parser** | `core/parser.py` | Add regex to `PATTERNS`, add `parse_*` functions. Do not change existing regex without test on real output. |
| **Engine** | `core/engine.py` | Add rules to end of `EXTENDED_RULES` (touch `DEFAULT_RULES` only after agreement). Do not change `Rule.check(metrics, thresholds)` signature. |
| **Model** | `core/models.py` | Add fields to end of `OntMetrics` with default. Update `to_dict()` in `report.py`. Do not delete or rename fields. |
| **Connection** | `core/olt.py` | Add methods to `OltConnection`. Do not change `_read_to_prompt`, `send_command`, `_gpon_ctx` logic without full telnet protocol understanding. |
| **Report** | `core/report.py`, `core/reporter.py` | Extend `to_text()` / `to_dict()`. Do not remove existing report sections. |
| **Web** | `web/app.py`, `web/templates/*`, `web/static/*` | Free zone, but do not break imports from `core.*`. |
| **CLI** | `diagnose.py` | Add arguments, extend `main()`. Do not change `run_diagnosis()` without protocol knowledge. |

---

## 3. Project Conventions

### 3.1. Language

- **Diagnostic messages** (rules, report): Russian.
- **Code, comments, docstrings**: English unless otherwise specified.
- **JSON keys** in `to_dict()`: English snake_case.

### 3.2. Style

- Python ≥3.12, dataclasses, type hints.
- Max line length: 120 chars.
- Indentation: 4 spaces.
- Strings: double quotes for f-strings and text, single quotes for dict keys.
- f-strings, `%` and `.format()` — only when necessary.

### 3.3. Huawei Telnet Protocol (SPECIFICS)

- `display ont optical-info` requires `interface gpon F/S` context → `_gpon_ctx()` / `_quit_gpon()`.
- Long output: pagination via `---- More ----`, handled in `send_command(max_more=...)`.
- `_parse_fsp()` accumulates F/S/P and ONT-ID line by line (key-value format) — do not change without understanding.
- Distance: primary `ONT distance(m)`, fallback to `ONT last distance(m)` when value is `-`.
- Optical params: `ont_rx_power`, `olt_rx_power`, `ont_tx_power`, `laser_bias_current`, `ont_temperature`, `supply_voltage`, `module_subtype` — take ONLY from `display ont optical-info`. **DO NOT** use `catv_rx_power`.

### 3.4. Rule Rules

- Rules for **offline** ONT — only `rule_offline` + `rule_match_state` / `rule_config_state`.
- All other rules — only for **online** ONT (`if not metrics.is_online: return None`).