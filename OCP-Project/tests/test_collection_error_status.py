"""Collection failures must never be presented as a healthy cluster."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from agent.nodes import send_email_node
from agent.reporter import _build_header


class CollectionErrorStatusTests(TestCase):
    def setUp(self):
        self.state = {
            "timestamp": "2026-08-31T00:00:00+00:00",
            "cluster_name": "TEST",
            "failures": [],
            "collection_errors": {"nodes": "cluster unavailable"},
            "report_html": "<p>collection failed</p>",
        }

    def test_report_header_marks_collection_error(self):
        header = _build_header(self.state)
        self.assertIn("COLLECTION ERROR", header)
        self.assertNotIn("🟢 HEALTHY", header)

    def test_email_subject_marks_collection_error(self):
        config = SimpleNamespace(
            email_enabled=True,
            email_on_collection_error=True,
            email_on_healthy=True,
            cluster_name="TEST",
            email_recipients=["recipient@example.com"],
        )
        with (
            patch("agent.nodes.cfg", config),
            patch("agent.emailer.dispatch") as dispatch,
        ):
            result = send_email_node(self.state)

        self.assertTrue(result["email_sent"])
        self.assertIn("COLLECTION ERROR", dispatch.call_args.kwargs["subject"])
        self.assertNotIn("HEALTHY", dispatch.call_args.kwargs["subject"])
