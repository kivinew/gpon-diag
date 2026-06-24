# QWEN.md – Project Instructional Context

## Project Overview
- **Name:** GPON Diagnostic Framework
- **Purpose:** Automated diagnosis of Huawei GPON OLT networks, collecting optical parameters from ONTs, parsing CLI output, and generating detailed reports.
- **Key Technologies:** Python 3.11+, `telnetlib3` for Telnet, `Flask` for web UI, `uv` for dependency management, `pyproject.toml` for packaging, SQLite for history storage, and SecureCRT integration for legacy environments.
- **Architecture Layers:**
  - `diagnose.py` – CLI entry point, argument parsing, orchestration.
  - `core/olt.py` – Telnet connection manager (singleton).
  - `core/parser.py` – Regex‑based parsing of OLT CLI output into `OntMetrics`.
  - `core/models.py` – Data classes (`OntMetrics`, `LanPort`, `MacDevice`).
  - `core/engine.py` – Rule‑based diagnostic engine (default + extended rules).
  - `core/report.py` – Diagnostic problem models.
  - `core/reporter.py` – Saves reports as JSON or formatted text.
  - `core/crt_stub.py` – SecureCRT API emulation for tests.
  - `GPON_class.py` – Legacy SecureCRT integration wrapper.
  - `web/` – Flask SSE UI for real‑time logs and report viewing.
  - `data/` – Stores generated reports (`data/reports/`) and optional incident backups.

## Building & Running
| Action | Command | Notes |
|--------|----------|-------|
| **Install dependencies** | `uv sync` | Uses the `pyproject.toml`/`uv.lock` configuration. |
| **Run a quick diagnosis** | `uv run diagnose.py <address|serial|description>` | Example: `uv run diagnose.py 0/1/3/9`. |
| **Select a specific OLT** | `uv run diagnose.py <target> --olt "OLT‑NAME"` | OLT names are defined in `config.yaml`. |
| **Copy result to clipboard** | `uv run diagnose.py <target> --clipboard` | Uses OS clipboard. |
| **Output JSON** | `uv run diagnose.py <target> --json` | Useful for programmatic consumption. |
| **Skip saving report** | `uv run diagnose.py <target> --no-save` | Generates output without writing a file. |
| **Run smoke tests** | `uv run python -m tests.test_smoke` | Validates core engine rules. |
| **Start web UI** | `uv run python -m web.app` | Access at `http://localhost:5000`. |
| **Run all tests** | `uv run pytest` *(if pytest is added)* | Not currently defined; fallback to individual test modules. |

> **TODO:** Verify exact test command and add any missing CI scripts.

## Development Conventions
- **Configuration:** All runtime settings live in `config.yaml`. Sensitive credentials are **never** stored here; they are supplied via environment variables `GPON_OLT_<NAME>_USERNAME` and `GPON_OLT_<NAME>_PASSWORD`.
- **Code Style:** Follows typical Python conventions – type‑annotated functions, dataclasses, and `ruff` linting (if present). No explicit style guide file, but existing code uses snake_case and adheres to PEP 8.
- **Testing:** Tests located under `tests/`. Smoke test (`test_smoke.py`) exercises rule engine. Additional unit tests target Telnet handling and parsers.
- **Commit Practices:** Use conventional commit messages (e.g., `feat:`, `fix:`, `docs:`) and ensure `git status && git diff HEAD && git log -n 3` before committing.
- **Reporting:** Reports are saved under `data/reports/` with timestamped filenames. Directory can be configured via `config.yaml`.
- **Web UI:** Flask app uses Server‑Sent Events (SSE) for live logs. Static assets in `web/static/`, templates in `web/templates/`.

## Key Files
- `config.yaml` – OLT definitions, thresholds, report settings.
- `diagnose.py` – CLI driver, parses arguments, creates `DiagnosticEngine`.
- `core/engine.py` – Implements rule set (`DEFAULT_RULES`, `EXTENDED_RULES`).
- `core/parser.py` – Regex patterns for extracting metrics.
- `core/olt.py` – Manages Telnet connections, singleton pattern.
- `core/models.py` – Data models (`OntMetrics`, etc.).
- `core/reporter.py` – Handles report persistence.
- `web/app.py` – Flask entry point for web interface.
- `tests/test_smoke.py` – Smoke test validating engine behavior.

## Usage Workflow (Typical)
1. **Prepare environment variables** for target OLT.
2. **Run diagnosis** via CLI or web UI.
3. **Review generated report** (text in console or JSON file).
4. **Iterate** – adjust thresholds in `config.yaml` if needed, re‑run.

---
*This QWEN.md file is auto‑generated to provide a concise reference for future interactions with the GPON Diagnostic Framework.*