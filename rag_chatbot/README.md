## RAG Chatbot

This app uses Groq as the production chat model and a local Hugging Face
embedding model with Qdrant for retrieval.

### Setup

1. Install dependencies:

	```bash
	pip install -r requirements.txt
	```

2. Copy `.env.example` to `.env` and set `GROQ_API_KEY`. The key is read
	only from the environment and is never rendered in the UI or trace metadata.

	Set `GROQ_MODEL` to the exact model identifier supported by your Groq account.

	Development uses `AUTH_MODE=development` and the configured development user
	and tenant IDs. Production must set `AUTH_MODE=enterprise` and replace
	`get_current_identity()` in `auth/identity.py` with an adapter for the trusted
	OIDC/SAML or reverse-proxy identity boundary; never trust user IDs from the
	browser. Upload, question, archive-expansion, and concurrency limits are
	configurable in `.env.example`.

3. Start the app:

	```bash
	.venv/bin/streamlit run app.py
	```

For a clean checkout, use Python 3.10 through 3.13, install with
`pip install -r requirements.txt`, copy `.env.example` to `.env`, and run
`pytest -q`. Pytest is configured through `pyproject.toml`; no `PYTHONPATH`
override is required.

For production, set `DATABASE_URL` to PostgreSQL and `QDRANT_URL` plus
`QDRANT_API_KEY` for a managed Qdrant instance. If `QDRANT_URL` is empty, the
app uses the local persistent store in `qdrant_storage/`. Hybrid and Research
modes use internal knowledge unless an external `SearchProvider` implementation
is configured in `services/search.py`; the app does not fabricate web sources.

`RELEVANCE_THRESHOLD` is configurable and defaults to `0.35`. Calibrate it on
representative relevant and irrelevant questions by measuring retrieval
precision and recall, then choose the highest threshold that preserves acceptable
recall. Re-evaluate it when the embedding model or corpus changes.

### Production deployment

1. Provision PostgreSQL and an authenticated remote Qdrant instance.
2. Create `.env` from `.env.example`; set `AUTH_MODE=enterprise`, a PostgreSQL
	`DATABASE_URL`, `QDRANT_URL`, and `QDRANT_API_KEY` from a secret manager.
3. Configure the enterprise identity adapter in `auth/identity.py` and place
	the app behind TLS and an authenticated reverse proxy.
4. Build and start the supplied deployment configuration:
	`docker compose -f docker-compose.production.yml up --build -d`.
5. Use `python -m compileall -q .`, `pytest -q`, and the readiness helper before
	accepting traffic. The Streamlit UI reports dependency failures without
	exposing credentials; Langfuse failures are non-fatal and remain redacted.

### OpenShift and DevOps controls

The `k8s/` directory contains an OpenShift-compatible Kustomize deployment for
the application. It covers C01-C03 and C05-C23: the image runs without root,
privileges, or fixed IPs; configuration is in a ConfigMap; credentials are
referenced from a Kubernetes Secret; the port and storage paths are
environment-driven; all three probes and resource requests/limits are present;
logs go to stdout; and the pod has a 30-second SIGTERM grace period.

Before applying it, coordinate these actions with DevOps/OCP:

1. Build `Dockerfile`, scan the image, and push it to the approved registry.
Replace the registry placeholder in `k8s/kustomization.yaml` (C04).
2. Provision PostgreSQL and authenticated Qdrant, then update their service DNS
name and storage class in `k8s/configmap.yaml` and `k8s/pvc.yaml`.
3. Create `enterprise-rag-secrets` using the cluster secret manager, with
`GROQ_API_KEY`, `DATABASE_URL`, and `QDRANT_API_KEY`; do not apply the template
with placeholder values. Configure the trusted OIDC/SAML identity adapter and
TLS route at the platform boundary.
4. Run `oc apply -k k8s/`, verify the three probes and resource quotas, then
confirm the image signature, registry admission policy, NetworkPolicies, and
backup/restore ownership with the platform team.

### Backup and restore

Back up PostgreSQL with `pg_dump --format=custom --file=backup.dump "$DATABASE_URL"`
and restore with `pg_restore --clean --if-exists --dbname="$DATABASE_URL" backup.dump`.
Back up Qdrant using its authenticated snapshot API or managed-service backup;
for the compose deployment, stop writes and archive the `qdrant_data` volume.
Restore the snapshot/volume before starting the app, then verify collection
availability and document ownership filters. Test restores regularly and keep
database and vector-store backups from the same recovery point.

Run tests with:

```bash
.venv/bin/pytest -q

The current schema bootstrap keeps existing local databases usable, but it is
not a migration system. Production deployments should introduce versioned
Alembic migrations before running schema changes across multiple replicas.

The compose app binds only to loopback so a TLS reverse proxy can be the public
boundary. PostgreSQL and Qdrant are private compose services. The upload volume
is initialized for the non-root application user.
```
