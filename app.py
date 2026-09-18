"""
EIDIKO Chatbot — local Gmail/Drive/Calendar assistant.

IMPORTANT SECURITY NOTES (read README.md for the full picture):
  - Runs locally on your machine only (127.0.0.1). Not deployed publicly.
  - Uses Gmail read/search plus explicit Gmail send permission, Calendar read/write permission, and Drive action scope. Gmail sends and Drive moves require explicit user confirmation.
  - It NEVER extracts or displays PAN/Aadhaar numbers, passwords, PINs,
    OTPs, or similar secrets — only links to the email/file that contains
    them, which you open yourself in Gmail/Drive.
  - Any queries containing words like "password", "otp", "cvv", "pin",
    "private key", "api key" are refused outright — see redact.py.
"""

import os
import re
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote
from flask import Flask, request, jsonify, render_template, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

import google_client
import claude_client
import query_intent
from redact import redact, is_blocked_query

load_dotenv()

app = Flask(__name__)
# OCP/Ingress terminates TLS and forwards the original scheme/host.
# This keeps Google OAuth redirect_uri correct behind an OpenShift Route.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Single-user local app: pending confirmations live only in memory and expire
# when the process restarts. No action is executed without explicit confirm.
_pending_actions = {}
# Lightweight conversation context for this single-user local app.
# Stores only non-sensitive references (file/person/event metadata) so follow-up
# phrases like "send it to him" can resolve naturally without re-searching blindly.
_conversation_context = {"last_file": None, "last_person": None, "last_email": None}


def _is_context_followup_request(text: str) -> bool:
    """Use prior context only when the user explicitly refers to it."""
    q = (text or "").strip().lower()
    if not q:
        return False
    has_action = re.search(r"\b(?:send|email|mail|schedule|book|create|set\s+up|share)\b", q)
    has_reference = re.search(r"\b(?:it|that|this|him|her|them|same)\b", q)
    return bool(has_action and has_reference)


def _reset_request_state(preserve_context: bool = False):
    """Clear stale pending actions and, for new requests, stale conversation context."""
    _pending_actions.clear()
    if not preserve_context:
        _conversation_context.clear()
        _conversation_context.update({"last_file": None, "last_person": None, "last_email": None})


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def status():
    return jsonify({"authenticated": google_client.is_authenticated()})


@app.route("/health/live")
def health_live():
    """Kubernetes liveness probe: process is alive and HTTP is serving."""
    return jsonify({"status": "ok"}), 200


@app.route("/health/ready")
def health_ready():
    """Kubernetes readiness probe: app is initialized and can accept traffic.

    Google/Claude credentials are intentionally NOT required here because
    OAuth is user/session state and a newly started pod may legitimately
    begin unauthenticated.
    """
    return jsonify({"status": "ready"}), 200


@app.route("/api/authorize")
def authorize():
    """Non-blocking: returns a Google sign-in URL for the browser to open
    in a new tab. Does NOT wait for the user to complete sign-in — see
    /oauth2callback, which Google redirects back to when they're done."""
    try:
        redirect_uri = url_for("oauth2callback", _external=True)
        auth_url = google_client.build_auth_url(redirect_uri)
        return jsonify({"ok": True, "authUrl": auth_url})
    except FileNotFoundError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": f"Could not start Google sign-in: {e}"}), 500


@app.route("/oauth2callback")
def oauth2callback():
    """Google redirects here after the user approves (or cancels) access
    in the tab opened from /api/authorize. Runs as a normal, fast request
    — nothing in this app ever blocks a whole server thread on OAuth."""
    error = request.args.get("error")
    if error:
        return (
            f"<h3>Google sign-in was cancelled ({error}).</h3>"
            "<p>You can close this tab and click \"Connect Google Account\" again.</p>"
        )

    state = request.args.get("state", "")
    try:
        google_client.finish_auth_flow(state, request.url)
    except Exception as e:  # noqa: BLE001
        return f"<h3>Sign-in failed: {e}</h3><p>Close this tab and try again.</p>", 400

    return (
        "<h3>Google account connected ✅</h3>"
        "<p>Gmail read/search + send access, Calendar read/write access, plus Drive access for confirmed file actions, granted. You can close this tab "
        "and go back to EIDIKO.</p>"
    )


@app.route("/api/disconnect", methods=["POST"])
def disconnect():
    google_client.disconnect()
    return jsonify({"ok": True})






def _parse_find_and_send_drive_request(text: str):
    """Parse 'find/take <Drive description> and send it to <person>'.

    The recipient is intentionally a person name here; it is resolved
    against verified Gmail sender headers before confirmation.
    """
    q=(text or "").strip()
    m=re.match(
        r"^(?:find|locate|take|get)\s+(?:the\s+)?(.+?)\s+(?:and\s+)?send\s+(?:it|that|this|the\s+file)?\s+to\s+([A-Za-z][A-Za-z'\- ]{1,60})\s*[.!]?$",
        q,re.I
    )
    if not m:
        return None
    source=m.group(1).strip(" .")
    person=m.group(2).strip(" .")
    if not source or not person:
        return None
    # Do not capture an explicit email address here; the existing explicit
    # file-send parser handles those cases.
    if "@" in person:
        return None
    return source, person


def _parse_latest_email_request(text: str):
    """Return a person for 'latest email from X and summarize' requests."""
    q=(text or "").strip()
    if not re.search(r"\b(latest|most recent|newest)\b", q, re.I):
        return None
    if not re.search(r"\b(email|mail|message)\b", q, re.I):
        return None
    if not re.search(r"\b(summarize|summary|summarise|what does|what's in)\b", q, re.I):
        return None
    m=re.search(r"\bfrom\s+([A-Za-z][A-Za-z'\-]{1,40})\b", q, re.I)
    if not m:
        return None
    return m.group(1).strip()


def _parse_person_document_last_week_request(text: str):
    """Return the sender/person for document requests constrained to last week.

    Handles natural forms such as:
      - "Find the document Yash sent me last week."
      - "Find the document from GoIndiGo sent me last week."
      - "Find the file Abhay shared last week."

    IMPORTANT: capture the person BEFORE the time phrase. The previous
    implementation could capture "last" from "last week" as the person.
    """
    q=(text or "").strip()
    if not re.search(r"\blast\s+week\b", q, re.I):
        return None
    if not re.search(r"\b(document|file|attachment|report|pdf)\b", q, re.I):
        return None

    # Most natural form: "document Yash sent me last week"
    m=re.search(
        r"\b(?:document|file|attachment|report|pdf)\s+"
        r"([A-Za-z][A-Za-z0-9@._'\- ]{1,80}?)\s+"
        r"(?:sent|shared|emailed)\b",
        q, re.I
    )
    if m:
        person=m.group(1).strip(" .,:;")
        # Remove connector words that may occur in "from X".
        person=re.sub(r"^(?:from|by)\s+", "", person, flags=re.I).strip()
        if person and person.lower() not in {"the","me","last","week"}:
            return person

    # Form: "document from Yash sent me last week"
    m=re.search(
        r"\b(?:document|file|attachment|report|pdf)\s+from\s+"
        r"([A-Za-z][A-Za-z0-9@._'\- ]{1,80}?)\s+"
        r"(?:sent|shared|emailed)\b",
        q, re.I
    )
    if m:
        person=m.group(1).strip(" .,:;")
        if person and person.lower() not in {"the","me","last","week"}:
            return person

    # Form: "document sent by Yash last week"
    m=re.search(
        r"\b(?:sent|shared|emailed)\s+by\s+"
        r"([A-Za-z][A-Za-z0-9@._'\- ]{1,80}?)\s+"
        r"last\s+week\b",
        q, re.I
    )
    if m:
        person=m.group(1).strip(" .,:;")
        if person and person.lower() not in {"the","me","last","week"}:
            return person

    # Form: "document from Yash last week"
    m=re.search(
        r"\b(?:document|file|attachment|report|pdf)\s+from\s+"
        r"([A-Za-z][A-Za-z0-9@._'\- ]{1,80}?)\s+"
        r"last\s+week\b",
        q, re.I
    )
    if m:
        person=m.group(1).strip(" .,:;")
        if person and person.lower() not in {"the","me","last","week"}:
            return person

    return None




def _parse_phase6b_gmail_calendar_request(text: str):
    """Parse Gmail -> Calendar combined requests.

    Examples:
      Find the latest email from Abhay about CP4I and schedule a meeting with him tomorrow at 4 PM.
      Find the latest email from Abhay about CP4I and schedule a meeting with him tomorrow when I'm free.
      Find the CP4I presentation, send it to Abhay, and schedule a meeting with him tomorrow.

    This parser is intentionally narrow; ordinary Gmail/Drive/Calendar requests
    continue through the existing handlers below.
    """
    q = (text or "").strip()
    if not re.search(r"\b(schedule|book|create|set up)\b", q, re.I):
        return None
    if not re.search(r"\b(meeting|appointment|call)\b", q, re.I):
        return None
    # This handler is only for Gmail -> Calendar requests. Ordinary Calendar
    # requests (for example, "schedule ... Kousik next week") belong to the
    # free-slot/create-calendar handlers below.
    if not re.search(r"\blatest\s+(?:email|mail|message)\s+from\b", q, re.I):
        return None

    # Person from the explicit "latest email from X" clause.
    # meeting clause. The caller verifies the resolved address against Gmail.
    person = None
    # Prefer the explicitly named sender in "latest email from X".
    # Pronouns in the meeting clause (him/her/them) refer to that sender.
    m = re.search(r"\blatest\s+email\s+from\s+([A-Za-z][A-Za-z0-9._'\- ]{0,60}?)(?=\s+about\b|\s+and\s+(?:schedule|book|create|set\s+up)\b|[,.!?]|$)", q, re.I)
    if m:
        person = m.group(1).strip(" .,-")
    if not person:
        m = re.search(r"\b(?:meeting|appointment|call)\s+with\s+([^,!.?]+?)(?=\s+(?:tomorrow|today|on\s+\d{4}-\d{1,2}-\d{1,2}|at\s+\d|for\s+\d|when\s+I(?:'m| am)\s+(?:free|available))\b|$)", q, re.I)
        if m:
            name = m.group(1).strip(" .,-")
            if name.lower() not in {"him", "her", "them"}:
                person = name
    if not person:
        return None

    topic = None
    m = re.search(r"\blatest\s+email\s+from\s+[A-Za-z][A-Za-z'\-]{1,40}\s+about\s+(.+?)(?=\s+and\s+(?:schedule|book|create)|$)", q, re.I)
    if m:
        topic = m.group(1).strip(" .,-")

    day = None
    tz = ZoneInfo("Asia/Kolkata")
    now = datetime.now(tz)
    if re.search(r"\btomorrow\b", q, re.I):
        day = (now + timedelta(days=1)).date()
    elif re.search(r"\btoday\b", q, re.I):
        day = now.date()

    # Explicit time, otherwise "when I'm free" means find the first free slot.
    tm = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", q, re.I)
    explicit_time = None
    if tm:
        hour = int(tm.group(1)); minute = int(tm.group(2) or 0); ap = (tm.group(3) or "").lower()
        if ap == "pm" and hour < 12: hour += 12
        if ap == "am" and hour == 12: hour = 0
        if not ap and hour <= 7: hour += 12
        explicit_time = (hour, minute)

    free = bool(re.search(r"\bfree\b|\bavailable\b", q, re.I))
    duration_minutes = 30
    dm = re.search(r"\bfor\s+(\d+)\s*(minute|minutes|min|mins|hour|hours|hr|hrs)\b", q, re.I)
    if dm:
        n = int(dm.group(1))
        duration_minutes = n if dm.group(2).lower().startswith("min") else n * 60

    return {
        "person": person,
        "topic": topic,
        "day": day,
        "explicit_time": explicit_time,
        "free": free,
        "duration_minutes": duration_minutes,
    }


