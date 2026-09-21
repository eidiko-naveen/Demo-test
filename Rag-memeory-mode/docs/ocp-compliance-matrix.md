# OCP Deployment Compliance Matrix

This project has been prepared for OpenShift deployment and evaluated against the requested control set.

| Control ID | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| C01 | Dockerfile available | ✅ | [Dockerfile](../Dockerfile) |
| C02 | Docker Compose file available | ✅ | [docker-compose.yml](../docker-compose.yml) |
| C03 | Container image builds successfully | ⚠️ Requires environment with Docker/Buildah | Local validation in this workspace is limited because Docker is not installed here |
| C04 | Image stored in approved registry | ⚠️ Requires OCP/DevOps registry push | Image reference is prepared in [k8s/enterprise-rag-platform.yaml](../k8s/enterprise-rag-platform.yaml) |
| C05 | Runs as a non-root, arbitrary UID | ✅ | Dockerfile runs as user 1001; Kubernetes manifest uses non-root security context |
| C06 | No privileged container required | ✅ | Security contexts drop privileges and disable escalation |
| C07 | No hardcoded credentials | ✅ | Secrets are externalized; .env template uses placeholders |
| C08 | Uses Kubernetes Secrets | ✅ | [k8s/enterprise-rag-platform.yaml](../k8s/enterprise-rag-platform.yaml) defines `Secret` resources |
| C09 | Uses environment variables | ✅ | App and Compose configuration rely on environment variables via `.env` and config maps |
| C10 | Configuration externalised to ConfigMaps | ✅ | [k8s/enterprise-rag-platform.yaml](../k8s/enterprise-rag-platform.yaml) includes `ConfigMap` |
| C11 | Application port configurable | ✅ | `PORT` is configurable in Dockerfile and Kubernetes manifest |
| C12 | No fixed IP dependencies | ✅ | Service discovery uses service names and environment config rather than fixed IP addresses |
| C13 | Liveness probe available | ✅ | App and dependent services include liveness probes |
| C14 | Readiness probe available | ✅ | App and dependent services include readiness probes |
| C15 | Startup probe available | ✅ | Startup probe has been configured for the app |
| C16 | CPU requests defined | ✅ | CPU requests are defined in the Kubernetes manifest |
| C17 | Memory requests defined | ✅ | Memory requests are defined in the Kubernetes manifest |
| C18 | CPU limits defined | ✅ | CPU limits are defined in the Kubernetes manifest |
| C19 | Memory limits defined | ✅ | Memory limits are defined in the Kubernetes manifest |
| C20 | Persistent storage identified | ✅ | PVCs are defined for Postgres and Qdrant |
| C21 | Logs written to stdout / stderr | ✅ | App uses Python logging and Uvicorn stdout output |
| C22 | Graceful shutdown on SIGTERM | ✅ | `--timeout-graceful-shutdown 30` and Kubernetes `preStop` hook are included |
| C23 | Kubernetes manifests prepared | ✅ | [k8s/enterprise-rag-platform.yaml](../k8s/enterprise-rag-platform.yaml) |

## Deployment notes

- Use a real secret store or OCP Secret values for `GROQ_API_KEY`, `POSTGRES_PASSWORD`, and any registry credentials.
- Replace the placeholder image in the manifest with the approved internal registry reference before deployment.
- Ensure namespace permissions, registry pull secret, and service account are aligned with the OCP cluster policies.
- The app health endpoints are already implemented at [app/api/v1/health.py](../app/api/v1/health.py) and are used by the probes.
