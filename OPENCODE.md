# GPON Diagnostic Framework — Project Context

## What it does
Diagnoses Huawei MA5600 ONT terminals via Telnet. Collects optical params, line quality, LAN/ETH stats, MAC, WAN, ping, registration history. Runs 21 diagnostic rules. Outputs text or JSON report. Web UI with history (Flask + SSE + SQLite).

## Entry points
| Command | Purpose |
|---------|---------|
| `uv run python -m tests.test_smoke` | Smoke tests (no OLT) |
| `uv run diagnose.py <F/S/P/ONT|SN|desc>` | Run diagnosis |
| `uv run loop_run.py --file onts.txt --loops 50` | Batch diagnosis |
| `uv run python -m web.app` | Flask web (port 5000) |
| `uv run python scripts/check_and_start_server.py` | Production (Waitress) |

## Core architecture
```
diagnose.py → CLI orchestration
  core/olt.py      → Telnet socket pool (max 2/OLT), _gpon_ctx() for optical-info
  core/parser.py   → 21 regexes in PATTERNS → OntMetrics
  core/engine.py   → 21 rules (13 DEFAULT_RULES + 8 EXTENDED_RULES)
  core/models.py   → OntMetrics (dataclass, ~85 fields), LanPort, MacDevice, OntSummary
  core/thresholds.py → Thresholds dataclass (from config.yaml)
  core/report.py   → DiagnosisProblem + DiagnosisReport (to_text/to_dict)
  core/reporter.py → File-saving with hermes-lockutils
web/app.py         → Flask, SSE, SQLite (data/diagnoses.db)
orchestrator/      → Agent task management
```

## Key conventions (from AGENTS.md)
- **Don't touch** without request: `OntMetrics` fields, `DEFAULT_RULES`/`EXTENDED_RULES` order, `OltConnection` logic, `PATTERNS` regexes, `run_diagnosis()` pipeline, `.env`/`config.yaml`
- **Sentinel values**: `999.0` (power), `-1` (distance/cpu/mem), `-999` (temp), `-1.0` (voltage) — check with `>= 900`, `< 0`, `<= -900`, never with `if not x`
- **Offline rules**: only `rule_offline` + `rule_match_state`/`rule_config_state`. All others guard `if not metrics.is_online: return None`
- **Optical data**: ONLY from `display ont optical-info` via `_gpon_ctx()`. Never use `catv_rx_power`.
- **Distance**: primary `ONT distance(m)`, fallback `ONT last distance(m)` when value is `-`
- **Language**: diagnostic messages in Russian, code/comments in English, JSON keys in English snake_case
- **Imports**: stdlib → third-party → core.* (blank line between groups)
- **New fields**: append to end of OntMetrics with `field(default=…)`
- **New rules**: append to end of `EXTENDED_RULES`, add `if not metrics.is_online: return None`
- **Credentials**: `GPON_OLT_<KEY>_USERNAME/PASSWORD` via .env, 3-tier lookup (credential_key → OLT name → host IP)

## Huawei Telnet quirks
- `display ont optical-info` needs `interface gpon F/S` context → `_gpon_ctx()` / `_quit_gpon()`
- Long output pagination `---- More ----` handled in `send_command(max_more=-1|0)`
- F/S/P + ONT-ID parsed from both table format and key-value format

## Important files
| File | Lines | Role |
|------|-------|------|
| `diagnose.py` | 535 | CLI + pipeline |
| `core/olt.py` | 537 | Telnet connection |
| `core/parser.py` | 358 | Huawei CLI parsers |
| `core/engine.py` | 370 | Diagnostic rules |
| `core/models.py` | 121 | Data models |
| `core/report.py` | 260 | Report formatting |
| `core/thresholds.py` | 26 | Threshold dataclass |
| `web/app.py` | 717 | Flask web app |
| `config.yaml` | 140 | 24 OLTs + thresholds |
| `tests/test_smoke.py` | 319 | Smoke tests |
