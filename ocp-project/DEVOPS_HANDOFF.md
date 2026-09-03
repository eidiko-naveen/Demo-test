# OCP AI Monitoring Agent — DevOps handoff

## Technology stack

| Layer | Technology | Purpose |
|---|---|---|
| Runtime | Python 3.12 | Application runtime used by the scheduler and dashboards. |
| AI orchestration | LangChain 0.3, LangGraph 0.2 | Prompt integration and the monitoring workflow graph. |
| LLM | Groq via `langchain-groq` | Cluster failure analysis and remediation generation. |
| RAG | LlamaIndex 0.12 | Similar-incident retrieval and remediation reuse. |
| Embeddings | HuggingFace `BAAI/bge-small-en-v1.5` | Local CPU embeddings for incident similarity. |
| ML runtime | CPU-only PyTorch 2.5 | Runs the local HuggingFace embedding model without CUDA. |
| Cluster API | Kubernetes Python client 31 | Reads OpenShift nodes, pods, PVCs, Secrets, and custom resources. |
| Database | PostgreSQL with pgvector | Monitoring history, failures, resolutions, incidents, and vectors. |
| ORM | SQLAlchemy 2 | Database models, connections, queries, and transactions. |
| Scheduling | APScheduler 3 | Executes an immediate cycle and repeats at the configured interval. |
| Dashboard | Streamlit 1.48 | Primary operations dashboard, exposed on configurable port 8501. |
| Optional API/UI | FastAPI, Uvicorn, Jinja2 | Alternative dashboard and JSON API on the configured dashboard port. |
| Email | SMTP or SendGrid | Sends HTML monitoring and remediation reports. |
| Meetings | Google Calendar API and OAuth 2 | Creates escalation events with Google Meet links. |
| Configuration | Pydantic Settings | Validates environment variables loaded from Secrets and ConfigMaps. |
| Logging | Structlog | JSON or console logs written to stdout/stderr. |
| Resilience | Tenacity | Retries transient LLM/API failures. |
| Containers | Docker / OCI | Builds one reusable non-root scheduler/dashboard image. |
| Local orchestration | Docker Compose | Runs scheduler, dashboard, and PostgreSQL/pgvector locally. |
| Platform | Kubernetes / Red Hat OpenShift | Production deployment, RBAC, probes, resources, Service, and Route. |
| Manifest management | Kustomize | Renders resources and substitutes the approved registry image. |

### External services and network dependencies

- Groq API over HTTPS (`443`).
- OpenShift Kubernetes API using the Pod ServiceAccount in-cluster.
- PostgreSQL/pgvector over configurable TCP host and port (`5432` by default).
- SMTP (`587` by default) or SendGrid HTTPS when email is enabled.
- Google OAuth and Calendar APIs over HTTPS when escalation is enabled.
- Configured CP4I health endpoints over HTTPS when supplied.
- HuggingFace model download over HTTPS on first RAG use unless the model cache
  is pre-populated or persisted.

## Deliverables

- One reusable image runs either the scheduler or Streamlit dashboard.
- `compose.yaml` provides local integration with PostgreSQL/pgvector.
- `deploy/kubernetes` provides OpenShift resources for the scheduler and dashboard.
- Local credentials (`.env`, `kubeconfig`, and `deploy/secrets.env`) are excluded
  from Git and the container build context.

## Build and publish

Replace the example registry with the approved registry and immutable release tag.

```bash
export IMAGE_REGISTRY=approved-registry.example.com/platform
export IMAGE_TAG=1.0.0

docker build \
  --build-arg APP_VERSION="$IMAGE_TAG" \
  --tag "$IMAGE_REGISTRY/ocp-monitor:$IMAGE_TAG" \
  .

docker login approved-registry.example.com
docker push "$IMAGE_REGISTRY/ocp-monitor:$IMAGE_TAG"
```

Update `deploy/kubernetes/kustomization.yaml` with the approved image name/tag.
Do not deploy a mutable `latest` tag in production.

## Local Compose verification

The local `.env` must provide at least `GROQ_API_KEY` and
`POSTGRES_PASSWORD`. `KUBECONFIG_FILE` can override the default `./kubeconfig`.

```bash
docker compose config
docker compose build
docker compose up -d
docker compose ps
```

Dashboard: <http://localhost:8501>

## Create the Kubernetes Secret

