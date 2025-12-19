# Trachs - Google Find My Device to Traccar Bridge
# Multi-stage build for smaller final image

FROM python:3.13-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster package installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./

# Create virtual environment and install dependencies
RUN uv venv /app/.venv
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Install dependencies (without dev dependencies)
RUN uv pip install --no-cache .

# Final stage
FROM python:3.13-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with default UID/GID (can be changed at runtime)
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser --create-home --shell /bin/bash appuser

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY src/ /app/

# Set Python path to find modules
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default environment variables
ENV TRACCAR_URL=http://localhost:5055
ENV SECRETS_PATH=/app/secrets.json
ENV POLL_INTERVAL_SECONDS=300
ENV REQUEST_TIMEOUT_SECONDS=60
ENV DEVICE_MAPPING={}
ENV AUTO_GENERATE_DEVICE_IDS=true
ENV TRACCAR_ENABLED=true
ENV LOG_LEVEL=INFO

# Default PUID/PGID (can be overridden at runtime)
ENV PUID=1000
ENV PGID=1000

# Copy and set up entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Health check - just verify Python can import the main module
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import main" || exit 1

# Use entrypoint to handle user switching
ENTRYPOINT ["/entrypoint.sh"]

# Run the service
CMD ["python", "main.py"]
