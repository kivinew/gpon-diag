FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (telnet test, curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml uv.lock ./
COPY core/ core/
COPY data/oui.txt data/oui.txt
COPY config.yaml ./

# Install dependencies
RUN pip install --no-cache-dir uv && uv sync

# MCP server runs as non-root
RUN addgroup --system --gid 1001 appuser && \
    adduser --system --uid 1001 --gid 1001 appuser
USER appuser

# Healthcheck via MCP protocol (list tools)
HEALTHCHECK --interval=30s --timeout=5s \
    CMD python -c "import sys; sys.path.insert(0,'.'); from mcp_server import _load_config; _load_config()" || exit 1

EXPOSE 8090

# Default: stdio transport (used by MCP hosts like Claude Desktop)
# Override via --transport sse --port 8090 for HTTP/SSE
CMD ["python", "mcp_server.py"]
