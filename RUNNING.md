# Local operation

Start or update the services from this project directory:

```bash
docker compose build scheduler
docker compose up -d --wait scheduler dashboard
docker compose ps
```

Both application services use the same image. Open the dashboard at
http://localhost:8501. The scheduler runs immediately on startup, then every
15 minutes. PostgreSQL is exposed locally on port 5437; containers use
`postgres:5432`. Local Python processes use the database settings in `.env`.

```bash
.venv/bin/python -m pytest -q
docker compose logs --tail 60 scheduler dashboard
```

The local `.env` points to the kubeconfig in this directory. Update
`KUBECONFIG_PATH` if the directory moves again. Compose mounts `./kubeconfig`
at its container path automatically.

The checked cluster does not advertise the CP4I integration API, so local
`CP4I_PLATFORM_NAVIGATOR_ENABLED=false`. Enable this check when CP4I is
installed and verify the PlatformNavigator namespace/API version in
`agent/tools.py`. Configured HTTP endpoint checks are independent of this flag.

Email delivery, Google escalation, and live remediation execution are disabled
in the verified local configuration. Remediation approval screens operate in
dry-run mode. The optional FastAPI application was tested against the database;
the Compose dashboard service serves Streamlit, not the FastAPI routes.

LLM failures now produce an error status. Partial collection failures are
retained and shown in Run Explorer, rather than being silently treated as
healthy telemetry. Historical runs retain their original saved results.
