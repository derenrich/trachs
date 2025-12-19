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
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

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

# Switch to non-root user
USER appuser

# Health check - just verify Python can import the main module
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import main" || exit 1

# Run the service
CMD ["python", "main.py"]
