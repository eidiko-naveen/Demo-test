# OCP Deployment Handoff

This package is the current EIDIKO Chatbot functional version plus deployment hardening for the C01–C23 controls supplied by the manager.

## Build

```bash
docker build -t <approved-registry>/eidiko-chatbot:<tag> .
docker run --rm -p 5000:5000 \
  -e ANTHROPIC_API_KEY="<local-test-key>" \
  -e GOOGLE_CREDENTIALS_FILE=/run/secrets/google_credentials \
  -v "$PWD/credentials/credentials.json:/run/secrets/google_credentials:ro" \
  -v eidiko-token-data:/data \
  <approved-registry>/eidiko-chatbot:<tag>
```

For local Docker testing only, `ALLOW_INSECURE_OAUTH=1` may be used for the localhost HTTP callback. OCP must use `ALLOW_INSECURE_OAUTH=0` and HTTPS.

## OCP

DevOps should replace `<APPROVED_REGISTRY>/...:<TAG>` in `k8s/deployment.yaml`, create the Secret through the approved mechanism, then apply:

```bash
oc apply -f k8s/configmap.yaml
oc apply -f k8s/pvc.yaml
oc apply -f k8s/deployment.yaml
oc apply -f k8s/service.yaml
oc apply -f k8s/route.yaml
```

The Route hostname must be registered in Google Cloud OAuth credentials as:

```text
https://<route-hostname>/oauth2callback
```

Do not use `127.0.0.1` for OCP.

## Health

- `GET /health/live` → 200 `{"status":"ok"}`
- `GET /health/ready` → 200 `{"status":"ready"}`

## Configuration

Non-secret configuration is in `k8s/configmap.yaml`.
Secrets are in `k8s/secret-template.yaml` and must be populated through approved secret management.

## Storage

The application needs writable state for `token.json` after Google OAuth. The supplied PVC is 1Gi and mounted at `/data`. DevOps should confirm whether this persistence model meets the organization's security/storage policy. Do not bake `token.json` into the image.

## Logs

Gunicorn writes access and error logs to stdout/stderr, suitable for OpenShift log collection.

## Demo/application behavior

The existing Gmail, Drive, multi-attachment, Calendar, Google Meet, confirmation, cross-service and free-slot workflows are unchanged by the deployment hardening.
