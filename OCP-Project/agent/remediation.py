"""Strictly allowlisted, human-approved OpenShift remediation workflow."""

from __future__ import annotations

import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from html import escape
from typing import Any

from sqlalchemy import desc

from agent.config import get_settings
from agent.db import get_session
from agent.logger import get_logger
from agent.models import RemediationRequest

log = get_logger(__name__)

ACTION_RESTART_DEPLOYMENT = "restart_deployment"
_DNS_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


class RemediationError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _event(event: str, actor: str, detail: str) -> dict[str, str]:
    return {
        "at": _now().isoformat(), "event": event, "actor": actor, "detail": detail,
    }


def validate_target(namespace: str, deployment: str, action: str) -> None:
    """Reject every action or target that is not explicitly configured."""
    cfg = get_settings()
    if not cfg.hitl_enabled:
        raise RemediationError("HITL remediation is disabled")
    if not _DNS_LABEL.fullmatch(namespace) or not _DNS_LABEL.fullmatch(deployment):
        raise RemediationError("Invalid Kubernetes namespace or Deployment name")
    if action != ACTION_RESTART_DEPLOYMENT:
        raise RemediationError(f"Action '{action}' is not allowed")
    if namespace != cfg.hitl_allowed_namespace:
        raise RemediationError(f"Namespace '{namespace}' is not allowlisted")
    if deployment != cfg.hitl_allowed_deployment:
        raise RemediationError(f"Deployment '{deployment}' is not allowlisted")


def create_request(
    reason: str,
    requested_by: str = "monitoring-dashboard",
    notify_approver: bool = True,
) -> uuid.UUID:
    """Create one pending request for the configured target; never executes it."""
    cfg = get_settings()
    namespace = cfg.hitl_allowed_namespace.strip()
    deployment = cfg.hitl_allowed_deployment.strip()
    reason = reason.strip()
    if not reason:
        raise RemediationError("A remediation reason is required")
    validate_target(namespace, deployment, ACTION_RESTART_DEPLOYMENT)

    with get_session() as session:
        existing = (
            session.query(RemediationRequest)
            .filter(
                RemediationRequest.namespace == namespace,
                RemediationRequest.resource_name == deployment,
                RemediationRequest.action == ACTION_RESTART_DEPLOYMENT,
                RemediationRequest.status.in_(["PENDING_APPROVAL", "APPROVED", "EXECUTING"]),
            )
            .order_by(desc(RemediationRequest.created_at))
            .first()
        )
        if existing:
            return existing.id

        mode = "LIVE" if cfg.hitl_execution_enabled else "DRY_RUN"
        request = RemediationRequest(
            namespace=namespace,
            resource_kind="Deployment",
            resource_name=deployment,
            action=ACTION_RESTART_DEPLOYMENT,
            reason=reason,
            requested_by=requested_by,
            status="PENDING_APPROVAL",
            execution_mode=mode,
            audit_trail=[_event("REQUESTED", requested_by, reason)],
        )
        session.add(request)
        session.flush()
        request_id = request.id

    log.info("remediation_requested", request_id=str(request_id), mode=mode)
    if notify_approver and cfg.email_enabled:
        try:
            from agent.emailer import dispatch

            dashboard_link = (
                f'<p><a href="{escape(cfg.hitl_dashboard_url)}">Open Incident Command Center</a></p>'
                if cfg.hitl_dashboard_url else "<p>Open the Incident Command Center dashboard to decide.</p>"
            )
            dispatch(
                f"[ACTION REQUIRED] Restart approval · {namespace}/{deployment}",
                "<h2>Human approval required</h2>"
                f"<p><b>Target:</b> {escape(namespace)}/{escape(deployment)}</p>"
                f"<p><b>Action:</b> Restart Deployment</p>"
                f"<p><b>Mode:</b> {escape(mode)}</p>"
                f"<p><b>Reason:</b> {escape(reason)}</p>"
                f"<p><b>Request ID:</b> {request_id}</p>"
                + dashboard_link,
                recipients=[cfg.hitl_approver_email],
            )
            log.info("remediation_approval_email_sent", request_id=str(request_id))
        except Exception as exc:
            log.error(
                "remediation_approval_email_failed",
                request_id=str(request_id), error=str(exc),
            )
    return request_id


