# Featherweight image — slim base, no native ML deps (ARCHITECTURE §2/§9).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend

# Run as a non-root user.
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

# Single uvicorn worker — Railway Hobby is a small container. `exec` via sh -c so
# Railway's injected $PORT is honoured while uvicorn receives SIGTERM directly
# (clean shutdown on redeploys).
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
