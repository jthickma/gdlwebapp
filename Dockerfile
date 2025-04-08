# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    # Set language to prevent encoding issues
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    # Set default download directory inside container
    DOWNLOAD_DIR=/app/downloads \
    # Tell RQ where Redis is (can be overridden by docker-compose)
    REDIS_URL=redis://redis:6379 \
    # Disable Flask debug mode in production
    FLASK_DEBUG=0 \
    # Set Flask app entrypoint
    FLASK_APP=app.py \
    # Optionally enable file server via env var (default off)
    ENABLE_FILE_SERVER=false

# Set work directory
WORKDIR /app

# Install system dependencies (if any are needed by gallery-dl or its dependencies)
# RUN apt-get update && apt-get install -y --no-install-recommends some-package && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
# Use pip cache for faster builds
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

# Copy application code to the container
COPY . .

# Create the download directory within the container image
# and ensure the app user (non-root, defined below) can write to it
RUN mkdir -p ${DOWNLOAD_DIR} && chown -R appuser:appuser ${DOWNLOAD_DIR}

# Create a non-root user and switch to it
RUN useradd -m appuser
USER appuser

# Expose the port the app runs on (Gunicorn default)
EXPOSE 5000

# Define the command to run the application using Gunicorn
# Use CMD so it can be easily overridden if needed
# Start Gunicorn with multiple workers (adjust -w based on your CPU cores)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]

# Note: You also need to run an RQ worker separately. See docker-compose.yml