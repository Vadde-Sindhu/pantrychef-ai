# PantryChef AI — single-stage image serving the FastAPI backend,
# which itself serves the static frontend. Runs on AWS App Runner /
# Elastic Beanstalk (Docker platform) / ECS out of the box.

FROM python:3.11-slim

# Prevent .pyc files and enable unbuffered logging (useful in container logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install backend dependencies first for better layer caching
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy application code (frontend + backend)
COPY backend ./backend
COPY frontend ./frontend

# Run as a non-root user
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# AWS App Runner / ELB health checks hit /api/health
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
