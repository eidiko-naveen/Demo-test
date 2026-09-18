# ============================================================
# OCP PROJECT - STREAMLIT APPLICATION
# ============================================================
#
# Container Requirements Covered:
#
# C04 - Dockerfile available
# C06 - Container image builds successfully
# C08 - Runs as non-root / arbitrary UID
# C09 - No privileged container required
# C10 - No hardcoded credentials
# C24 - Logs written to stdout/stderr
# C25 - Graceful shutdown on SIGTERM
#
# ============================================================


# ------------------------------------------------------------
# C04 - Dockerfile available
# C06 - Use a fixed Python base image
# ------------------------------------------------------------
FROM python:3.12-slim


# ------------------------------------------------------------
# C10 - NO HARDCODED CREDENTIALS
#
# Do NOT put:
#   API keys
#   passwords
#   tokens
#   Google credentials
#   client secrets
#
# in this Dockerfile.
#
# Sensitive values must be provided at runtime using:
#   - Docker environment variables
#   - Docker Compose .env
#   - OpenShift Secrets
# ------------------------------------------------------------


# ------------------------------------------------------------
# C24 - LOGGING
#
# Python output is unbuffered so application logs are
# immediately written to stdout/stderr.
# Docker/OpenShift can then collect the logs.
# ------------------------------------------------------------
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8


# ------------------------------------------------------------
# C08 - OPENSHIFT ARBITRARY UID COMPATIBILITY
#
# OpenShift can assign an arbitrary non-root UID.
#
# HOME and cache directories are placed under /tmp,
# which is writable by the container process.
# ------------------------------------------------------------
ENV HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache


# ------------------------------------------------------------
# Streamlit configuration
# ------------------------------------------------------------
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501


# ------------------------------------------------------------
# C06 - Application working directory
# ------------------------------------------------------------
WORKDIR /app


# ------------------------------------------------------------
# C06 - Copy dependency file
# ------------------------------------------------------------
COPY requirements.txt .


# ------------------------------------------------------------
# C06 - Install application dependencies
# ------------------------------------------------------------
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# ------------------------------------------------------------
# C06 - Copy application source code
# ------------------------------------------------------------
COPY . .


# ------------------------------------------------------------
# C08 - NON-ROOT / ARBITRARY UID COMPATIBILITY
#
# OpenShift may run this container with an arbitrary UID.
#
# Group 0 permissions allow arbitrary OpenShift UIDs
# to read/write the required application files.
# ------------------------------------------------------------
RUN chgrp -R 0 /app && \
    chmod -R g=u /app


# ------------------------------------------------------------
# C09 - NO PRIVILEGED CONTAINER REQUIRED
#
# This image does NOT require:
#
#   privileged: true
#   --privileged
#   hostNetwork
#   hostPID
#   host filesystem
#   Linux capabilities
#
# The application can run without root privileges.
# ------------------------------------------------------------


# ------------------------------------------------------------
# C06 - Application port
# ------------------------------------------------------------
EXPOSE 8501


# ------------------------------------------------------------
# C25 - GRACEFUL SHUTDOWN
#
# Python application is started as the main container process.
#
# Docker sends SIGTERM to the main process during shutdown.
# The application must handle SIGTERM and perform cleanup.
# ------------------------------------------------------------
CMD ["python", "run_streamlit.py"]
