---
name: run-smoke-test
description: Run GPON diagnostic smoke tests without OLT connection to verify code changes don't break core functionality. Required after any changes to core/ modules per AGENTS.md §5.
---

# Smoke Test for GPON Diagnostic Framework

Run smoke tests after any code changes in `core/` to verify parser and engine functionality work correctly. These tests use sample data and require no live OLT connection.

## When to Use This Skill

After editing any file in `core/` directory:
- `core/models.py` — after adding OntMetrics fields
- `core/parser.py` — after adding/updating regex patterns
- `core/engine.py` — after adding new diagnostic rules
- `core/report.py` — after modifying report output
- Any other core module changes

## Command

```bash
uv run python -m tests.test_smoke
```

## Expected Output

All three tests should pass with "ALL TESTS PASSED" at the end:

```
=== TEST 1: Offline (dying-gasp) ===
<report output>

PASSED

=== TEST 2: Online healthy ===
<report output>

PASSED

=== TEST 3: Low Rx + BIP errors ===
<report output>

PASSED

========================================
ALL TESTS PASSED
```

## Stopping Condition

Tests complete when:
1. All 3 test functions execute successfully
2. Output contains "ALL TESTS PASSED"
3. No assertion errors raised

## What Tests Cover

| Test | Purpose |
|------|---------|
| `test_offline_dying_gasp()` | Offline ONT with dying-gasp cause → power category problem |
| `test_online_healthy()` | Online ONT with good metrics → no problems |
| `test_low_rx()` | Low optical power + BIP errors → optic category problem |

## Failure Handling

If tests fail:
1. Check the assertion error message
2. Revert the change that caused failure
3. Ensure any new fields have defaults in OntMetrics
4. Ensure new rules follow `if not metrics.is_online: return None` pattern (except offline rules)