def _parse_phase6b_combined_file_meeting(text: str):
    """Parse the final end-to-end request: Drive file + Gmail recipient + Calendar.

    Example: "Find the CP4I presentation, send it to Abhay, and schedule a meeting
    with him tomorrow."  Both writes are placed behind one confirmation.
    """
    q = (text or "").strip()
    if not re.search(r"\b(find|locate|take|get)\b", q, re.I):
        return None
    if not re.search(r"\b(send|email|mail)\b", q, re.I):
        return None
    if not re.search(r"\b(schedule|book|create|set up)\b", q, re.I):
        return None
    if not re.search(r"\b(meeting|appointment|call)\b", q, re.I):
        return None

    m = re.match(
        r"^(?:find|locate|take|get)\s+(?:the\s+)?(.+?)\s*,?\s+"
        r"(?:and\s+)?(?:send|email|mail)\s+(?:it|that|this|the\s+file)?\s*to\s+"
        r"([A-Za-z][A-Za-z'\- ]{1,60})\s*,?\s+"
        r"(?:and\s+)?(?:schedule|book|create|set\s+up)\s+(?:a\s+)?(?:meeting|appointment|call)\s+"
        r"(?:with\s+)?(?:him|her|them|(?:[A-Za-z][A-Za-z'\-]{1,40}))"
        r"(?:\s+tomorrow|\s+today|\s+on\s+\d{4}-\d{1,2}-\d{1,2})?"
        r"(?:\s+when\s+I(?:'m|\s+am)\s+(?:free|available))?"
        r"(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?"
        r"(?:\s+for\s+\d+\s*(?:minute|minutes|min|mins|hour|hours|hr|hrs))?\s*[.!]?$",
        q, re.I
    )
    if not m:
        return None
    source = m.group(1).strip(" .,")
    recipient_person = m.group(2).strip(" .,")
    if not source or not recipient_person or "@" in recipient_person:
        return None
    # Prevent the source phrase from swallowing the scheduling clause.
    source = re.sub(r"\s+(?:and\s+)?send\s*$", "", source, flags=re.I).strip(" .,")
    return source, recipient_person



def _parse_phase6b_followup(text: str):
    """Resolve short follow-ups using the local conversation context."""
    q = (text or "").strip()
    last_file = _conversation_context.get("last_file")
    last_person = _conversation_context.get("last_person")
    if not last_file or not re.search(r"\b(send|email|mail)\b", q, re.I):
        return None
    # Do not treat every new email as a follow-up to the previous file.
    if not re.search(r"\b(?:it|that|this|the\s+(?:file|document))\b", q, re.I):
        return None
    m = re.search(r"\b(?:to|for)\s+([A-Za-z][A-Za-z'\- ]{1,50})\b", q, re.I)
    recipient_person = m.group(1).strip(" .,") if m else last_person
    if recipient_person and recipient_person.lower() in {"him", "her", "them"}:
        recipient_person = last_person
    schedule = bool(re.search(r"\b(schedule|book|create|set up)\b", q, re.I)) and bool(re.search(r"\b(meeting|appointment|call)\b", q, re.I))
    if not recipient_person:
        return None
    return {"file": last_file, "person": recipient_person, "schedule": schedule}

def _phase6b_resolve_person(creds, person):
    resolved = google_client.resolve_person_emails(creds, person)
    if not resolved:
        return None, f'I could not find a Gmail contact matching "{person}". Please provide their complete email address.'
    if len(resolved) > 1:
        return None, f'I found multiple email addresses for "{person}". Please provide the complete email address to avoid inviting the wrong person.'
    _conversation_context["last_person"] = person
    return resolved[0], None


def _phase6b_find_latest_email(creds, person, topic=None):
    keywords = [topic] if topic else None
    matches = google_client.search_gmail(creds, keywords=keywords, person=person, max_results=20)
    matches = [m for m in matches if m.get("sender_match")]
    if topic:
        topic_l = topic.lower()
        # Keep results whose subject/snippet actually mention the requested topic.
        filtered = [m for m in matches if topic_l in (m.get("subject", "") + " " + m.get("snippet", "")).lower()]
        if filtered:
            matches = filtered
    return matches[0] if matches else None


def _phase6b_calendar_target(day, explicit_time, duration_minutes, creds, use_free=False):
    tz = ZoneInfo("Asia/Kolkata")
    if use_free:
        # For "tomorrow when I'm free", search one concrete day rather than next week.
        events = _calendar_week_events(creds, day, 1)
        duration = timedelta(minutes=duration_minutes)
        windows = [(10,0,13,0), (14,0,17,0), (17,30,19,0)]
        for sh, sm, eh, em in windows:
            candidate = datetime(day.year, day.month, day.day, sh, sm, tzinfo=tz)
            window_end = datetime(day.year, day.month, day.day, eh, em, tzinfo=tz)
            while candidate + duration <= window_end:
                if not any(candidate < en and candidate + duration > st for _, st, en in events):
                    return candidate, candidate + duration
                candidate += timedelta(minutes=30)
        return None, None
    if day is None or explicit_time is None:
        return None, None
    hour, minute = explicit_time
    start = datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)
    return start, start + timedelta(minutes=duration_minutes)

def _parse_calendar_cancel_all_request(text: str):
    """Parse requests to cancel all calendar events in a day/window."""
    q = (text or "").strip()
    if not re.search(r"\b(cancel|delete|remove)\b", q, re.I):
        return None
    if not re.search(r"\b(all|every)\b", q, re.I):
        return None
    if not re.search(r"\b(meetings?|events?|appointments?|calls?)\b", q, re.I):
        return None
    if re.search(r"\btomorrow\b", q, re.I):
        day = datetime.now(ZoneInfo("Asia/Kolkata")).date() + timedelta(days=1)
        return {"label": "tomorrow", "start_day": day}
    if re.search(r"\btoday\b", q, re.I):
        day = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        return {"label": "today", "start_day": day}
    return None


def _parse_calendar_free_slot_request(text: str):
    """Parse 'schedule ... next week when I'm free' requests."""
    q = (text or "").strip()
    if not re.search(r"\b(schedule|book|create|set up)\b", q, re.I):
        return None
    if not re.search(r"\b(meeting|event|appointment|call)\b", q, re.I):
        return None
    if not re.search(r"\bnext week\b", q, re.I) or not re.search(r"\bfree\b|\bavailable\b", q, re.I):
        return None

    # Extract people from "with A and B"; reuse the same conservative name
    # parsing rules as normal event creation.
    people = []
    m = re.search(r"\b(?:meeting|event|appointment|call)\s+with\s+(.+?)(?=\s+next\s+week|\s+when\s+|\s+for\s+\d+|\s+at\s+|$)", q, re.I)
    if m:
        raw = m.group(1).strip(" ,.-")
        for part in re.split(r"\s*(?:,|\band\b|\&)\s*", raw, flags=re.I):
            part = part.strip(" ,.-")
            if part:
                people.append(part)

    dm = re.search(r"\bfor\s+(\d+)\s*(minute|minutes|min|mins|hour|hours|hr|hrs)\b", q, re.I)
    duration_minutes = 30
    if dm:
        n = int(dm.group(1))
        duration_minutes = n if dm.group(2).lower().startswith(("min",)) else n * 60

    return {"people": people, "duration_minutes": duration_minutes}


def _calendar_week_events(creds, start_day, days=7):
    """Fetch calendar events for a concrete local-date window."""
    tz = ZoneInfo("Asia/Kolkata")
    start = datetime.combine(start_day, datetime.min.time(), tzinfo=tz)
    end = start + timedelta(days=days)
    service = google_client._calendar_service(creds)
    resp = service.events().list(
        calendarId="primary",
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=250,
    ).execute()
    events = []
    for e in resp.get("items", []):
        if e.get("status") == "cancelled":
            continue
        s = e.get("start", {}).get("dateTime")
        en = e.get("end", {}).get("dateTime")
        if s and en:
            try:
                events.append((e, datetime.fromisoformat(s.replace("Z","+00:00")).astimezone(tz),
                               datetime.fromisoformat(en.replace("Z","+00:00")).astimezone(tz)))
            except ValueError:
                continue
    return events


def _find_next_free_slot(creds, duration_minutes=30):
    """Find the first genuinely free weekday slot next week.

    Office availability:
      Mon-Fri: 10:00 AM-7:00 PM IST
      Break:   1:00-2:00 PM
      Break:   5:00-5:30 PM

    Existing Calendar events are checked for overlap.
    """
    tz = ZoneInfo("Asia/Kolkata")
    now = datetime.now(tz)
    next_monday = (now + timedelta(days=7-now.weekday())).date()
    events = _calendar_week_events(creds, next_monday, 7)
    duration = timedelta(minutes=duration_minutes)

    working_windows = [
        (10, 0, 13, 0),   # 10:00 AM - 1:00 PM
        (14, 0, 17, 0),   # 2:00 PM - 5:00 PM
        (17, 30, 19, 0),  # 5:30 PM - 7:00 PM
    ]

    for offset in range(7):
        day = next_monday + timedelta(days=offset)
        if day.weekday() >= 5:
            continue

        for start_hour, start_minute, end_hour, end_minute in working_windows:
            candidate = datetime(
                day.year, day.month, day.day,
                start_hour, start_minute, tzinfo=tz
            )
            window_end = datetime(
                day.year, day.month, day.day,
                end_hour, end_minute, tzinfo=tz
            )

            while candidate + duration <= window_end:
                overlap = any(
                    candidate < en and candidate + duration > st
                    for _, st, en in events
                )
                if not overlap:
                    return candidate, candidate + duration

                candidate += timedelta(minutes=30)

    return None, None

