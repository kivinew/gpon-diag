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
├── core/olt.py       → OltConnection: telnet-based OLT connection manager (singleton pattern)
├── core/collector.py → (planned) Data collector abstraction
├── core/parser.py    → CLI output parsers → OntMetrics
├── core/models.py    → OntMetrics, LanPort, MacDevice dataclasses
├── core/engine.py    → Rule-based diagnostic engine (13 default + 8 extended rules)
├── core/thresholds.py → Diagnostic thresholds configuration
├── core/report.py    → DiagnosisReport, DiagnosisProblem models
└── core/reporter.py  → save_report(), save_text_report()
```

## Key Design Decisions

1. **Synchronous sockets in `olt.py`** — Uses `select` and raw sockets instead of `telnetlib` for better control over telnet IAC negotiations and async behavior.

2. **Rule-based engine in `engine.py`** — Each rule is a `(metrics, thresholds) -> DiagnosisProblem|None` function. Rules check specific conditions:
   - Offline (die-gasp, LOS, LOFi, wire-down)
   - Low optical power (ONT/OLT Rx/Tx)
   - BIP errors (optical line quality)
   - Bad firmware versions
   - Hardware issues (temperature, voltage, CPU/memory)
   - Configuration state mismatches

3. **SecureCRT integration** — `crt_stub.py` emulates SecureCRT's API for testing. The legacy `GPON_class.py` integrates with actual SecureCRT through `inject_crt()`.

4. **Credential handling** — Credentials come from environment variables: `GPON_OLT_<OLT_NAME>_USERNAME` and `GPON_OLT_<OLT_NAME>_PASSWORD`. Names with special characters use underscores.

5. **Dual ONT lookup** — Supports F/S/P/ONT address, serial number (48575443... format), or description. Serial/description lookups use `display ont info by-sn`/`by-desc` commands.

## Parser Patterns

The `parser.py` uses regex patterns defined in `PATTERNS` dict. Key patterns:
- `ont_rx_power`, `olt_rx_power`, `ont_tx_power` — optical power levels
- `upstream_errors`, `downstream_errors` — BIP error counts
- `lan_ports` — extracts port state table (LAN ID, type, speed, duplex, link)
- `wan_connections` — parses `display ont wan-info` multi-section output

## Configuration

`thresholds.py` + `config.yaml` define:
- Optical power thresholds (warn/crit for Rx/Tx)
- BIP error thresholds
- Temperature/voltage thresholds
- Bad firmware version list
- No-ping models list (e.g., model "310")