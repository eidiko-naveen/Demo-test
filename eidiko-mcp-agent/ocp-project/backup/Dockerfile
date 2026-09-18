# syntax=docker/dockerfile:1
FROM python:3.12-slim

ARG APP_VERSION=dev
LABEL org.opencontainers.image.title="OCP AI Monitoring Agent" \
      org.opencontainers.image.description="OpenShift monitoring, analysis, reporting, and dashboard" \
      org.opencontainers.image.version="${APP_VERSION}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    XDG_CACHE_HOME=/tmp/.cache \
    HF_HOME=/tmp/huggingface \
    TRANSFORMERS_CACHE=/tmp/huggingface/transformers

WORKDIR /opt/app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY agent ./agent
COPY scheduler.py run_streamlit.py get_google_refresh_token.py ./
COPY GOOGLE_MEET_SETUP.md ./

# OpenShift may assign any UID. Group 0 permissions make the image compatible
# with that model while the default UID remains non-root for Docker/Compose.
RUN mkdir -p /tmp/ocp-monitor /tmp/.cache /tmp/huggingface /cache/huggingface \
    && chgrp -R 0 /opt/app /tmp/ocp-monitor /tmp/.cache /tmp/huggingface /cache \
    && chmod -R g=u /opt/app /tmp/ocp-monitor /tmp/.cache /tmp/huggingface /cache

USER 1001

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-m", "agent.healthcheck", "liveness"]

CMD ["python", "scheduler.py"]