def _parse_calendar_create_request(text: str):
    """Parse common Calendar creation requests.

    Supports explicit titles, natural "meeting with <person>" and
    "meeting with <person> and <person>" phrasing, today/tomorrow or
    YYYY-MM-DD dates, time/duration, and explicit attendee email addresses.
    Named people are resolved by the caller against verified Gmail headers.
    """
    q = (text or "").strip()
    if not re.search(r"\b(create|schedule|book|add)\b", q, re.I):
        return None
    if not re.search(r"\b(event|meeting|calendar|appointment|call)\b", q, re.I):
        return None
    if not re.search(r"\b(today|tomorrow|on\s+\d{4}-\d{1,2}-\d{1,2})\b", q, re.I):
        return None

    email_pat = r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"

    title = None
    attendee_person = None
    attendee_people = []

    # "Create a meeting with Abhay tomorrow..." OR
    # "Create a meeting with Abhay and Jaina tomorrow..."
    # Capture the attendee phrase up to the first scheduling detail. Names
    # are resolved later against verified Gmail sender headers.
    person_match = re.search(
        r"\b(?:meeting|event|appointment|call)\s+with\s+"
        r"(.+?)(?=\s+(?:today|tomorrow|on\s+\d{4}-\d{1,2}-\d{1,2}|"
        r"\d{4}-\d{1,2}-\d{1,2}|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?|"
        r"for\s+\d+\s*(?:hour|hours|hr|hrs|minute|minutes|min|mins)\b)|$)",
        q, re.I
    )
    if person_match:
        attendee_text = person_match.group(1).strip(" ,.-")
        # Split multiple people on natural separators. Keep multi-word names
        # intact, e.g. "Abhay Badwaik and Jaina Sumith Gupta".
        for part in re.split(r"\s*(?:,|\band\b|\&)\s*", attendee_text, flags=re.I):
            part = part.strip(" ,.-")
            if part:
                attendee_people.append(part)
        if attendee_people:
            attendee_person = attendee_people[0]
            title = "Meeting with " + " and ".join(attendee_people)

    # Explicit title always wins: "called CP4I Discussion".
    m = re.search(
        r'(?:called|named)\s+["“]?([^"”]+?)["”]?(?=\s+'
        r'(?:tomorrow|today|on\s+\d{4}-|\d{4}-)|\s+at\s+|\s+for\s+'
        r'|\s+and\s+invite|\s+with\s+' + email_pat + r'|$)',
        q, re.I
    )
    if m:
        title = m.group(1).strip(" ,.-")

    if not title:
        m = re.search(r'(?:event|meeting)\s+["“]([^"”]+)["”]', q, re.I)
        if m:
            title = m.group(1).strip()

    if not title:
        # "schedule CP4I Discussion tomorrow..."
        m = re.search(
            r'^(?:create|schedule|book|add)\s+(?:a\s+)?(?:calendar\s+)?'
            r'(?:event|meeting)\s+(.+?)(?=\s+'
            r'(?:tomorrow|today|on\s+\d{4}-|\d{4}-\d{1,2}-\d{1,2})\b)',
            q, re.I
        )
        if m:
            title = m.group(1).strip(" ,.-")

    if not title:
        return None

    tz = ZoneInfo("Asia/Kolkata")
    now = datetime.now(tz)
    if re.search(r"\btomorrow\b", q, re.I):
        day = (now + timedelta(days=1)).date()
    elif re.search(r"\btoday\b", q, re.I):
        day = now.date()
    else:
        m = re.search(r"\b(?:on\s+)?(\d{4})-(\d{1,2})-(\d{1,2})\b", q)
        if not m:
            return None
        day = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()

    tm = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", q, re.I)
    if not tm:
        return None
    hour = int(tm.group(1))
    minute = int(tm.group(2) or 0)
    ap = (tm.group(3) or "").lower()
    if ap == "pm" and hour < 12:
        hour += 12
    if ap == "am" and hour == 12:
        hour = 0
    if not ap and hour <= 7:
        hour += 12
    start = datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)

    dur = timedelta(minutes=30)
    dm = re.search(
        r"\bfor\s+(\d+)\s*(hour|hours|hr|hrs|minute|minutes|min|mins)\b",
        q, re.I
    )
    if dm:
        n = int(dm.group(1))
        unit = dm.group(2).lower()
        dur = timedelta(minutes=n if unit.startswith("min") else n * 60)
    end = start + dur

    attendees = re.findall(email_pat, q, re.I)
    attendees = list(dict.fromkeys(a.lower() for a in attendees))

    return {
        "summary": title,
        "start": start,
        "end": end,
        "attendees": attendees,
        "attendee_person": attendee_person,
        "attendee_people": attendee_people,
    }

def _calendar_create_action_result(parsed, action_id):
    start=parsed["start"].strftime("%d %b %Y, %I:%M %p")
    end=parsed["end"].strftime("%I:%M %p")
    people=", ".join(parsed["attendees"]) if parsed["attendees"] else "None"
    return {"action":{
        "id":action_id,
        "type":"create_calendar_event",
        "title":"Create Calendar event",
        "summary":parsed["summary"],
        "start":start,
        "end":end,
        "attendees":parsed["attendees"],
        "confirm_text":f'Create "{parsed["summary"]}" on {start}–{end} with a Google Meet link?',
        "meet":True,
        "attendee_text":people
    }}


def _parse_calendar_modify_request(text: str):
    """Parse requests that reschedule an existing calendar event.

    Supported examples:
      change my "Meeting with Abhay" to 5 PM tomorrow
      reschedule Meeting with Abhay to 6 PM on 2026-08-30
      move my OCP meeting to 4:30 PM tomorrow
    This phase intentionally changes only date/time, not attendees or Meet data.
    """
    q = (text or "").strip()
    if not re.search(r"\b(change|reschedule|move|update)\b", q, re.I):
        return None
    if not re.search(r"\b(event|meeting|appointment|call)\b|\bmy\s+[\"“']?[^\"”']+", q, re.I):
        return None
    tm = re.search(r"\bto\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", q, re.I)
    if not tm:
        return None
    hour = int(tm.group(1)); minute = int(tm.group(2) or 0); ap = (tm.group(3) or '').lower()
    if ap == 'pm' and hour < 12: hour += 12
    if ap == 'am' and hour == 12: hour = 0
    if not ap and hour <= 7: hour += 12

    # Target event is normally between "my"/"event" and "to <time>".
    prefix = re.search(r"(?:change|reschedule|move|update)\s+(?:my\s+|the\s+)?(?:event\s+|meeting\s+|appointment\s+|call\s+)?[\"“']?(.+?)[\"”']?\s+to\s+\d", q, re.I)
    if not prefix:
        return None
    target = prefix.group(1).strip(" .,-\"“”'")
    target = re.sub(r"^(?:my|the)\s+", "", target, flags=re.I).strip()
    if not target:
        return None

    tz = ZoneInfo("Asia/Kolkata"); now = datetime.now(tz)
    if re.search(r"\btomorrow\b", q, re.I):
        day = (now + timedelta(days=1)).date()
    elif re.search(r"\btoday\b", q, re.I):
        day = now.date()
    else:
        dm = re.search(r"\b(?:on\s+)?(\d{4})-(\d{1,2})-(\d{1,2})\b", q)
        if dm:
            day = datetime(int(dm.group(1)), int(dm.group(2)), int(dm.group(3))).date()
        else:
            # No new date: preserve the existing event date.
            day = None
    return {"target": target, "new_day": day, "new_hour": hour, "new_minute": minute}


def _parse_calendar_cancel_request(text: str):
    """Parse requests to cancel/delete an existing Calendar event."""
    q = (text or "").strip()
    if not re.search(r"\b(cancel|delete|remove)\b", q, re.I):
        return None
    if not re.search(r"\b(event|meeting|appointment|call)\b|\bmy\s+[\"“']?[^\"”']+", q, re.I):
        return None
    m = re.search(r"\b(?:cancel|delete|remove)\s+(?:my\s+|the\s+)?(?:event\s+|meeting\s+|appointment\s+|call\s+)?[\"“']?(.+?)[\"”']?(?:\s+(?:today|tomorrow|on\s+\d{4}-\d{1,2}-\d{1,2}))?$", q, re.I)
    if not m:
        return None
    target = m.group(1).strip(" .,-\"“”'")
    if not target:
        return None
    return {"target": target}


def _calendar_event_for_action(creds, target: str):
    """Resolve an existing event by exact title first, then a unique loose match."""
    target_norm = re.sub(r"[^a-z0-9]+", " ", (target or "").lower()).strip()
    terms = [t for t in re.findall(r"[a-z0-9]+", target_norm) if len(t) > 1]
    results = google_client.search_calendar(creds, user_query="upcoming", keywords=terms[:5], person=None, max_results=50)
    exact = [r for r in results if re.sub(r"[^a-z0-9]+", " ", (r.get("name") or "").lower()).strip() == target_norm]
    if len(exact) == 1:
        return exact[0], []
    if len(exact) > 1:
        return None, exact
    if len(results) == 1:
        return results[0], []
    # Prefer titles containing the requested phrase, but require uniqueness.
    contains = [r for r in results if target_norm and target_norm in re.sub(r"[^a-z0-9]+", " ", (r.get("name") or "").lower())]
    if len(contains) == 1:
        return contains[0], []
    return None, results[:10]

def _parse_send_email_request(text: str):
    """Parse a conservative explicit email-send request.

    Supported forms include:
      send email to person@example.com subject: Hello body: Hi there
      send an email to person@example.com with subject Hello saying Hi there
      email person@example.com subject "Hello" saying "Hi there"

    The recipient must be an explicit email address. Names are deliberately
    not guessed in this phase; a later phase can add contact resolution.
    Returns (recipient, subject, body) or (None, None, None).
    """
    q = (text or "").strip()
    email = r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
    patterns = [
        rf"^send\s+(?:an\s+)?email\s+to\s+({email})\s+subject\s*[:=-]\s*(.+?)\s+body\s*[:=-]\s*(.+)$",
        rf"^send\s+(?:an\s+)?email\s+to\s+({email})\s+with\s+subject\s*[:=-]\s*(.+?)\s+(?:saying|message|body)\s*[:=-]?\s*(.+)$",
        rf"^email\s+({email})\s+subject\s*[:=-]\s*(.+?)\s+(?:saying|body)\s*[:=-]?\s*(.+)$",
        rf"^send\s+(?:an\s+)?email\s+to\s+({email})\s+saying\s+(.+)$",
    ]
    for i, pattern in enumerate(patterns):
        m = re.match(pattern, q, re.IGNORECASE | re.DOTALL)
        if not m:
            continue
        recipient = m.group(1).strip()
        if i == 3:
            return recipient, "Message from EIDIKO Chatbot", m.group(2).strip()
        subject = m.group(2).strip().strip('"')
        body = m.group(3).strip().strip('"')
        if recipient and subject and body:
            return recipient, subject, body
    return None, None, None