Use the organization's approved secret manager where available. For a manual
bootstrap, copy the unpopulated template and fill it outside source control:

```bash
cp deploy/secrets.env.example deploy/secrets.env
oc -n ocp-monitor create secret generic ocp-monitor-secrets \
  --from-env-file=deploy/secrets.env \
  --dry-run=client -o yaml | oc apply -f -
```

Only populate SMTP or Google values when those features are enabled in the
ConfigMap. Never place real values in `secret.example.yaml`.

## Configure and deploy

Before deployment, review:

1. Registry name/tag in `kustomization.yaml`.
2. PostgreSQL DNS name and database settings in `configmap.yaml`.
3. Email sender/recipients and `EMAIL_ENABLED`.
4. CP4I URLs and monitored namespaces.
5. Google escalation owners and `ESCALATION_ENABLED`.
6. CPU/memory settings against observed usage.
7. The ClusterRole rule that reads TLS Secrets. It is required for certificate
   expiry monitoring and should be removed if cluster policy disallows it.

Deploy and verify:

```bash
oc apply -f deploy/kubernetes/namespace.yaml
# Create ocp-monitor-secrets before applying the kustomization.
oc apply -k deploy/kubernetes
oc -n ocp-monitor rollout status deployment/ocp-monitor-scheduler
oc -n ocp-monitor rollout status deployment/ocp-monitor-dashboard
oc -n ocp-monitor get pods,service,route
```

## Persistent storage

- The application containers are stateless and need no application PVC.
- PostgreSQL is the system of record and must use the platform's managed
  PostgreSQL service or a separately managed StatefulSet/PVC and backup policy.
- Compose uses the `postgres-data` named volume for local persistence.
- The HuggingFace cache can be ephemeral. The Kubernetes scheduler uses `/tmp`;
  add a cache PVC only if repeated model downloads are operationally expensive.

## C01–C23 compliance matrix

| ID | Status | Implementation / owner action |
|---|---|---|
| C01 | Ready | Root `Dockerfile`. |
| C02 | Ready | Root `compose.yaml`. |
| C03 | Ready | Built successfully as `ocp-monitor:dev`; CI should repeat the build for every release. |
| C04 | DevOps action | Push the versioned image to the approved registry and update Kustomize. |
| C05 | Ready | UID 1001 by default; group-0 permissions and no fixed Kubernetes UID support OpenShift arbitrary UID. |
| C06 | Ready | No privileged mode; all capabilities dropped and privilege escalation disabled. |
| C07 | Ready for source handoff | Examples contain placeholders; local secret files are ignored/excluded. |
| C08 | Ready | Deployments consume `ocp-monitor-secrets`; example/bootstrap instructions supplied. |
| C09 | Ready | Runtime settings use environment variables through Pydantic Settings. |
| C10 | Ready | Non-secret runtime configuration is in `configmap.yaml`. |
| C11 | Ready | `DASHBOARD_HOST` and `DASHBOARD_PORT` control Streamlit binding. |
| C12 | Ready | PostgreSQL and endpoints use externalized DNS names/URLs; no fixed IPs. |
| C13 | Ready | Scheduler exec and dashboard HTTP liveness probes. |
| C14 | Ready | Scheduler exec and dashboard HTTP readiness probes. |
| C15 | Ready | Scheduler exec and dashboard HTTP startup probes. |
| C16 | Ready | CPU requests on both Deployments. |
| C17 | Ready | Memory requests on both Deployments. |
| C18 | Ready | CPU limits on both Deployments. |
| C19 | Ready | Memory limits on both Deployments. |
| C20 | Identified | PostgreSQL requires persistent managed storage; app containers are stateless. |
| C21 | Ready | Structlog writes to stdout/stderr; no application log files. |
| C22 | Ready | Scheduler handles SIGTERM; direct exec-form commands preserve signals. |
| C23 | Ready | Namespace, RBAC, ConfigMap, Deployments, Service, Route, and Kustomize supplied. |

## Recommended CI gates

1. Unit tests and Python compilation.
2. Dependency consistency and vulnerability scan.
3. Secret scanning.
4. `docker build` followed by an image vulnerability scan.
5. Kustomize render and Kubernetes schema/policy validation.
6. Run the image with a random UID and read-only root filesystem.
7. Push only after every gate passes; sign the image if required by policy.
