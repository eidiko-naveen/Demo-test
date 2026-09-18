from types import SimpleNamespace

import pytest

from agent import remediation
from agent import nodes
from agent.config import Settings


def _cfg(**overrides):
    values = {
        "hitl_enabled": True,
        "hitl_execution_enabled": False,
        "hitl_allowed_namespace": "eidiko-chatbot",
        "hitl_allowed_deployment": "bankingchatbot",
        "hitl_approver_email": "yash.eidiko@gmail.com",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_allowlist_accepts_only_configured_restart(monkeypatch):
    monkeypatch.setattr(remediation, "get_settings", lambda: _cfg())

    remediation.validate_target(
        "eidiko-chatbot", "bankingchatbot", remediation.ACTION_RESTART_DEPLOYMENT
    )

    with pytest.raises(remediation.RemediationError, match="not allowlisted"):
        remediation.validate_target(
            "default", "bankingchatbot", remediation.ACTION_RESTART_DEPLOYMENT
        )
    with pytest.raises(remediation.RemediationError, match="not allowed"):
        remediation.validate_target("eidiko-chatbot", "bankingchatbot", "scale")


def test_execution_gate_does_not_load_kubernetes_client(monkeypatch):
    monkeypatch.setattr(remediation, "get_settings", lambda: _cfg())
    monkeypatch.setattr(
        remediation,
        "_load_apps_api",
        lambda: pytest.fail("Kubernetes client must not load while execution is disabled"),
    )

    assert remediation.execute_one_approved_request() is False


def test_live_execution_requires_second_factor():
    with pytest.raises(ValueError, match="HITL_APPROVAL_SECRET"):
        Settings(
            _env_file=None,
            groq_api_key="test",
            postgres_password="test",
            email_enabled=False,
            hitl_enabled=True,
            hitl_execution_enabled=True,
            hitl_allowed_namespace="eidiko-chatbot",
            hitl_allowed_deployment="bankingchatbot",
            hitl_approver_email="yash.eidiko@gmail.com",
        )


def test_auto_proposal_requires_exact_deployment_ownership(monkeypatch):
    state = {
        "failures": [{
            "id": "F-1", "severity": "CRITICAL",
            "resource_name": "bankingchatbot-abc-123", "message": "CrashLoop",
        }],
        "pods": [{
            "name": "bankingchatbot-abc-123", "namespace": "eidiko-chatbot",
            "deployment": "bankingchatbot", "phase": "Running",
        }],
        "resolutions": [],
    }
    created = []
    monkeypatch.setattr(
        remediation, "create_request",
        lambda *args, **kwargs: created.append((args, kwargs)) or
        "00000000-0000-0000-0000-000000000001",
    )

    result = nodes.propose_remediation_node(state)
    assert result["remediation_requests"][0]["deployment"] == "bankingchatbot"
    assert len(created) == 1

    state["pods"][0]["deployment"] = "another-deployment"
    assert nodes.propose_remediation_node(state) == {"remediation_requests": []}
    assert len(created) == 1