def _parse_send_drive_file_request(text: str):
    """Parse one-or-more explicit Drive filenames plus a recipient."""
    q = (text or "").strip()
    email = r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
    if _is_send_email_request(q):
        return None, None, None, None

    # Require explicit file extensions. This prevents phrases such as
    # "the ... and send them" from becoming one giant Drive search query.
    file_pat = r"(?:`([^`]+)`|\"([^\"]+)\"|'([^']+)'|([A-Za-z0-9][A-Za-z0-9 _().-]*\.(?:pdf|docx?|xlsx?|pptx?|zip|csv|txt|html?|png|jpe?g)))"
    m = re.search(rf"^(?:take|attach|send)\s+(.+?)\s+(?:and\s+)?(?:send|email|mail)\s+(?:it|them)?\s*to\s+({email})(.*)$", q, re.IGNORECASE | re.DOTALL)
    if not m:
        m = re.search(rf"^(?:take|attach|send)\s+(.+?)\s+to\s+({email})(.*)$", q, re.IGNORECASE | re.DOTALL)
    if not m:
        return None, None, None, None

    source_text = m.group(1).strip().strip(' .')
    recipient = m.group(2).strip()
    tail = (m.group(3) or '').strip()
    names = []
    # Multiple files are commonly joined with "and" or commas. Parse each
    # segment independently and strip conversational filler such as "the".
    for segment in re.split(r"\s+(?:and|,)\s+", source_text, flags=re.IGNORECASE):
        segment = re.sub(r"^the\s+", "", segment.strip(), flags=re.IGNORECASE).strip(" ,.")
        fm = re.search(file_pat, segment, re.IGNORECASE)
        if fm:
            name = next((g for g in fm.groups() if g), '').strip().strip(' ,')
            if name and name.casefold() not in {n.casefold() for n in names}:
                names.append(name)
    if not names:
        return None, None, None, None
    subject = ''
    body = ''
    sm = re.search(r'(?:subject|with\s+subject)\s*[:=-]\s*(.+?)(?=\s+(?:body|saying|message)\s*[:=-]|$)', tail, re.I | re.S)
    bm = re.search(r'(?:body|saying|message)\s*[:=-]\s*(.+)$', tail, re.I | re.S)
    if sm: subject = sm.group(1).strip().strip('"')
    if bm: body = bm.group(1).strip().strip('"')
    return names, recipient, subject, body

def _is_send_drive_file_request(text: str) -> bool:
    source, recipient, subject, body = _parse_send_drive_file_request(text)
    return bool(source and recipient)


def _drive_attachment_action_result(source, recipient, subject, body, action_id):
    return {
        "action": {
            "id": action_id,
            "type": "send_drive_file_gmail",
            "title": "Send Drive file by email",
            "source": source,
            "recipient": recipient,
            "subject": subject,
            "body_preview": body[:180] + ("..." if len(body) > 180 else ""),
            "confirm_text": f'Send "{source}" as an attachment to "{recipient}"?',
        }
    }


def _is_send_email_request(text: str) -> bool:
    to, subject, body = _parse_send_email_request(text)
    return bool(to and subject and body)


def _email_action_result(recipient, subject, body, action_id):
    preview = re.sub(r"\s+", " ", body).strip()
    if len(preview) > 180:
        preview = preview[:177] + "..."
    return {
        "action": {
            "id": action_id,
            "type": "send_gmail",
            "title": "Send email",
            "recipient": recipient,
            "subject": subject,
            "body_preview": preview,
            "confirm_text": f'Send email to "{recipient}" with subject "{subject}"?'
        }
    }


def _parse_drive_move_request(text: str):
    """Parse common, intentionally conservative Drive move requests.

    Returns (source_phrase, destination_folder) or (None, None). We do not
    let an LLM invent a destination; both values must come from the user's
    words.
    """
    q = (text or "").strip()
    patterns = [
        r"^(?:take|move|put|save)\s+(.+?)\s+(?:and\s+)?(?:store|save|move|put)\s+(?:it\s+)?(?:in|into|to)\s+(?:my\s+)?(.+?)\s+folder\s*$",
        r"^(?:move|put|store)\s+(.+?)\s+(?:to|into|in)\s+(?:my\s+)?(.+?)\s+folder\s*$",
        r"^(?:take)\s+(.+?)\s+(?:and\s+)?(?:store|save|put)\s+(?:it\s+)?(?:in|into)\s+(?:my\s+)?(.+?)\s+folder\s*$",
    ]
    for pattern in patterns:
        m = re.match(pattern, q, re.IGNORECASE)
        if m:
            source = m.group(1).strip(" .")
            folder = m.group(2).strip(" .")
            if source and folder:
                return source, folder
    return None, None


def _is_drive_move_request(text: str) -> bool:
    source, folder = _parse_drive_move_request(text)
    return bool(source and folder)


def _drive_action_result(title, source, destination, action_id):
    return {
        "action": {
            "id": action_id,
            "type": "move_drive_file",
            "title": title,
            "source": source,
            "destination": destination,
            "confirm_text": f"Move \"{source}\" to the \"{destination}\" folder?",
        }
    }


@app.route("/api/action/confirm", methods=["POST"])
def confirm_action():
    data = request.get_json(force=True) or {}
    action_id = (data.get("action_id") or "").strip()
    action = _pending_actions.pop(action_id, None)
    if not action:
        return jsonify({"ok": False, "reply": "That action has expired. Please ask me again."}), 400

    try:
        creds = google_client.get_credentials()
        if creds is None:
            return jsonify({"ok": False, "reply": "Your Google account isn't connected. Please reconnect first."}), 400

        if action["type"] == "multi_action":
            sent_name = None
            created_event = None
            # Execute only the exact steps that were shown in the confirmation.
            for step in action.get("steps", []):
                if step["type"] == "send_drive_files_gmail":
                    google_client.send_gmail_attachments(
                        creds, step["recipient"], step["subject"], step["body"], step["files"]
                    )
                    sent_name = step["files"][0].get("file_name", "file") if step.get("files") else "file"
                elif step["type"] == "create_calendar_event":
                    created_event = google_client.create_calendar_event(
                        creds, step["summary"], step["start_dt"], step["end_dt"],
                        attendees=step.get("attendees", []), description=step.get("description", ""), add_google_meet=True
                    )
            meet_link = created_event.get("hangoutLink", "") if created_event else ""
            reply = "Combined action completed successfully."
            if sent_name:
                reply += f' File "{sent_name}" was emailed.'
            if created_event:
                reply += f' Calendar event "{created_event.get("summary", action.get("summary", "Meeting"))}" was created.'
                if meet_link:
                    reply += f" Google Meet: {meet_link}"
            return jsonify({"ok": True, "reply": reply, "results": ([{
                "title": created_event.get("summary", action.get("summary", "Meeting")), "source": "calendar",
                "meta": "created successfully", "date": created_event.get("start", {}).get("dateTime", ""),
                "link": created_event.get("htmlLink", ""), "start": created_event.get("start", {}).get("dateTime", ""),
                "end": created_event.get("end", {}).get("dateTime", ""),
                "attendees": [a.get("email", "") for a in created_event.get("attendees", [])], "meet_link": meet_link,
            }] if created_event else [])})

        if action["type"] == "create_calendar_event":
            event = google_client.create_calendar_event(
                creds,
                action["summary"],
                action["start_dt"],
                action["end_dt"],
                attendees=action.get("attendees", []),
                description=action.get("description", ""),
                add_google_meet=True,
            )
            meet_link = event.get("hangoutLink", "")
            start_info = event.get("start", {}).get("dateTime", action["start_display"])
            end_info = event.get("end", {}).get("dateTime", action["end_display"])
            result = {
                "title": event.get("summary", action["summary"]),
                "source": "calendar",
                "meta": "created successfully",
                "date": start_info,
                "link": event.get("htmlLink", ""),
                "start": start_info,
                "end": end_info,
                "attendees": [a.get("email","") for a in event.get("attendees", [])],
                "meet_link": meet_link,
            }
            reply = f'Calendar event "{event.get("summary", action["summary"])}" created successfully.'
            if meet_link:
                reply += f" Google Meet: {meet_link}"
            return jsonify({"ok": True, "reply": reply, "results": [result]})

        if action["type"] == "update_calendar_event":
            event = google_client.update_calendar_event(
                creds,
                action["event_id"],
                start_dt=action.get("new_start_dt"),
                end_dt=action.get("new_end_dt"),
                calendar_id=action.get("calendar_id", "primary"),
            )
            start_info = event.get("start", {}).get("dateTime", action.get("new_start_display", ""))
            end_info = event.get("end", {}).get("dateTime", action.get("new_end_display", ""))
            return jsonify({
                "ok": True,
                "reply": f'Calendar event "{event.get("summary", action["summary"])}" updated successfully.',
                "results": [{
                    "title": event.get("summary", action["summary"]), "source": "calendar",
                    "meta": "updated successfully", "date": start_info,
                    "link": event.get("htmlLink", ""), "start": start_info, "end": end_info,
                    "attendees": [a.get("email", "") for a in event.get("attendees", [])],
                    "meet_link": event.get("hangoutLink", ""),
                }],
            })

        if action["type"] == "cancel_calendar_events":
            cancelled = 0
            for item in action.get("events", []):
                google_client.cancel_calendar_event(
                    creds, item["event_id"], calendar_id=item.get("calendar_id", "primary")
                )
                cancelled += 1
            return jsonify({
                "ok": True,
                "reply": f'Successfully cancelled {cancelled} calendar event(s) on {action.get("label", "that day")}.',
                "results": [],
            })

        if action["type"] == "cancel_calendar_event":
            google_client.cancel_calendar_event(creds, action["event_id"], calendar_id=action.get("calendar_id", "primary"))
            return jsonify({
                "ok": True,
                "reply": f'Calendar event "{action["summary"]}" cancelled successfully.',
                "results": [],
            })

        if action["type"] == "move_drive_file":
            moved = google_client.move_drive_file(
                creds, action["file_id"], action["folder_id"]
            )
            return jsonify({
                "ok": True,
                "reply": (
                    f'Done. I moved "{moved.get("name", action["source_name"])}" '
                    f'to the "{action["folder_name"]}" folder.'
                ),
                "results": [{
                    "title": moved.get("name", action["source_name"]),
                    "source": "drive",
                    "meta": "moved successfully",
                    "date": "",
                    "link": moved.get("webViewLink", ""),
                }],
            })

        if action["type"] == "send_drive_files_gmail":
            google_client.send_gmail_attachments(
                creds, action["recipient"], action["subject"], action["body"], action["files"]
            )
            names = [f["file_name"] for f in action["files"]]
            return jsonify({"ok": True, "reply": f'Email sent successfully to "{action["recipient"]}" with {len(names)} attachment(s): ' + ", ".join(f'"{n}"' for n in names) + ".", "results": []})

        if action["type"] == "send_gmail":
            sent = google_client.send_gmail_message(
                creds, action["recipient"], action["subject"], action["body"]
            )
            return jsonify({
                "ok": True,
                "reply": f'Email sent successfully to "{action["recipient"]}" with subject "{action["subject"]}".',
                "results": [],
            })

        return jsonify({"ok": False, "reply": "Unknown action."}), 400
    except Exception as e:
        return jsonify({
            "ok": False,
            "reply": f"I couldn't complete that action: {e}",
        }), 500


