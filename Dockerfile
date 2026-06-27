# Dockerfile for Scrutator Academic
# ─────────────────────────────────────────────────────────────────────────────
# Build stage: Install dependencies in an isolated layer for smaller image
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

# Install build deps (gcc needed for some packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ─────────────────────────────────────────────────────────────────────────────
# Runtime stage
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.13-slim

# Security: create a non-root user before copying anything in
RUN groupadd --system appgroup && \
    useradd --system --gid appgroup --shell /bin/false --home /app appuser

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/root/.local/bin:$PATH"

# Install runtime system dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy project files
COPY --chown=appuser:appgroup . .

# Create necessary directories and fix ownership
RUN mkdir -p reports logs && \
    chown -R appuser:appgroup /app

# Switch to the non-root user
USER appuser

# Update PATH for the non-root user's installed packages
ENV PATH="/home/appuser/.local/bin:$PATH"

# Expose ports (7860 for Gradio Web UI, 8000 for FastAPI REST API)
EXPOSE 7860 8000

# Default command (runs Web UI)
CMD ["python", "-m", "api.web_ui"]
