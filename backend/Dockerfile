FROM python:3.11-slim

# Install system dependencies including FFmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create required directories
RUN mkdir -p assets/videos assets/output assets/audio/generated tmp/uploads assets/characters

# Expose FastAPI port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Apply the idempotent additive migration before code that reads clip origin.
# Fresh local databases receive the complete schema from docker-compose init mounts;
# existing databases are upgraded here before the API accepts traffic.
CMD ["sh", "-c", "python scripts/migrate_timeline_clip_origin.py && exec uvicorn main:app --host 0.0.0.0 --port 8000"]
