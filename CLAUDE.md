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

# Run web interface
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
├── core/engine.py    → Rule-based diagnostic engine (13 default + 8 extended rules)
├── core/thresholds.py → Diagnostic thresholds configuration
├── core/report.py    → DiagnosisProblem, DiagnosisReport models
└── core/reporter.py  → save_report(), save_text_report()
```

## Key Design Decisions

1. **Synchronous sockets in `olt.py`** — Uses `select` and raw sockets for telnet control.

2. **Rule-based engine** — Each rule is a `(metrics, thresholds) -> DiagnosisProblem|None` function.

3. **SecureCRT integration** — `crt_stub.py` emulates SecureCRT's API; `GPON_class.py` integrates with real SecureCRT.

4. **Credentials via env vars** — `GPON_OLT_<OLT_NAME>_USERNAME/PASSWORD` (e.g., `GPON_OLT_40_111_USERNAME`).

5. **Three lookup modes** — F/S/P/ONT address, serial number, or description.

## File Locking Integration

The `hermes-lockutils/file_lock.py` is integrated in `core/reporter.py` for thread-safe concurrent report writes using atomic directory-based locks. See AGENTS.md for complete documentation.