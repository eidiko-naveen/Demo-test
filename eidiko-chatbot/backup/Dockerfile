# ============================================================
# EIDIKO Chatbot - Python Application
#
# Container Requirements:
# C04 - Dockerfile available
# C06 - Container image builds successfully
# C08 - Non-root / OpenShift arbitrary UID compatible
# C09 - No privileged container required
# C10 - No hardcoded credentials
# C24 - Logs written to stdout/stderr
# C25 - Graceful shutdown on SIGTERM
# ============================================================

# ------------------------------------------------------------
# Base image
# ------------------------------------------------------------
FROM python:3.12-slim

# ------------------------------------------------------------
# Python runtime configuration

# PYTHONDONTWRITEBYTECODE:
#   Prevents Python from creating .pyc files.

# PYTHONUNBUFFERED:
#   Sends application output immediately to stdout/stderr.
#   Important for Docker/Kubernetes/OpenShift logging.
# ------------------------------------------------------------

# -------------------------------------------------------

# PYTHONDONTWRITEBYTECODE=1 Prevents Python from creating .pyc bytecode files inside the container, keeping the container filesystem clean.

# PYTHONUNBUFFERED=1 helps the application logs appear immediately in Docker/OpenShift logs

# Python uses UTF-8 so that different types of text and characters are handled correctly.

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8

# ------------------------------------------------------------
# Application directory
# ------------------------------------------------------------
WORKDIR /app

# ------------------------------------------------------------
# Install Python dependencies
#
# Copy requirements first so Docker can reuse the dependency
# layer when application source code changes.
# ------------------------------------------------------------
COPY requirements.txt .

RUN pip install --no-cache-dir --disable-pip-version-check \
    -r requirements.txt

# ------------------------------------------------------------
# Copy application source
#
# Credentials are NOT copied.
#
# credentials/
# token.json
# .env
#
# are excluded by .dockerignore.
# ------------------------------------------------------------

COPY app.py .
COPY claude_client.py .
COPY google_client.py .
COPY redact.py .

COPY templates ./templates
COPY static ./static

# ------------------------------------------------------------
# C08 - OpenShift arbitrary UID compatibility
#
# OpenShift can assign an arbitrary non-root UID.
#
# Files/directories used by the application are owned by
# group 0 and group permissions are made equal to owner
# permissions.
#
# This allows an arbitrary OpenShift UID that belongs to
# group 0 to access the application files.
# ------------------------------------------------------------

# GID 0 is the Linux ID for the root group, used here to provide the required file permissions without running 
# the application as the root user.

# GID 0 allows the OpenShift user to access the application files.

RUN chgrp -R 0 /app && \
    chmod -R g=u /app

# ------------------------------------------------------------
# C09 - No privileged container
#
# This image does not require:
#
#   --privileged
#   hostNetwork
#   hostPID
#   hostIPC
#
# No privileged Linux capability is required by the
# application.
# ------------------------------------------------------------

# ------------------------------------------------------------
# Application port
#
# The application should listen on:
#
#   0.0.0.0:8080
#
# EXPOSE documents the container port.
# It does NOT publish the port by itself.
# ------------------------------------------------------------
EXPOSE 8080

# ------------------------------------------------------------
# C24 - stdout/stderr logging
#
# PYTHONUNBUFFERED=1 above ensures Python logs are flushed
# immediately.
#
# Applications should use:
#
#   print(...)
#
# or Python logging to stdout/stderr.
#
# Do NOT write application logs to files inside the container.
# ------------------------------------------------------------

# ------------------------------------------------------------
# C25 - Graceful SIGTERM
#
# Exec-form CMD ensures Python is the container process
# and can receive SIGTERM directly.
#
# OpenShift/Docker can therefore send:
#
#   SIGTERM -> Python application
#
# before the container is stopped.
# ------------------------------------------------------------

CMD ["python", "app.py"]