@app.route("/api/action/cancel", methods=["POST"])
def cancel_action():
    data = request.get_json(force=True) or {}
    action_id = (data.get("action_id") or "").strip()
    _pending_actions.pop(action_id, None)
    return jsonify({"ok": True, "reply": "Okay, I didn't make any changes."})


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True) or {}
    user_query = (data.get("message") or "").strip()

    if not user_query:
        return jsonify({"reply": "Ask me something like \"find my PAN card\" or \"find my Aadhaar\".", "results": []})

    # A new request must not inherit an old file, recipient, email, or pending
    # action unless the user clearly refers to prior context.
    _reset_request_state(preserve_context=_is_context_followup_request(user_query))

    # Hard refusal for password/secret-style requests — no search is run.
    if is_blocked_query(user_query):
        return jsonify(
            {
                "reply": (
                    "I won't search for or return passwords, PINs, OTPs, or similar "
                    "secrets — that's exactly the kind of data an account-takeover tool "
                    "goes after, so it's out of scope here by design. If you have "
                    "passwords sitting in old emails, please delete those emails and "
                    "move to a password manager instead."
                ),
                "results": [],
            }
        )

    creds = google_client.get_credentials()
    if creds is None:
        return jsonify(
            {
                "reply": "Your Google account isn't connected yet. Click \"Connect Google Account\" above first.",
                "results": [],
            }
        )

    # --- Phase 6B: combined Drive + Gmail + Calendar ------------------------
    combined_req = _parse_phase6b_combined_file_meeting(user_query)
    if combined_req:
        source_phrase, recipient_person = combined_req
        candidates = [f for f in google_client.resolve_drive_file(creds, source_phrase)
                      if f.get("mimeType") != "application/vnd.google-apps.folder"]
        if not candidates:
            return jsonify({"reply": f'I couldn\'t find a Drive file matching "{source_phrase}".', "results": []})
        if len(candidates) > 1:
            results = [{"title": f.get("name", ""), "source": "drive", "meta": f.get("mimeType", ""),
                        "date": f.get("modifiedTime", ""), "link": f.get("webViewLink", "")} for f in candidates[:8]]
            return jsonify({"reply": f'I found multiple Drive files matching "{source_phrase}". Please specify the exact file name before I prepare the combined action.', "results": results})
        recipient, err = _phase6b_resolve_person(creds, recipient_person)
        if err:
            return jsonify({"reply": err, "results": []})
        # Reuse tomorrow/free parsing from the general request.
        cal_req = _parse_phase6b_gmail_calendar_request(user_query + f" with {recipient_person}")
        tz = ZoneInfo("Asia/Kolkata"); now = datetime.now(tz)
        day = (now + timedelta(days=1)).date() if re.search(r"\btomorrow\b", user_query, re.I) else now.date()
        explicit_time = cal_req.get("explicit_time") if cal_req else None
        use_free = not explicit_time
        duration = cal_req.get("duration_minutes", 30) if cal_req else 30
        start_dt, end_dt = _phase6b_calendar_target(day, explicit_time, duration, creds, use_free=use_free)
        if not start_dt:
            return jsonify({"reply": f'I found the file and recipient, but I could not find a free calendar slot tomorrow within 10 AM–7 PM IST, excluding 1–2 PM and 5–5:30 PM.', "results": []})
        f = candidates[0]; name = f.get("name", source_phrase)
        summary = f"Meeting with {recipient_person}"
        action_id = uuid.uuid4().hex
        _pending_actions[action_id] = {
            "type": "multi_action",
            "steps": [
                {"type": "send_drive_files_gmail", "files": [{"file_id": f["id"], "file_name": name}],
                 "recipient": recipient, "subject": name, "body": f"Please find the attached file: {name}"},
                {"type": "create_calendar_event", "summary": summary, "start_dt": start_dt, "end_dt": end_dt,
                 "start_display": start_dt.strftime("%d %b %Y, %I:%M %p"), "end_display": end_dt.strftime("%I:%M %p"),
                 "attendees": [recipient], "description": f"Follow-up meeting with {recipient_person}."},
            ],
        }
        return jsonify({
            "reply": f'I found "{name}", verified {recipient_person} as {recipient}, and found a suitable meeting slot. I will not send or create anything until you confirm.',
            "results": [],
            "action": {"id": action_id, "type": "multi_action", "title": "Send file + schedule meeting",
                       "file": name, "recipient": recipient, "summary": summary,
                       "start": start_dt.strftime("%d %b %Y, %I:%M %p"),
                       "end": end_dt.strftime("%I:%M %p"), "attendees": [recipient],
                       "confirm_text": f'Send "{name}" to "{recipient}" and create "{summary}" on {start_dt.strftime("%d %b %Y, %I:%M %p")}–{end_dt.strftime("%I:%M %p")} with a Google Meet link?'}
        })


    # --- Phase 6B: conversational follow-up -------------------------------
    followup = _parse_phase6b_followup(user_query)
    if followup and not _parse_find_and_send_drive_request(user_query):
        recipient, err = _phase6b_resolve_person(creds, followup["person"])
        if err:
            return jsonify({"reply": err, "results": []})
        f = followup["file"]
        name = f.get("name", "file")
        if not followup["schedule"]:
            action_id = uuid.uuid4().hex
            _pending_actions[action_id] = {"type": "send_drive_files_gmail", "files": [{"file_id": f["id"], "file_name": name}],
                "recipient": recipient, "subject": name, "body": f"Please find the attached file: {name}"}
            return jsonify({"reply": f'I remembered the file "{name}" and verified "{followup["person"]}" as {recipient}. I will not send anything until you confirm.',
                            "results": [], "action": {"id": action_id, "type": "send_drive_files_gmail", "title": "Send Drive file by email",
                            "files": [name], "recipient": recipient, "subject": name, "body_preview": f"Please find the attached file: {name}",
                            "confirm_text": f'Send "{name}" to "{recipient}"?'}})

        cal_req = _parse_phase6b_gmail_calendar_request(user_query)
        day = (datetime.now(ZoneInfo("Asia/Kolkata")) + timedelta(days=1)).date()
        explicit_time = cal_req.get("explicit_time") if cal_req else None
        duration = cal_req.get("duration_minutes", 30) if cal_req else 30
        start_dt, end_dt = _phase6b_calendar_target(day, explicit_time, duration, creds, use_free=not explicit_time)
        if not start_dt:
            return jsonify({"reply": "I found the file and person, but I could not find a free meeting slot tomorrow within 10 AM–7 PM IST, excluding 1–2 PM and 5–5:30 PM.", "results": []})
        summary = f"Meeting with {followup['person']}"
        action_id = uuid.uuid4().hex
        _pending_actions[action_id] = {"type": "multi_action", "steps": [
            {"type": "send_drive_files_gmail", "files": [{"file_id": f["id"], "file_name": name}], "recipient": recipient,
             "subject": name, "body": f"Please find the attached file: {name}"},
            {"type": "create_calendar_event", "summary": summary, "start_dt": start_dt, "end_dt": end_dt,
             "start_display": start_dt.strftime("%d %b %Y, %I:%M %p"), "end_display": end_dt.strftime("%I:%M %p"), "attendees": [recipient], "description": "Follow-up meeting."},
        ]}
        return jsonify({"reply": f'I remembered "{name}" and {followup["person"]}, and found a suitable meeting slot. I will not send or create anything until you confirm.',
                        "results": [], "action": {"id": action_id, "type": "multi_action", "title": "Send file + schedule meeting", "file": name,
                        "recipient": recipient, "summary": summary, "start": start_dt.strftime("%d %b %Y, %I:%M %p"), "end": end_dt.strftime("%I:%M %p"),
                        "attendees": [recipient], "confirm_text": f'Send "{name}" to "{recipient}" and create "{summary}" on {start_dt.strftime("%d %b %Y, %I:%M %p")}–{end_dt.strftime("%I:%M %p")} with a Google Meet link?'}})

    # --- Phase 6B: Gmail -> Calendar ---------------------------------------
    gmail_calendar_req = _parse_phase6b_gmail_calendar_request(user_query)
    if gmail_calendar_req:
        person = gmail_calendar_req["person"]
        recipient, err = _phase6b_resolve_person(creds, person)
        if err:
            return jsonify({"reply": err, "results": []})
        latest = _phase6b_find_latest_email(creds, person, gmail_calendar_req.get("topic"))
        if not latest:
            topic_text = f' about "{gmail_calendar_req["topic"]}"' if gmail_calendar_req.get("topic") else ""
            return jsonify({"reply": f'I could not find a matching latest email from "{person}"{topic_text}.', "results": []})
        _conversation_context["last_email"] = {"id": latest.get("id"), "subject": latest.get("subject", ""), "person": person}
        day = gmail_calendar_req.get("day")
        if day is None:
            day = (datetime.now(ZoneInfo("Asia/Kolkata")) + timedelta(days=1)).date()
        start_dt, end_dt = _phase6b_calendar_target(day, gmail_calendar_req.get("explicit_time"), gmail_calendar_req["duration_minutes"], creds, use_free=gmail_calendar_req["free"] or not gmail_calendar_req.get("explicit_time"))
        if not start_dt:
            return jsonify({"reply": "I found the email, but I could not find a free meeting slot within 10 AM–7 PM IST, excluding 1–2 PM and 5–5:30 PM.", "results": []})
        summary = f"Meeting with {person}"
        action_id = uuid.uuid4().hex
        _pending_actions[action_id] = {"type": "create_calendar_event", "summary": summary,
            "start_dt": start_dt, "end_dt": end_dt, "start_display": start_dt.isoformat(), "end_display": end_dt.isoformat(),
            "attendees": [recipient], "description": f"Follow-up from latest email: {latest.get('subject', '(no subject)')}"}
        safe_latest = {"source": "gmail", "title": redact(latest.get("subject", "")), "meta": redact(latest.get("from", "")), "date": latest.get("date", ""), "link": latest.get("link", "")}
        return jsonify({"reply": f'I found the latest matching email from "{person}" and prepared a meeting based on it. I will not create the meeting until you confirm.',
                        "results": [safe_latest],
                        "action": {"id": action_id, "type": "create_calendar_event", "title": "Create Calendar event", "summary": summary,
                                   "start": start_dt.strftime("%d %b %Y, %I:%M %p"), "end": end_dt.strftime("%I:%M %p"),
                                   "attendees": [recipient], "confirm_text": f'Create "{summary}" on {start_dt.strftime("%d %b %Y, %I:%M %p")}–{end_dt.strftime("%I:%M %p")} with a Google Meet link?'}})

    # --- Phase 5: cancel all events for a day -------------------------------
    cancel_all = _parse_calendar_cancel_all_request(user_query)
    if cancel_all:
        tz = ZoneInfo("Asia/Kolkata")
        day = cancel_all["start_day"]
        events = _calendar_week_events(creds, day, 1)
        if not events:
            return jsonify({"reply": f'I found no calendar events to cancel on {cancel_all["label"]}.', "results": []})
        action_id = uuid.uuid4().hex
        event_items = [{"event_id": e["id"], "calendar_id": "primary", "summary": e.get("summary") or "(untitled event)",
                        "start": st.isoformat(), "end": en.isoformat()} for e, st, en in events]
        _pending_actions[action_id] = {"type": "cancel_calendar_events", "events": event_items,
                                       "label": cancel_all["label"]}
        return jsonify({
            "reply": f'I found {len(event_items)} calendar event(s) on {cancel_all["label"]}. I will not cancel them until you confirm.',
            "results": [],
            "action": {"id": action_id, "type": "cancel_calendar_events",
                       "count": len(event_items),
                       "events": [x["summary"] for x in event_items],
                       "confirm_text": f'Cancel all {len(event_items)} calendar event(s) on {cancel_all["label"]}?'}
        })

    # --- Phase 5: schedule with a free slot next week -----------------------
    free_req = _parse_calendar_free_slot_request(user_query)
    if free_req:
        attendees = []
        for person in free_req["people"]:
            resolved = google_client.resolve_person_emails(creds, person)
            if not resolved:
                return jsonify({"reply": f'I could not find a Gmail contact matching "{person}". Please provide their complete email address.', "results": []})
            if len(resolved) > 1:
                return jsonify({"reply": f'I found multiple email addresses for "{person}". Please provide the complete email address to avoid inviting the wrong person.', "results": []})
            attendees.extend(resolved)
        start_dt, end_dt = _find_next_free_slot(creds, free_req["duration_minutes"])
        if not start_dt:
            return jsonify({"reply": "I couldn't find a free weekday slot next week during the configured 10 AM–7 PM office hours, excluding 1–2 PM and 5–5:30 PM.", "results": []})
        summary = "Meeting with " + " and ".join(free_req["people"]) if free_req["people"] else "Scheduled meeting"
        action_id = uuid.uuid4().hex
        _pending_actions[action_id] = {"type":"create_calendar_event","summary":summary,
            "start_dt":start_dt,"end_dt":end_dt,"start_display":start_dt.isoformat(),"end_display":end_dt.isoformat(),
            "attendees":list(dict.fromkeys(a.lower() for a in attendees)),"description":""}
        return jsonify({"reply":f'I found a free slot next week and prepared the Calendar event "{summary}". I will not create it until you confirm.',
                        "results":[],
                        "action": {"id":action_id,"type":"create_calendar_event","summary":summary,
                                   "start":start_dt.strftime("%d %b %Y, %I:%M %p"),
                                   "end":end_dt.strftime("%d %b %Y, %I:%M %p"),
                                   "attendees":list(dict.fromkeys(a.lower() for a in attendees)),
                                   "confirm_text":f'Create "{summary}" on {start_dt.strftime("%d %b %Y, %I:%M %p")}–{end_dt.strftime("%I:%M %p")} with a Google Meet link?'}})

    # --- Phase 4D: modify an existing Calendar event ------------------------
    calendar_modify = _parse_calendar_modify_request(user_query)
    if calendar_modify:
        event, candidates = _calendar_event_for_action(creds, calendar_modify["target"])
        if not event:
            if candidates:
                names = ", ".join(f'"{c.get("name", "(untitled)")}"' for c in candidates[:5])
                return jsonify({"reply": f'I found multiple calendar events matching "{calendar_modify["target"]}": {names}. Please specify the exact event name.', "results": []})
            return jsonify({"reply": f'I couldn\'t find a calendar event matching "{calendar_modify["target"]}".', "results": []})
        old_start = event.get("start", "")
        old_end = event.get("end", "")
        old_start_dt = datetime.fromisoformat(old_start.replace("Z", "+00:00")) if old_start and "T" in old_start else None
        old_end_dt = datetime.fromisoformat(old_end.replace("Z", "+00:00")) if old_end and "T" in old_end else None
        if old_start_dt is None or old_end_dt is None:
            return jsonify({"reply": "I can only reschedule timed calendar events in this phase.", "results": []})
        tz = ZoneInfo("Asia/Kolkata")
        old_start_dt = old_start_dt.astimezone(tz); old_end_dt = old_end_dt.astimezone(tz)
        new_day = calendar_modify["new_day"] or old_start_dt.date()
        new_start = datetime(new_day.year, new_day.month, new_day.day, calendar_modify["new_hour"], calendar_modify["new_minute"], tzinfo=tz)
        duration = old_end_dt - old_start_dt
        new_end = new_start + duration
        action_id = uuid.uuid4().hex
        _pending_actions[action_id] = {"type":"update_calendar_event", "event_id":event["id"], "calendar_id":event.get("calendar_id","primary"), "summary":event.get("name","(untitled event)"), "new_start_dt":new_start, "new_end_dt":new_end, "new_start_display":new_start.isoformat(), "new_end_display":new_end.isoformat()}
        attendees = event.get("attendees", [])
        return jsonify({"reply":f'I found the calendar event "{event.get("name","(untitled event)")}". I will not change it until you confirm.', "results":[], "action":{"id":action_id,"type":"update_calendar_event","title":"Update Calendar event","summary":event.get("name","(untitled event)"),"old_start":old_start,"old_end":old_end,"new_start":new_start.strftime("%d %b %Y, %I:%M %p"),"new_end":new_end.strftime("%I:%M %p"),"attendees":attendees,"confirm_text":f'Change "{event.get("name","(untitled event)")}" to {new_start.strftime("%d %b %Y, %I:%M %p")}–{new_end.strftime("%I:%M %p")}?'}})

    # --- Phase 4D: cancel an existing Calendar event ------------------------
    calendar_cancel = _parse_calendar_cancel_request(user_query)
    if calendar_cancel:
        event, candidates = _calendar_event_for_action(creds, calendar_cancel["target"])
        if not event:
            if candidates:
                names = ", ".join(f'"{c.get("name", "(untitled)")}"' for c in candidates[:5])
                return jsonify({"reply": f'I found multiple calendar events matching "{calendar_cancel["target"]}": {names}. Please specify the exact event name.', "results": []})
            return jsonify({"reply": f'I couldn\'t find a calendar event matching "{calendar_cancel["target"]}".', "results": []})
        action_id = uuid.uuid4().hex
        _pending_actions[action_id] = {"type":"cancel_calendar_event", "event_id":event["id"], "calendar_id":event.get("calendar_id","primary"), "summary":event.get("name","(untitled event)")}
        return jsonify({"reply":f'I found the calendar event "{event.get("name","(untitled event)")}". I will not cancel it until you confirm.', "results":[], "action":{"id":action_id,"type":"cancel_calendar_event","summary":event.get("name","(untitled event)"),"confirm_text":f'Cancel "{event.get("name","(untitled event)")}"?'}})

    # --- Phase 4A: create Calendar event + Google Meet ----------------------
    calendar_create = _parse_calendar_create_request(user_query)
    if calendar_create:
        # If the user named a person ("with Abhay"), resolve the attendee
        # email before presenting confirmation. Never invent the address.
        people = calendar_create.pop("attendee_people", None) or []
        # Backward-compatible fallback for the single-attendee parser field.
        if not people:
            person = calendar_create.pop("attendee_person", None)
            if person:
                people = [person]
        else:
            calendar_create.pop("attendee_person", None)

        if people and not calendar_create["attendees"]:
            resolved_all = []
            for person in people:
                resolved_emails = google_client.resolve_person_emails(creds, person)
                # Safety: never invite an automated/no-reply mailbox as a person.
                blocked = ("no-reply", "noreply", "donotreply", "mailer-daemon",
                           "notifications", "alerts", "newsletter")
                resolved_emails = [
                    e for e in resolved_emails
                    if not any(x in e.lower().split("@", 1)[0] for x in blocked)
                ]
                if not resolved_emails:
                    return jsonify({
                        "reply": (
                            f'I could not find a Gmail contact matching "{person}". '
                            "Please provide their complete email address."
                        ),
                        "results": [],
                    })
                if len(resolved_emails) > 1:
                    return jsonify({
                        "reply": (
                            f'I found multiple email addresses for "{person}". '
                            "Please provide the complete email address to avoid inviting the wrong person."
                        ),
                        "results": [
                            {
                                "title": person,
                                "source": "gmail",
                                "meta": "possible attendee",
                                "date": "",
                                "link": "",
                            }
                        ],
                    })
                resolved_all.extend(resolved_emails)

            calendar_create["attendees"] = list(dict.fromkeys(resolved_all))

        action_id = uuid.uuid4().hex
        _pending_actions[action_id] = {
            "type": "create_calendar_event",
            "summary": calendar_create["summary"],
            "start_dt": calendar_create["start"],
            "end_dt": calendar_create["end"],
            "start_display": calendar_create["start"].isoformat(),
            "end_display": calendar_create["end"].isoformat(),
            "attendees": calendar_create["attendees"],
            "description": "",
        }
        return jsonify({
            "reply": (
                f'I prepared the Calendar event "{calendar_create["summary"]}". '
                "I will not create it until you confirm."
            ),
            "results": [],
            "action": _calendar_create_action_result(calendar_create, action_id)["action"],
        })

    # --- Phase 3B: explicit Gmail send action -------------------------------
    recipient, email_subject, email_body = _parse_send_email_request(user_query)
    if recipient and email_subject and email_body:
        action_id = uuid.uuid4().hex
        _pending_actions[action_id] = {
            "type": "send_gmail",
            "recipient": recipient,
            "subject": email_subject,
            "body": email_body,
        }
        payload = _email_action_result(recipient, email_subject, email_body, action_id)
        return jsonify({
            "reply": (
                f'I prepared an email to "{recipient}". '
                "I will not send it until you confirm."
            ),
            "results": [],
            **payload,
        })

    # --- Phase 3D: send one or more Drive files as Gmail attachments -----
    file_sources, file_recipient, file_subject, file_body = _parse_send_drive_file_request(user_query)
    if file_sources and file_recipient:
        selected = []
        for file_source in file_sources:
            candidates = [f for f in google_client.resolve_drive_file(creds, file_source)
                          if f.get("mimeType") != "application/vnd.google-apps.folder"]
            if not candidates:
                return jsonify({"reply": f'I couldn\'t find a Drive file matching "{file_source}".', "results": []})
            if len(candidates) > 1:
                results = [{"title": f.get("name", ""), "source": "drive", "meta": f.get("mimeType", ""), "date": f.get("modifiedTime", ""), "link": f.get("webViewLink", "")} for f in candidates[:8]]
                return jsonify({"reply": f'I found multiple Drive files matching "{file_source}". Please specify the complete file name before I send anything.', "results": results})
            selected.append(candidates[0])

        names = [f.get("name", "") for f in selected]
        subject = file_subject or (names[0] if len(names) == 1 else f"{len(names)} attachments from EIDIKO Chatbot")
        body = file_body or "Please find the attached file(s):\n" + "\n".join(f"- {n}" for n in names)
        action_id = uuid.uuid4().hex
        _pending_actions[action_id] = {
            "type": "send_drive_files_gmail",
            "files": [{"file_id": f["id"], "file_name": f.get("name", "")} for f in selected],
            "recipient": file_recipient, "subject": subject, "body": body,
        }
        return jsonify({"reply": f'I found {len(names)} Drive file(s) and recipient "{file_recipient}". I will not send anything until you confirm.', "results": [], "action": {"id": action_id, "type": "send_drive_files_gmail", "title": "Send Drive files by email", "files": names, "recipient": file_recipient, "subject": subject, "body_preview": body[:180], "confirm_text": f'Send {len(names)} attachment(s) to "{file_recipient}"?'}})

    # --- Phase 3A: explicit Drive move action -------------------------------
    # We detect this deterministically and require confirmation before the
    # only write operation currently supported by the chatbot.
    move_source, move_folder = _parse_drive_move_request(user_query)
    if move_source and move_folder:
        # Resolve source using the existing safe metadata search path.
        source_candidates = google_client.resolve_drive_file(creds, move_source)
        source_candidates = [
            f for f in source_candidates
            if f.get("mimeType") != "application/vnd.google-apps.folder"
        ]
        folder_candidates = google_client.resolve_drive_folder(creds, move_folder)

        if not source_candidates:
            return jsonify({
                "reply": f'I couldn\'t find a Drive file matching "{move_source}".',
                "results": [],
            })
        if len(source_candidates) > 1:
            results = [
                {
                    "title": f.get("name", ""),
                    "source": "drive",
                    "meta": f.get("mimeType", ""),
                    "date": f.get("modifiedTime", ""),
                    "link": f.get("webViewLink", ""),
                }
                for f in source_candidates[:8]
            ]
            return jsonify({
                "reply": (
                    f'I found multiple Drive files matching "{move_source}". '
                    "Please specify the exact file name before I move anything."
                ),
                "results": results,
            })
        if not folder_candidates:
            return jsonify({
                "reply": f'I couldn\'t find a Drive folder named "{move_folder}".',
                "results": [],
            })
        if len(folder_candidates) > 1:
            results = [
                {
                    "title": f.get("name", ""),
                    "source": "drive",
                    "meta": "folder",
                    "date": f.get("modifiedTime", ""),
                    "link": f.get("webViewLink", ""),
                }
                for f in folder_candidates[:8]
            ]
            return jsonify({
                "reply": (
                    f'I found multiple Drive folders named "{move_folder}". '
                    "Please use a more specific folder name before I move anything."
                ),
                "results": results,
            })

        source = source_candidates[0]
        folder = folder_candidates[0]
        action_id = uuid.uuid4().hex
        _pending_actions[action_id] = {
            "type": "move_drive_file",
            "file_id": source["id"],
            "folder_id": folder["id"],
            "source_name": source.get("name", move_source),
            "folder_name": folder.get("name", move_folder),
        }
        payload = _drive_action_result(
            "Drive move",
            source.get("name", move_source),
            folder.get("name", move_folder),
            action_id,
        )
        return jsonify({
            "reply": (
                f'I found "{source.get("name", move_source)}" and the '
                f'"{folder.get("name", move_folder)}" folder. '
                "I will not move anything until you confirm."
            ),
            "results": [],
            **payload,
        })

    
    # --- Phase 6A: deterministic cross-service "find + send" --------------
    # Examples:
    #   Find the CP4I presentation and send it to Abhay.
    #   Find the CP4I-Auto-Escalation-Technical-Documentation.pdf and send it to Jaina.
    #
    # We resolve the Drive file first, then resolve the recipient from
    # verified Gmail sender headers. Nothing is sent until confirmation.
    cross_send = _parse_find_and_send_drive_request(user_query)
    if cross_send:
        source_phrase, recipient_person = cross_send
        candidates = [
            f for f in google_client.resolve_drive_file(creds, source_phrase)
            if f.get("mimeType") != "application/vnd.google-apps.folder"
        ]
        if not candidates:
            return jsonify({"reply": f'I couldn\'t find a Drive file matching "{source_phrase}".', "results": []})
        if len(candidates) > 1:
            results = [
                {"title": f.get("name",""), "source":"drive",
                 "meta": f.get("mimeType",""), "date": f.get("modifiedTime",""),
                 "link": f.get("webViewLink","")}
                for f in candidates[:8]
            ]
            return jsonify({
                "reply": f'I found multiple Drive files matching "{source_phrase}". Please specify the exact file name before I send anything.',
                "results": results,
            })

        resolved = google_client.resolve_person_emails(creds, recipient_person)
        if not resolved:
            return jsonify({"reply": f'I could not find a Gmail contact matching "{recipient_person}". Please provide their complete email address.', "results":[]})
        if len(resolved) > 1:
            return jsonify({"reply": f'I found multiple email addresses for "{recipient_person}". Please provide the complete email address to avoid sending to the wrong person.', "results":[]})

        f = candidates[0]
        recipient = resolved[0]
        name = f.get("name","")
        _conversation_context["last_file"] = {"id": f.get("id"), "name": name}
        _conversation_context["last_person"] = recipient_person
        action_id = uuid.uuid4().hex
        _pending_actions[action_id] = {
            "type": "send_drive_files_gmail",
            "files": [{"file_id": f["id"], "file_name": name}],
            "recipient": recipient,
            "subject": name,
            "body": f"Please find the attached file: {name}",
        }
        return jsonify({
            "reply": f'I found the exact Drive file "{name}" and verified "{recipient_person}" as {recipient}. I will not send anything until you confirm.',
            "results": [],
            "action": {
                "id": action_id,
                "type": "send_drive_files_gmail",
                "title": "Send Drive file by email",
                "files": [name],
                "recipient": recipient,
                "subject": name,
                "body_preview": f"Please find the attached file: {name}",
                "confirm_text": f'Send "{name}" to "{recipient}"?',
            },
        })

    # --- Phase 6A: latest email from a person + summary --------------------
    latest_mail = _parse_latest_email_request(user_query)
    if latest_mail:
        person = latest_mail
        matches = google_client.search_gmail(creds, keywords=None, person=person, max_results=15)
        matches = [m for m in matches if m.get("sender_match")]
        if not matches:
            return jsonify({"reply": f'I couldn\'t find any emails from "{person}".', "results":[]})
        # Gmail returns newest messages first. Keep exactly one so "latest"
        # can never accidentally summarize an older message.
        latest = matches[0]
        safe_results = [{
            "source": "gmail",
            "id": latest.get("id",""),
            "subject": redact(latest.get("subject","")),
            "from": redact(latest.get("from","")),
            "date": latest.get("date",""),
            "snippet": redact(latest.get("snippet","")),
            "link": latest.get("link",""),
            "attachments": [{"filename": redact(a.get("filename","")), "attachment_id": a.get("attachment_id",""), "mime_type": a.get("mime_type",""), "size": a.get("size",0)} for a in latest.get("attachments",[])],
            "sender_match": True,
        }]
        summary = claude_client.summarize_results(
            user_query, safe_results,
            intent_context=f'Detected intent: latest email from verified sender "{person}". Summarize only this one email.'
        )
        idxs = summary.get("relevant_indices", [0])
        display = [latest] if 0 in idxs or not idxs else []
        # Never expose raw sensitive text; the normal result renderer only
        # uses subject/date/link/attachment metadata.
        # Convert Gmail attachment metadata into the same renderer shape used
        # by normal search results. Without download_url the UI falls back to
        # /undefined, even though the attachment itself was found correctly.
        display = []
        latest_for_display = dict(latest)
        latest_for_display["attachments"] = [
            {
                **a,
                "download_url": (
                    f"/api/download?message_id={latest.get('id','')}"
                    f"&attachment_id={a.get('attachment_id','')}"
                    f"&filename={quote(a.get('filename',''), safe='')}"
                ),
            }
            for a in latest.get("attachments", [])
        ]
        display.append(latest_for_display)
        return jsonify({"reply": summary.get("reply") or f'I found the latest email from "{person}".',
                        "results": display})

    # --- Phase 6A: "document/file sent by person last week" ----------------
    sent_doc = _parse_person_document_last_week_request(user_query)
    if sent_doc:
        person = sent_doc
        matches = google_client.search_gmail(creds, keywords=None, person=person, max_results=50)
        matches = [m for m in matches if m.get("sender_match") and m.get("attachments")]
        tz = ZoneInfo("Asia/Kolkata")
        now = datetime.now(tz)
        start = datetime.combine((now - timedelta(days=now.weekday()+7)).date(), datetime.min.time(), tzinfo=tz)
        end = start + timedelta(days=7)
        filtered = []
        for m in matches:
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(m.get("date","")).astimezone(tz)
            except Exception:
                continue
            if start <= dt < end:
                filtered.append(m)
        results = []
        for m in filtered:
            results.append({
                "source":"gmail","id":m.get("id",""),"subject":redact(m.get("subject","")),
                "from":redact(m.get("from","")),"date":m.get("date",""),
                "snippet":redact(m.get("snippet","")),"link":m.get("link",""),
                "attachments":[
                    {
                        **a,
                        "filename":redact(a.get("filename","")),
                        "download_url": (
                            f"/api/download?message_id={m.get('id','')}"
                            f"&attachment_id={a.get('attachment_id','')}"
                            f"&filename={quote(a.get('filename',''), safe='')}"
                        ),
                    }
                    for a in m.get("attachments", [])
                ],
                "sender_match":True,
            })
        if not results:
            return jsonify({"reply": f'I couldn\'t find an email from "{person}" with a document attachment sent last week.', "results":[]})
        summary = claude_client.summarize_results(
            user_query, results,
            intent_context=f'Detected intent: documents attached to emails from verified sender "{person}" during last calendar week. Keep only those emails.'
        )
        keep = summary.get("relevant_indices", list(range(len(results))))
        return jsonify({"reply": summary.get("reply") or f'I found {len(results)} email(s) from "{person}" with document attachment(s) last week.',
                        "results":[results[i] for i in keep if 0 <= i < len(results)]})

