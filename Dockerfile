FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY omega_stenographer_mcp_standalone.py .

# Non-root user for security
RUN useradd -m steno && chown -R steno:steno /app
USER steno

# Critical for stdio MCP transport — no buffering
ENV PYTHONUNBUFFERED=1
ENV PYTHONUTF8=1

# Default: stdio transport (Glama inspection compatible)
ENTRYPOINT ["python", "omega_stenographer_mcp_standalone.py"]
