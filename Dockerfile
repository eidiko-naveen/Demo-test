FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000 \
    HOST=0.0.0.0 \
    FLASK_DEBUG=0 \
    ALLOW_INSECURE_OAUTH=0 \
    GOOGLE_CREDENTIALS_FILE=/etc/eidiko/google/credentials.json \
    TOKEN_FILE=/data/token.json

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# OpenShift may run the image with an arbitrary UID. Group 0 permissions
# allow the assigned UID to write only where the application needs state.
RUN mkdir -p /data \
    && chgrp -R 0 /app /data \
    && chmod -R g=u /app /data

EXPOSE 5000

# Non-root default; OpenShift may override this with its arbitrary UID.
USER 1001

CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile - app:app"]
