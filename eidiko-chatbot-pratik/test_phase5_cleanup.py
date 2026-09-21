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
assert r and r["person"] == "Yash"
assert r["topic"] == "OCP"
assert r["explicit_time"] == (16, 0)

# This must go to the Calendar free-slot parser, not Gmail->Calendar.
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

assert _is_context_followup_request("Send it to Abhay")
assert _is_context_followup_request("Schedule a meeting with him tomorrow")
assert not _is_context_followup_request("Send an email to Abhay")
assert not _is_context_followup_request("Schedule a meeting with Kousik next week")

_conversation_context.clear()
_conversation_context.update({"last_file": {"id": "1", "name": "old.pdf"}, "last_person": "Abhay", "last_email": None})
assert _parse_phase6b_followup("Send an email to Abhay") is None
assert _parse_phase6b_followup("Send it to Abhay") is not None

_pending_actions["old"] = {"type": "send_gmail"}
_reset_request_state(False)
assert not _pending_actions
assert _conversation_context["last_file"] is None

_conversation_context["last_file"] = {"id": "2", "name": "current.pdf"}
_pending_actions["new"] = {"type": "send_gmail"}
_reset_request_state(True)
assert not _pending_actions
assert _conversation_context["last_file"]["name"] == "current.pdf"

print("Phase 5 cleanup regression tests passed.")
