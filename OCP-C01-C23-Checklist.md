# EIDIKO Chatbot — OCP C01–C23 Deployment Checklist

| Control | Status from application package | Evidence / owner |
|---|---|---|
| C01 Dockerfile available | READY | `Dockerfile` |
| C02 Docker Compose available | READY | `docker-compose.yml` |
| C03 Container image builds successfully | DEVOPS VERIFY | Build command in deployment README |
| C04 Image stored in approved registry | DEVOPS | Replace image placeholder in `k8s/deployment.yaml` |
| C05 Non-root, arbitrary UID | READY | Dockerfile uses non-root default + group-0 writable app/state paths |
| C06 No privileged container | READY | `privileged: false`, `allowPrivilegeEscalation: false`, all capabilities dropped |
| C07 No hardcoded credentials | READY | Secrets excluded; `.env`, token and credentials ignored |
| C08 Kubernetes Secrets | READY | `k8s/secret-template.yaml`; use approved secret-management process |
| C09 Environment variables | READY | Configurable `PORT`, credential/token paths and API key |
| C10 ConfigMaps | READY | `k8s/configmap.yaml` |
| C11 Application port configurable | READY | `PORT`; Docker exposes 5000 by default |
| C12 No fixed IP dependencies | READY | OCP Service/Route; OAuth redirect uses request host/proxy headers |
| C13 Liveness probe | READY | `/health/live` |
| C14 Readiness probe | READY | `/health/ready` |
| C15 Startup probe | READY | `/health/live` startup probe in Deployment |
| C16 CPU requests | READY | 250m |
| C17 Memory requests | READY | 512Mi |
| C18 CPU limits | READY | 1 CPU |
| C19 Memory limits | READY | 1Gi |
| C20 Persistent storage | IDENTIFIED | PVC for OAuth token state at `/data`; confirm storage policy with DevOps |
| C21 stdout/stderr logging | READY | Gunicorn access/error logs use stdout/stderr |
| C22 Graceful SIGTERM | READY | Gunicorn is PID 1 via `exec` and handles SIGTERM gracefully |
| C23 Kubernetes manifests | READY | `k8s/` |

## DevOps handoff

1. Build the image from the supplied `Dockerfile`.
2. Run the image as an arbitrary non-root UID and verify `/health/live` and `/health/ready`.
3. Push the image to the approved registry.
4. Create `eidiko-chatbot-secrets` using the organization's approved secret-management process. Do not commit real values.
5. Apply the ConfigMap, PVC, Deployment, Service and Route.
6. Provide the final HTTPS Route hostname.
7. Register that HTTPS hostname + `/oauth2callback` as an authorized redirect URI in the Google OAuth client.
8. Verify the first Google OAuth login and token persistence on the PVC.
9. Verify Gmail/Drive/Calendar/Meet workflows after deployment.

### Important OAuth note

Local development may use an HTTP localhost callback. OCP must use the HTTPS Route URL. The application uses forwarded host/protocol headers so `url_for(..., _external=True)` generates the public HTTPS callback behind the OpenShift Route.

### Important token note

`token.json` contains OAuth credentials and is sensitive. It is intentionally not included in the application image or source ZIP. This deployment uses the PVC for writable token state; protect the PVC according to the organization's security/storage policy. The Google OAuth client JSON and Anthropic key belong in the Kubernetes Secret/approved secret manager.
