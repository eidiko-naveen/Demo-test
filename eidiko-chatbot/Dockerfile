# ============================================================
# EIDIKO CHATBOT - Python Application
#
# Requirements:
# C04 - Dockerfile available
# C06 - Container image builds successfully
# C08 - Non-root / OpenShift arbitrary UID compatible
# C09 - No privileged container required
# C10 - No hardcoded credentials
# C12 - Environment variables
# C14 - Configurable application port
# C15 - No fixed IP dependencies
# C24 - Logs to stdout/stderr
# C25 - Graceful shutdown on SIGTERM
# ============================================================

FROM python:3.12-slim

# ============================================================
# Runtime environment
# ============================================================

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    HOST=0.0.0.0 \
    PORT=5000

# ============================================================
# Application directory
# ============================================================

WORKDIR /app

# ============================================================
# Install Python dependencies
# ============================================================

COPY requirements.txt .

RUN pip install --no-cache-dir --disable-pip-version-check \
    -r requirements.txt

# ============================================================
# Copy application source
#
# Credentials are NOT copied into the image.
# They are mounted at runtime.
# ============================================================

COPY app.py .
COPY claude_client.py .
COPY google_client.py .
COPY redact.py .

COPY templates ./templates
COPY static ./static

# ============================================================
# C08 - OpenShift arbitrary UID compatibility
#
# OpenShift can assign an arbitrary non-root UID.
# Group 0 permissions allow the arbitrary UID to read/write
# application files where required.
# ============================================================

RUN chgrp -R 0 /app && \
    chmod -R g=u /app

# ============================================================
# C09 - No privileged container
#
# The application does not require root or privileged mode.
# ============================================================

# ============================================================
# C14 - Application port
#
# Application listens on 0.0.0.0:5000 by default.
# PORT can be overridden through environment variables.
# ============================================================

EXPOSE 5000

# ============================================================
# C24 - Logs
#
# Application runs in foreground.
# Python logs go to stdout/stderr.
# ============================================================

# ============================================================
# C25 - Graceful SIGTERM
#
# Exec-form CMD ensures Python receives SIGTERM directly.
# ============================================================

CMD ["python", "app.py"]
