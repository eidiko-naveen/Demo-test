"""Lightweight Phase 6B parser smoke tests.
Run after installing requirements with: python test_phase6b.py
"""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# These tests intentionally avoid Google API calls. They are useful for checking
# the natural-language routing before connecting a real account.
from app import _parse_phase6b_gmail_calendar_request, _parse_phase6b_combined_file_meeting

cases = [
    "Find the latest email from Abhay about CP4I and schedule a meeting with him tomorrow at 4 PM.",
    "Find the latest email from Abhay about CP4I and schedule a meeting with him tomorrow when I'm free.",
    "Find the CP4I presentation, send it to Abhay, and schedule a meeting with him tomorrow.",
]

assert _parse_phase6b_gmail_calendar_request(cases[0])["person"] == "Abhay"
assert _parse_phase6b_gmail_calendar_request(cases[0])["topic"] == "CP4I"
assert _parse_phase6b_gmail_calendar_request(cases[0])["explicit_time"] == (16, 0)
assert _parse_phase6b_gmail_calendar_request(cases[1])["free"] is True
assert _parse_phase6b_combined_file_meeting(cases[2]) == ("CP4I presentation", "Abhay")
print("Phase 6B parser smoke tests: PASS")


# --- Phase 5 cleanup regressions --------------------------------------------
from app import (
    _parse_phase6b_gmail_calendar_request,
    _parse_calendar_free_slot_request,
    _parse_phase6b_followup,
    _is_context_followup_request,
    _conversation_context,
    _pending_actions,
    _reset_request_state,
)

r = _parse_phase6b_gmail_calendar_request(
    "Find the latest email from Yash about OCP and schedule a meeting with him tomorrow at 4 PM."
)
assert r and r["person"] == "Yash" and r["topic"] == "OCP"
assert r["explicit_time"] == (16, 0)

# Ordinary "next week when I'm free" requests must be handled by Calendar,
# not mistaken for Gmail -> Calendar.
assert _parse_phase6b_gmail_calendar_request(
    "Schedule a 30-minute meeting with Kousik next week when I'm free."
) is None
r = _parse_calendar_free_slot_request(
    "Schedule a 30-minute meeting with Kousik next week when I'm free."
)
assert r and r["people"] == ["Kousik"] and r["duration_minutes"] == 30

r = _parse_calendar_free_slot_request(
    "Schedule a 30-minute meeting with Kousik and Yash next week when I'm free."
)
assert r and r["people"] == ["Kousik", "Yash"]

# A normal email must never reuse a previous Drive file implicitly.
_conversation_context.clear()
_conversation_context.update({
    "last_file": {"id": "old", "name": "old.pdf"},
    "last_person": "Abhay",
    "last_email": None,
})
assert _parse_phase6b_followup("Send an email to Abhay") is None
assert _parse_phase6b_followup("Send it to Abhay") is not None

assert _is_context_followup_request("Send it to Abhay")
assert _is_context_followup_request("Schedule a meeting with him tomorrow")
assert not _is_context_followup_request("Send an email to Abhay")
assert not _is_context_followup_request("Schedule a meeting with Kousik next week")

_pending_actions["stale"] = {"type": "send_gmail"}
_reset_request_state(False)
assert not _pending_actions
assert _conversation_context["last_file"] is None

print("Phase 5 cleanup regressions passed.")
