FROM python:3.12-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY omega_stenographer_mcp_standalone.py omega_stenographer_mcp.py omega_runtime.py veritas_bridge.py codex_capture.py steno_client.py stdio_client.py ./

# Non-root user for security
RUN useradd -m steno && chown -R steno:steno /app
USER steno

# Critical for stdio MCP transport — no buffering
ENV PYTHONUNBUFFERED=1
ENV PYTHONUTF8=1

# Default: stdio transport (Glama inspection compatible)
CMD ["python", "omega_stenographer_mcp_standalone.py"]
