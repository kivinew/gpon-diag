#!/usr/bin/env bash
# Wrapper to launch gpon MCP server with correct cwd.
cd /mnt/e/DOWNLOADS/CREATIVE/PYTHON/GitHub/gpon-diag
exec uv run --project /mnt/e/DOWNLOADS/CREATIVE/PYTHON/GitHub/gpon-diag python /mnt/e/DOWNLOADS/CREATIVE/PYTHON/GitHub/gpon-diag/mcp_server.py "$@"
