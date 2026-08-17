FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create non-root user, plus a writable /app/data directory for SQLite
# persistence when a deployment mounts a volume there (e.g. an EC2/Docker
# deployment using SQLITE_URL=sqlite:////app/data/expense.db instead of
# Postgres) - Docker initializes a fresh named volume from whatever
# already exists at the mount point, so this directory's ownership is
# what the volume ends up with, not root's.
RUN useradd -m appuser && mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser

# Railway (and most PaaS) inject a dynamic $PORT at container start, a
# different value on every deploy - this default of 5000 only applies to
# a plain `docker run` with no -e PORT=... set (e.g. local testing).
ENV PORT=5000
EXPOSE 5000

# Uses Python's built-in urllib (no extra dependency) and reads $PORT at
# runtime, so this works identically whether run locally or on Railway.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:' + os.environ.get('PORT', '5000') + '/api/health', timeout=5)"

# Shell form (not a JSON array) so $PORT is expanded by the shell at
# container start, not baked in at build time.
CMD gunicorn -w 2 -b 0.0.0.0:$PORT main:app
