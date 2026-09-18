FROM python:3.11-slim AS builder
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
RUN uv sync --no-dev

FROM python:3.11-slim
RUN groupadd -r appgroup && useradd -r -g appgroup -u 1001 appuser
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY app.py ./
ENV PATH="/app/.venv/bin:$PATH"
RUN chown -R appuser:appgroup /app
USER 1001
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]