# --- Query understanding -------------------------------------------------
    # Person-name and gmail-vs-drive routing are decided deterministically
    # first (query_intent.py, pure regex over the user's own text — no
    # network call, nothing an LLM could get wrong). Claude's own guess
    # (extract_query_intent) fills in keywords and is used as a fallback
    # for person/target ONLY when the regexes found nothing — see
    # docstrings in query_intent.py and claude_client.py for why.
    try:
        claude_intent = claude_client.extract_query_intent(user_query)
    except RuntimeError as e:
        return jsonify({"reply": str(e), "results": []}), 400

    person = query_intent.extract_person_candidate(user_query) or claude_intent.get("person")
    keywords = claude_intent.get("keywords") or []

    # When the user is asking only whether a person sent/emailed them,
    # generic words such as "mail" or "email" must NOT be added to a
    # `from:` Gmail query. Doing so can turn a reliable sender search into
    # an accidental AND condition and hide genuine messages. Keep only
    # distinctive topic terms when a person + topic was actually requested.
    if person:
        generic_mail_terms = {
            "mail", "mails", "email", "emails", "message", "messages",
            "inbox", "sent", "send", "sender", "from", "me", "my",
        }
        keywords = [
            k.strip() for k in keywords
            if isinstance(k, str) and k.strip() and k.strip().lower() not in generic_mail_terms
        ]
    else:
        keywords = keywords or [user_query]

    deterministic_target = query_intent.classify_target(user_query)
    # When the user's wording clearly names a source, trust the deterministic
    # router. Claude is only used to disambiguate queries that do not contain
    # a clear Gmail/Drive/Calendar hint.
    target = (
        deterministic_target
        if deterministic_target != "both"
        else (claude_intent.get("target") or "both")
    )

    # Calendar time words are handled by search_calendar's date window,
    # not as text-matching terms. Likewise, "meeting/event/calendar"
    # are routing words rather than useful event-content keywords.
    if target == "calendar":
        calendar_noise = {
            "today", "tomorrow", "yesterday", "week", "this", "next",
            "calendar", "meeting", "meetings", "event", "events",
            "appointment", "appointments", "schedule", "scheduled",
            "agenda", "call", "calls", "upcoming", "future", "coming", "up",
        "any", "anything", "do", "does", "did", "i", "me", "my", "have",
        "has", "on", "for", "with", "at", "the", "a", "an", "what", "when",
        "show", "find",
        }
        keywords = [
            k.strip() for k in keywords
            if isinstance(k, str)
            and k.strip()
            and k.strip().lower() not in calendar_noise
        ]
    if target not in ("gmail", "drive", "calendar", "both"):
        target = query_intent.classify_target(user_query)

    run_gmail = target in ("gmail", "both") or bool(person and target != "calendar")
    run_drive = target in ("drive", "both")
    run_calendar = target in ("calendar", "both")

    gmail_results = google_client.search_gmail(creds, keywords=keywords, person=person) if run_gmail else []
    drive_results = google_client.search_drive(creds, keywords) if run_drive else []
    calendar_results = (
        google_client.search_calendar(creds, user_query=user_query, keywords=keywords, person=person)
        if run_calendar else []
    )

    # Safety net: only if the routed searches found nothing at all do we
    # check a skipped source. Calendar is included here so an ambiguous
    # query can still discover an event without making every normal
    # document/email query hit all three APIs.
    if not gmail_results and not drive_results and not calendar_results:
        if not run_gmail:
            gmail_results = google_client.search_gmail(creds, keywords=keywords, person=person)
        if not run_drive:
            drive_results = google_client.search_drive(creds, keywords)
        if not run_calendar:
            calendar_results = google_client.search_calendar(
                creds, user_query=user_query, keywords=keywords, person=person
            )

    # Redact BEFORE anything leaves this function — both for what's shown
    # to the user and what's sent to the Claude API for summarization.
    for r in gmail_results:
        r["subject"] = redact(r["subject"])
        r["snippet"] = redact(r["snippet"])
        for a in r.get("attachments", []):
            a["filename"] = redact(a["filename"])
    for r in drive_results:
        r["name"] = redact(r["name"])
    for r in calendar_results:
        r["name"] = redact(r["name"])
        r["location"] = redact(r.get("location", ""))
        r["description"] = redact(r.get("description", ""))
        r["from"] = redact(r.get("from", ""))
        r["organizer_email"] = redact(r.get("organizer_email", ""))
        r["attendees"] = [redact(a) for a in r.get("attendees", [])]

    combined = gmail_results + drive_results + calendar_results

    # Keep only non-sensitive references for natural follow-up turns.
    if drive_results:
        first_drive = drive_results[0]
        _conversation_context["last_file"] = {"id": first_drive.get("id"), "name": first_drive.get("name", "")}
    if person:
        _conversation_context["last_person"] = person

    if not combined:
        if target == "calendar":
            return jsonify(
                {
                    "reply": (
                        "You don't have any matching calendar events for that time range."
                    ),
                    "results": [],
                }
            )
        if target == "gmail":
            return jsonify({"reply": "I couldn't find any matching emails in Gmail.", "results": []})
        if target == "drive":
            return jsonify({"reply": "I couldn't find any matching files in Drive.", "results": []})
        return jsonify({"reply": "I couldn't find anything matching that in your Gmail or Drive.", "results": []})

    # Results Python itself already verified as a genuine sender match
    # (see google_client._sender_matches) are never dropped, regardless
    # of what Claude decides below — this is the actual fix for
    # "did Jeevan send me any mail" silently saying no when a Jeevan
    # email exists: it no longer depends on Claude recognizing the name.
    forced_relevant = {i for i, r in enumerate(combined) if r.get("sender_match")}

    # Claude only ever sees redacted subjects/snippets/filenames for
    # ranking/summarizing — never attachment ids/bytes, never raw content.
    claude_payload = [
        {k: v for k, v in r.items() if k not in ("id", "attachments")} for r in combined
    ]
    intent_context = f"Detected intent: person={person or 'none'}, target={target}"
    outcome = claude_client.summarize_results(user_query, claude_payload, intent_context=intent_context)

    # Final belt-and-suspenders redaction pass on the model's own output.
    summary = redact(outcome["reply"])

    # Only show the results Claude judged as genuine matches (plus any
    # deterministically-confirmed sender matches, which always count) —
    # the underlying Gmail/Drive search is loose full-text matching, so
    # "find my Aadhaar" can otherwise surface an unrelated "insurance
    # e-card" email just because both contain the word "card".
    relevant_indices = sorted(set(outcome["relevant_indices"]) | forced_relevant)
    relevant = [combined[i] for i in relevant_indices]

    # If Claude's own text summary didn't count any of the
    # deterministically-confirmed sender matches (e.g. it initially
    # concluded "no emails from X" before those were forced back in),
    # replace it with a summary that isn't self-contradictory — the
    # link results below are the source of truth either way.
    if forced_relevant and not (set(outcome["relevant_indices"]) & forced_relevant):
        summary = "Found it — see the matching result(s) below."

    display_results = [
        {
            "title": r.get("subject") or r.get("name"),
            "meta": r.get("from") or r.get("mime_type", ""),
            "date": r.get("date") or r.get("modified", "") or r.get("start", ""),
            "link": r["link"],
            "source": r["source"],
            "start": r.get("start", ""),
            "end": r.get("end", ""),
            "attendees": r.get("attendees", []),
            "location": r.get("location", ""),
            "meet_link": r.get("meet_link", ""),
            "attachments": [
                {
                    "filename": a["filename"],
                    "download_url": (
                        f"/api/download?message_id={r['id']}&attachment_id={a['attachment_id']}"
                        f"&filename={a['filename']}"
                    ),
                }
                for a in r.get("attachments", [])
            ],
        }
        for r in relevant
    ]

    return jsonify({"reply": summary, "results": display_results})


