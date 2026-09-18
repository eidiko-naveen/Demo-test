# Phase 4A — Create Calendar Event + Confirmation + Google Meet

Added:
- Calendar write scope: calendar.events
- Deterministic create-event parser for today/tomorrow or YYYY-MM-DD
- Time and duration parsing
- Optional explicit attendee email addresses
- Confirmation required before Calendar API write
- Google Meet conference creation via conferenceDataVersion=1
- Created event result includes Calendar link and Meet link when returned

IMPORTANT:
Because the OAuth scope changed from calendar.events.readonly to calendar.events,
the existing token must be disconnected/re-authorized once.

\n## Phase 4B — Named attendee resolution\n\nAdded on top of the working Phase 4A flow:\n- Understands natural phrasing such as "Create a meeting with Abhay tomorrow..."\n- Resolves the named attendee against verified Gmail sender headers in the user's own mailbox.\n- Shows the complete resolved email address in the confirmation UI.\n- Refuses to guess when no matching person is found.\n- Refuses to auto-select when multiple email addresses match the same person.\n- Existing explicit attendee email addresses remain supported.\n- Confirmation is still required before the Calendar write.\n