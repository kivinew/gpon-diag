# AGENTS.md

Comprehensive guide for AI agents working with the GPON Diagnostic Framework.

## Project Overview

This is a diagnostic tool for Huawei MA5600 series GPON OLTs. It collects optical parameters, parses CLI output, and generates problem reports based on configurable rules.

## Quick Start

```bash
# Install dependencies (uses uv)
uv sync

# Run smoke tests without OLT connection
uv run python -m tests.test_smoke

# Run full diagnosis
uv run diagnose.py 0/1/3/9 --olt "OLT-40.111"

# Run with specific options
uv run diagnose.py 4857544312E0E379 --json --no-save   # Serial, JSON, no file save
uv run diagnose.py fl_12345 --no-actions              # Description, no resets
```

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│ diagnose.py    CLI entry point, argument parsing, orchestration │
├─────────────────────────────────────────────────────────────┤
│ core/olt.py          Telnet connection manager (singleton)   │
│   - OltConnection: connect(), send_command(), collect_ont() │
│   - get_olt_connection(): factory with registry             │
│   - close_all(): cleanup all connections                      │
├─────────────────────────────────────────────────────────────┤
│ core/parser.py       Huawei CLI output → OntMetrics           │
│   - parse_ont_info(), parse_optical_info(), etc.            │
│   - Uses regex patterns in PATTERNS dict                    │
├─────────────────────────────────────────────────────────────┤
│ core/models.py       Data structures                         │
│   - OntMetrics: all collected metrics (dataclass)           │
│   - LanPort, MacDevice: nested structures                   │
├─────────────────────────────────────────────────────────────┤
│ core/engine.py       Rule-based diagnostic engine             │
│   - DiagnosticEngine: holds rules, runs diagnose()           │
│   - DEFAULT_RULES: 13 core rules                            │
│   - EXTENDED_RULES: DEFAULT + 8 additional rules              │
│   - create_default_engine(), create_extended_engine()          │
├─────────────────────────────────────────────────────────────┤
│ core/thresholds.py   Threshold configuration (dataclass)      │
│   - ont_rx_power_warn/crit, olt_rx_power_warn/crit          │
│   - bip_error_warn/crit, cpu/memory thresholds               │
├─────────────────────────────────────────────────────────────┤
│ core/report.py       Diagnosis models                         │
│   - DiagnosisProblem: severity, category, description        │
│   - DiagnosisReport: metrics, problems, to_text()/to_dict()  │
├─────────────────────────────────────────────────────────────┤
│ core/reporter.py     File output                             │
│   - save_report(): JSON format                              │
│   - save_text_report(): formatted text                        │
├─────────────────────────────────────────────────────────────┤
│ core/crt_stub.py     SecureCRT API emulation (for testing)    │
│   - FakeScreen, FakeCRT, FakeArguments                      │
├─────────────────────────────────────────────────────────────┤
│ GPON_class.py        Legacy SecureCRT integration             │
│   - GPON: diagnostic methods using crt object                │
│   - inject_crt(): must be called before using GPON           │
└─────────────────────────────────────────────────────────────┘
```

## Core Data Flow

1. **Input parsing** (`diagnose.py:parse_input()`):
   - Serial: `48575443` + 8 hex chars → `{"type": "serial", "value": "..."}`
   - Address: `F/S/P/ONT` (e.g., `0/1/3/9`) → `{"type": "address", ...}`
   - Description: alphanumeric → `{"type": "description", "value": "..."}`

2. **ONT lookup** (`olt.py:find_ont_by_sn()`, `find_ont_by_description()`):
   - Uses `display ont info by-sn <serial>` or `by-desc <description>`
   - Returns `{"frame", "slot", "port", "ont_id"}` or `None`

3. **Data collection** (`olt.py:collect_ont()`):
   - Runs 10+ commands via `send_command()`:
     - `display ont info`
     - `display ont version`
     - `display ont optical-info` (requires `interface gpon F/S` context)
     - `display statistics ont-line-quality`
     - `display ont port state eth-port all`
     - `display mac-address ont`
     - `display ont wan-info`
     - `display ont ipconfig`
     - `display ont register-info`
     - `display statistics ont-eth` (for each LAN port)

4. **Rule evaluation** (`engine.py:diagnose()`):
   - Each rule checks specific condition
   - Returns `DiagnosisProblem` or `None`
   - Problems sorted by severity (critical < warning < info)

## Rule Reference

| Rule | Category | Condition |
|------|----------|-----------|
| `rule_offline` | optic/power/config | Status not "online", analyzes last_down_cause |
| `rule_low_ont_rx` | optic | ont_rx_power < threshold |
| `rule_low_olt_rx` | optic | olt_rx_power < threshold |
| `rule_low_tx_power` | optic | ont_tx_power < 0.0/-1.0 dBm |
| `rule_bip_errors` | optic | upstream+downstream errors >= threshold |
| `rule_bad_firmware` | firmware | version in bad_versions list |
| `rule_no_lan` | ethernet | online but no LAN ports UP |
| `rule_overheating` | hardware | cpu_temp >= threshold |
| `rule_high_temperature` | hardware | ont_temperature >= 65/75°C |
| `rule_low_voltage` | hardware | supply_voltage outside 3.0-3.6V |
| `rule_long_distance` | optic | distance_m >= threshold |
| `rule_wan_disconnected` | wan | IPv4 status in ["disconnected", "connecting", "failed"] |
| `rule_lan_no_link` | ethernet | all LAN ports down |
| `rule_high_cpu` | hardware | cpu_usage >= threshold |
| `rule_high_memory` | hardware | memory_usage >= threshold |
| `rule_no_description` | accounting | description == "ONT_NO_DESCRIPTION" |
| `rule_frequent_falls` | stability | 2+ downtimes within 1 hour |
| `rule_eth_port_errors` | ethernet | FCS or bad bytes on active ports |
| `rule_long_uptime` | maintenance | uptime >= 5 days |

## Adding a New Rule

1. Add rule function in `core/engine.py`:
```python
def rule_new_check(metrics, t):
    """Check for X condition."""
    if not metrics.is_online:
        return None
    # Your check logic
    if condition:
        return DiagnosisProblem("warning", "category", "Description", "Recommendation")
    return None
