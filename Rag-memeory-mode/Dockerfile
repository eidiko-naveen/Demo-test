FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/app \
    PORT=8000

WORKDIR ${APP_HOME}
COPY . .

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e ".[ui,rag,migrations]" \
    && groupadd --system app && useradd --system --uid 1001 --gid app --create-home --home-dir /home/appuser appuser \
    && chown -R appuser:app ${APP_HOME}

USER 1001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -fsS "http://localhost:${PORT:-8000}/api/v1/health" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-graceful-shutdown 30"]
