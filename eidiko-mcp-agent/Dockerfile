# ============================================================
# EIDIKO MCP AGENT
# Dockerfile
# ============================================================

FROM python:3.12-slim

# ============================================================
# C10 - Runtime configuration
# Do NOT put passwords, API keys or tokens here.
# ============================================================

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache \
    STREAMLIT_HOME=/tmp/.streamlit

# ============================================================
# Application directory
# ============================================================

WORKDIR /app

# ============================================================
# Install dependencies
# C06 - Image build
# ============================================================

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ============================================================
# Copy application
# ============================================================

COPY agent/ ./agent/
COPY mcp_client/ ./mcp_client/
COPY scripts/ ./scripts/
COPY ui/ ./ui/
COPY config.py ./

# ============================================================
# C08 - OpenShift arbitrary UID compatibility
#
# OpenShift can run the container with a random non-root UID.
# Group 0 permissions allow arbitrary UID access.
# ============================================================

RUN chgrp -R 0 /app && \
    chmod -R g=u /app

# ============================================================
# C09 - No privileged container
#
# No USER root
# No privileged requirement
# ============================================================

# ============================================================
# Streamlit application port
# ============================================================

EXPOSE 8501

# ============================================================
# C24 - Logs to stdout/stderr
# C25 - Foreground process receives SIGTERM
# ============================================================

CMD ["streamlit", "run", "ui/app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false"]