def decide_request(
    request_id: str | uuid.UUID,
    approver_email: str,
    approve: bool,
    decision_reason: str = "",
    approval_secret: str = "",
) -> str:
    """Approve or reject a pending request after exact approver validation."""
    cfg = get_settings()
    try:
        parsed_request_id = uuid.UUID(str(request_id))
    except ValueError as exc:
        raise RemediationError("Remediation request ID is invalid") from exc
    normalized = approver_email.strip().lower()
    if normalized != cfg.hitl_approver_email.strip().lower():
        raise RemediationError("This email address is not authorized to approve remediation")
    if cfg.hitl_execution_enabled:
        expected = cfg.hitl_approval_secret.get_secret_value() if cfg.hitl_approval_secret else ""
        if not expected or not secrets.compare_digest(approval_secret, expected):
            raise RemediationError("Live approval credential is invalid")

    with get_session() as session:
        request = (
            session.query(RemediationRequest)
            .filter(RemediationRequest.id == parsed_request_id)
            .with_for_update()
            .one_or_none()
        )
        if request is None:
            raise RemediationError("Remediation request was not found")
        if request.status != "PENDING_APPROVAL":
            raise RemediationError(f"Request is already {request.status}")
        validate_target(request.namespace, request.resource_name, request.action)

        request.approver_email = normalized
        request.decision_reason = decision_reason.strip() or None
        request.decided_at = _now()
        trail = list(request.audit_trail or [])
        if not approve:
            request.status = "REJECTED"
            trail.append(_event("REJECTED", normalized, decision_reason or "No reason supplied"))
        elif not cfg.hitl_execution_enabled:
            request.status = "DRY_RUN_SUCCEEDED"
            request.executed_at = _now()
            request.result_message = "Approval validated; OpenShift execution was intentionally disabled."
            trail.append(_event("APPROVED", normalized, decision_reason or "Approved"))
            trail.append(_event("DRY_RUN", "safety-gate", request.result_message))
        else:
            request.status = "APPROVED"
            trail.append(_event("APPROVED", normalized, decision_reason or "Approved"))
        request.audit_trail = trail
        status = request.status

    log.info("remediation_decided", request_id=str(parsed_request_id), status=status)
    return status


def _deployment_state(deployment: Any) -> dict[str, Any]:
    status = deployment.status
    return {
        "generation": deployment.metadata.generation,
        "observed_generation": status.observed_generation or 0,
        "desired_replicas": deployment.spec.replicas,
        "updated_replicas": status.updated_replicas or 0,
        "ready_replicas": status.ready_replicas or 0,
        "available_replicas": status.available_replicas or 0,
        "unavailable_replicas": status.unavailable_replicas or 0,
        "images": [container.image for container in deployment.spec.template.spec.containers],
    }


def _load_apps_api():
    from kubernetes import client, config

    cfg = get_settings()
    if cfg.kubeconfig_path:
        config.load_kube_config(config_file=cfg.kubeconfig_path, context=cfg.ocp_context)
    else:
        config.load_incluster_config()
    return client.AppsV1Api()


def execute_one_approved_request() -> bool:
    """Execute at most one approved request. Called only by the scheduler."""
    cfg = get_settings()
    if not (cfg.hitl_enabled and cfg.hitl_execution_enabled):
        return False

    with get_session() as session:
        request = (
            session.query(RemediationRequest)
            .filter(RemediationRequest.status == "APPROVED")
            .order_by(RemediationRequest.created_at)
            .with_for_update(skip_locked=True)
            .first()
        )
        if request is None:
            return False
        validate_target(request.namespace, request.resource_name, request.action)
        request.status = "EXECUTING"
        request.execution_started_at = _now()
        trail = list(request.audit_trail or [])
        trail.append(_event("EXECUTION_STARTED", "scheduler", "Safety allowlist passed"))
        request.audit_trail = trail
        request_id = request.id
        namespace = request.namespace
        deployment_name = request.resource_name

    try:
        api = _load_apps_api()
        before = api.read_namespaced_deployment(deployment_name, namespace)
        pre_state = _deployment_state(before)
        restarted_at = _now().isoformat()
        patch = {
            "spec": {"template": {"metadata": {"annotations": {
                "ocp-monitor.eidiko.com/restartedAt": restarted_at
            }}}}
        }
        api.patch_namespaced_deployment(deployment_name, namespace, patch)

        deadline = time.monotonic() + cfg.hitl_rollout_timeout_seconds
        after = None
        while time.monotonic() < deadline:
            after = api.read_namespaced_deployment(deployment_name, namespace)
            state = _deployment_state(after)
            desired = state["desired_replicas"] or 0
            if (
                state["observed_generation"] >= state["generation"]
                and state["updated_replicas"] == desired
                and state["ready_replicas"] == desired
                and state["available_replicas"] == desired
                and state["unavailable_replicas"] == 0
            ):
                break
            time.sleep(5)
        else:
            raise RemediationError("Deployment rollout did not become healthy before timeout")

        _finish_execution(request_id, "SUCCEEDED", "Deployment restart completed and verified.", pre_state, _deployment_state(after))
    except Exception as exc:
        _finish_execution(request_id, "FAILED", str(exc), locals().get("pre_state"), None)
        log.error("remediation_execution_failed", request_id=str(request_id), error=str(exc))
    return True


def _finish_execution(request_id, status, message, pre_state, post_state) -> None:
    with get_session() as session:
        request = session.query(RemediationRequest).filter(RemediationRequest.id == request_id).one()
        request.status = status
        request.result_message = message
        request.pre_state = pre_state
        request.post_state = post_state
        request.executed_at = _now()
        trail = list(request.audit_trail or [])
        trail.append(_event(status, "scheduler", message))
        request.audit_trail = trail
