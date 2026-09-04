"""Unit tests for escalation decisions; no database or Google calls are made."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from agent.nodes import (
    _is_escalation_candidate,
    _resolve_escalation_attendees,
    escalate_node,
)


class EscalationTests(TestCase):
    def setUp(self):
        self.config = SimpleNamespace(
            escalation_enabled=True,
            escalation_components_list=["cp4i"],
            escalation_fallback_owners_list=["fallback@example.com"],
            escalation_consecutive_cycles=2,
            escalation_meeting_duration_minutes=30,
            cluster_name="TEST",
        )
        self.failure = {
            "id": "F-001",
            "component": "pods",
            "resource_name": "apic-0",
            "severity": "CRITICAL",
            "message": "Pod is unavailable",
        }
        self.state = {
            "timestamp": "2026-08-27T00:00:00+00:00",
            "cluster_name": "TEST",
            "pods": [{"name": "apic-0", "namespace": "cp4i-prod"}],
            "failures": [self.failure],
            "summary": "A CP4I workload remains unavailable.",
            "resolutions": [
                {
                    "failure_id": "F-001",
                    "root_cause": "The application pod cannot start.",
                    "steps": ["Inspect pod events."],
                    "commands": ["oc describe pod apic-0 -n cp4i-prod"],
                    "docs_ref": "https://docs.example.com/runbook",
                }
            ],
        }

    def test_candidate_can_match_namespace(self):
        with patch("agent.nodes.cfg", self.config):
            self.assertTrue(_is_escalation_candidate(self.failure, "cp4i-prod"))

    def test_owner_resolution_prefers_most_specific_match(self):
        with patch("agent.nodes.cfg", self.config):
            attendees = _resolve_escalation_attendees(
                self.failure,
                "cp4i-prod",
                {
                    "cp4i": ["general@example.com"],
                    "cp4i-prod": ["specific@example.com"],
                },
            )
        self.assertEqual(attendees, ["specific@example.com"])

    def test_disabled_feature_is_a_no_op(self):
        self.config.escalation_enabled = False
        with patch("agent.nodes.cfg", self.config):
            self.assertEqual(
                escalate_node(self.state),
                {"escalations": [], "meeting_scheduled": False},
            )

    def test_eligible_failure_schedules_google_meet(self):
        result_from_google = {
            "event_id": "event-1",
            "join_url": "https://meet.google.com/example",
        }
        with (
            patch("agent.nodes.cfg", self.config),
            patch("agent.nodes._load_escalation_owners", return_value={"cp4i": ["owner@example.com"]}),
            patch("agent.nodes._persistence_threshold_reached", return_value=True),
            patch("agent.google_meet.schedule_meeting", return_value=result_from_google) as schedule,
        ):
            result = escalate_node(self.state)

        self.assertTrue(result["meeting_scheduled"])
        self.assertEqual(result["escalations"][0]["event_id"], "event-1")
        schedule.assert_called_once()
        description = schedule.call_args.args[1]
        self.assertIn("WHY THIS MEETING WAS CREATED", description)
        self.assertIn("A CP4I workload remains unavailable.", description)
        self.assertIn("The application pod cannot start.", description)
        self.assertIn("oc describe pod apic-0 -n cp4i-prod", description)
        self.assertEqual(
            result["escalations"][0]["description"],
            description,
        )

    def test_google_failure_does_not_stop_pipeline(self):
        with (
            patch("agent.nodes.cfg", self.config),
            patch("agent.nodes._load_escalation_owners", return_value={}),
            patch("agent.nodes._persistence_threshold_reached", return_value=True),
            patch("agent.google_meet.schedule_meeting", side_effect=RuntimeError("offline")),
        ):
            result = escalate_node(self.state)

        self.assertEqual(result, {"escalations": [], "meeting_scheduled": False})
