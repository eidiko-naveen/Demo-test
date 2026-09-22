"""Monitoring failures must remain visible through analysis and reporting."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from agent import llm_chains, nodes
from agent.reporter import _build_header
from agent.state import initial_state


@pytest.mark.parametrize("response", [RuntimeError("LLM unavailable"), '{}'])
def test_analysis_error_is_reported_and_persisted(monkeypatch, response):
    invoke = Mock(side_effect=response) if isinstance(response, Exception) else Mock(return_value=response)
    monkeypatch.setattr(llm_chains, "_invoke_analysis_chain", invoke)
    state = initial_state("2026-09-10T00:00:00+00:00", "TEST")
    state.update(nodes.analyze_node(state))
    assert state["analysis_error"]
    assert "ANALYSIS ERROR" in _build_header(state)
    assert "🟢 HEALTHY" not in _build_header(state)

    session = Mock()

    @contextmanager
    def get_session():
        yield session

    monkeypatch.setattr("agent.db.get_session", get_session)
    nodes.save_run_node(state)
    run = session.add.call_args.args[0]
    assert run.status == "ERROR"
    assert "analysis" in run.collection_errors

    monkeypatch.setattr(nodes, "cfg", SimpleNamespace(
        email_enabled=True, email_on_healthy=False, email_on_collection_error=True,
        cluster_name="TEST", email_recipients=["test@example.com"],
    ))
    dispatch = Mock()
    monkeypatch.setattr("agent.emailer.dispatch", dispatch)
    assert nodes.send_email_node(state)["email_sent"]
    assert "ANALYSIS ERROR" in dispatch.call_args.kwargs["subject"]


def test_unhealthy_collector_payloads_reach_analysis():
    state = initial_state("2026-09-10T00:00:00+00:00", "TEST")
    state["etcd"] = {"healthy": False, "endpoints": [{"healthy": False, "phase": "Pending"}]}
    state["cp4i_endpoints"] = [{"kind": "PlatformNavigator", "healthy": False}]
    snapshot = llm_chains._trim_snapshot(state)
    assert snapshot["etcd"] == state["etcd"]
    assert snapshot["unhealthy_endpoints"] == state["cp4i_endpoints"]
    assert snapshot["healthy_counts"]["endpoints"] == 0


def test_certificate_threshold_is_inclusive_and_configurable(monkeypatch):
    monkeypatch.setattr(llm_chains, "cfg", SimpleNamespace(cert_expiry_warning_days=45))
    assert llm_chains._is_cert_unhealthy({"days_remaining": 45})
    assert not llm_chains._is_cert_unhealthy({"days_remaining": 46})


def test_partial_collection_error_is_not_lost():
    result = nodes.aggregate_node({"pods": [
        {"name": "failed-pod", "phase": "Failed"},
        {"namespace": "restricted", "error": "Forbidden"},
    ]})
    assert result["collection_errors"]["pods"] == "Forbidden"


def test_incomplete_collection_cannot_have_healthy_summary(monkeypatch):
    monkeypatch.setattr(llm_chains, "run_analysis", lambda state: ([], "All healthy"))
    result = nodes.analyze_node({"collection_errors": {"pods": "Forbidden"}})
    assert "Monitoring incomplete" in result["summary"]
    assert "All healthy" not in result["summary"]


def test_optional_platform_navigator_check_can_be_disabled(monkeypatch):
    from agent import tools

    monkeypatch.setattr(tools, "cfg", SimpleNamespace(
        cp4i_platform_navigator_enabled=False, cp4i_endpoints_list=[],
    ))
    monkeypatch.setattr(tools, "_load_kube", lambda: None)
    api = Mock()
    monkeypatch.setattr(tools.client, "CustomObjectsApi", lambda: api)
    assert tools.check_cp4i_endpoints.invoke({}) == []
    api.list_namespaced_custom_object.assert_not_called()