@app.route("/api/download")
def download_attachment():
    """Streams one Gmail attachment straight from the Gmail API to the
    browser as a file download. The bytes pass through this process only
    — they are never parsed, stored on disk, or sent to the Claude API."""
    creds = google_client.get_credentials()
    if creds is None:
        return jsonify({"error": "Google account not connected."}), 401

    message_id = request.args.get("message_id", "")
    attachment_id = request.args.get("attachment_id", "")
    filename = request.args.get("filename") or "attachment"
    if not message_id or not attachment_id:
        return jsonify({"error": "Missing message_id or attachment_id."}), 400

    try:
        data = google_client.get_attachment_bytes(creds, message_id, attachment_id)
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Couldn't fetch attachment: {e}"}), 500

    from werkzeug.utils import secure_filename
    from flask import Response

    safe_name = secure_filename(filename) or "attachment"
    return Response(
        data,
        mimetype="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


# --- Phase 3D: multiple Drive attachments helper ---
def _extract_multiple_attachment_names(text: str):
    """Extract explicit filenames from common 'take X and Y and send' requests.
    Returns a de-duplicated ordered list. Conservative by design.
    """
    import re
    if not text:
        return []
    patterns = [
        r'`([^`]+\.[A-Za-z0-9]{1,8})`',
        r'"([^"]+\.[A-Za-z0-9]{1,8})"',
        r"'([^']+\.[A-Za-z0-9]{1,8})'",
    ]
    found = []
    for pat in patterns:
        found.extend(re.findall(pat, text))
    # Also catch obvious filenames without quoting, but only after a
    # take/send attachment phrase so normal email text isn't treated as a file.
    if re.search(r'\b(take|attach|attachments?|files?)\b', text, re.I) and re.search(r'\b(send|email)\b', text, re.I):
        found.extend(re.findall(
            r'(?<![\w-])([A-Za-z0-9][A-Za-z0-9 _().-]*\.(?:pdf|docx?|xlsx?|pptx?|zip|csv|txt|html?|png|jpe?g))\b',
            text, re.I
        ))
    out = []
    seen = set()
    for name in found:
        name = name.strip()
        key = name.casefold()
        if key not in seen:
            seen.add(key)
            out.append(name)
    return out


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # use_reloader=False: on some Windows Python installs (e.g. the
    # Microsoft Store package), the reloader's file-watcher spuriously
    # detects "changes" in stdlib files and restarts the process — which
    # kills in-flight requests like the blocking Google OAuth flow before
    # it can open a browser window.
    host = os.environ.get("HOST", "127.0.0.1")
    debug = os.environ.get("FLASK_DEBUG", "0").lower() in {"1", "true", "yes"}
    app.run(host=host, port=port, debug=debug, use_reloader=False)