```

2. Add to appropriate rule list:
```python
DEFAULT_RULES = [..., Rule("new_check", rule_new_check, "category")]
# or
EXTENDED_RULES = DEFAULT_RULES + [Rule("new_check", rule_new_check, "category")]
```

## Parser Development

When adding new CLI output parsing:
1. Add pattern to `PATTERNS` dict in `core/parser.py`
2. Create `_search_int`, `_search_float`, or `_search` helper usage
3. Add parsing function that mutates `OntMetrics`

Example:
```python
# In PATTERNS
"new_field": r"New Field\s*: *(.+)",

# Parser function
def parse_new_info(raw: str, m: OntMetrics) -> None:
    m.new_field = _search(raw, PATTERNS["new_field"]) or ""
```

## Testing Strategy

- `tests/test_smoke.py`: Creates mock `OntMetrics` with sample CLI output, runs engine rules
- No integration tests with real OLT (requires network access + credentials)
- Use `--no-actions` flag to prevent port resets during testing

## Environment Variables

Credentials are loaded via `python-dotenv` from `.env` file or system env:

| Variable | Description | Example |
|----------|-------------|---------|
| `GPON_OLT_<NAME>_USERNAME` | OLT login | `GPON_OLT_40_111_USERNAME` |
| `GPON_OLT_<NAME>_PASSWORD` | OLT password | `GPON_OLT_40_111_PASSWORD` |

Names with non-alphanumeric chars are sanitized (e.g., `OLT-17.232` → `17_232`).

## File Structure Notes

- Reports saved to `data/reports/` as `{timestamp}_{ont_address}.json` or `.txt`
- MAC OUI database at `data/oui.txt` for vendor lookup
- Config at `config.yaml` (OLT list + thresholds + settings)