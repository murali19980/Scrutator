# Dockerfile for Scrutator Academic
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create necessary directories
RUN mkdir -p reports logs

# Expose ports (7860 for Gradio Web UI, 8000 for FastAPI REST API)
EXPOSE 7860 8000

# Set entrypoint
ENTRYPOINT ["python", "-m"]

# Default command (runs Web UI)
CMD ["api.web_ui"]
