"""
google_client.py
-----------------
Handles Google OAuth (your own account only) and both search AND write
actions over Gmail, Drive, Calendar and Sheets.

Search (Gmail/Drive/Calendar/Sheets listing) is still read-only metadata
only, same as before. Write actions — sending an email, creating a
calendar event, creating a new sheet, or appending rows to an existing
one — are new, and are ALWAYS gated behind an explicit user confirmation
step in app.py before any of the *_action functions below are called;
this file itself does not do any confirming, it just executes.

Scopes: gmail.readonly + gmail.send, drive.readonly (search only — no
Drive write scope is requested; new sheets are created via the Sheets
API itself, which needs no separate Drive permission), calendar.events
(read + write events), spreadsheets (read + write).
"""

import os
import re

# Our own OAuth callback runs on plain http://localhost — allow that for
# the oauthlib token exchange (this is the standard local-dev escape
# hatch; it does not affect the actual Google-side connection, which is
# always https).
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

# Without this, oauthlib raises "Scope has changed" if Google's token
# response includes any scope beyond exactly what was requested — which
# happens naturally once an account has ever granted a scope (like an
# older calendar.readonly) that isn't in the current SCOPES list. This
# only relaxes oauthlib's own strict comparison; it does not grant this
# app any scope Google didn't actually approve on the consent screen.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    # Send-only — cannot read, modify, or delete mail beyond what
    # gmail.readonly above already allows for search.
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive.readonly",
    # calendar.events (not the broader "calendar" scope) — read + write
    # events on calendars you can already access, but cannot create,
    # delete, or change sharing on the calendars themselves.
    "https://www.googleapis.com/auth/calendar.events",
    # Full read/write, upgraded from spreadsheets.readonly — needed so
    # existing sheets (like a PF sheet you didn't create with this app)
    # can be edited, not just newly-created ones.
    "https://www.googleapis.com/auth/spreadsheets",
]

CREDENTIALS_FILE = os.path.join("credentials", "credentials.json")
TOKEN_FILE = "token.json"

# In-memory map of pending OAuth attempts, keyed by the `state` value
# Google echoes back on redirect. Fine for a single-user local app; each
# entry is discarded as soon as the callback completes (or the process
# restarts).
_pending_flows: dict[str, Flow] = {}


def is_authenticated() -> bool:
    return os.path.exists(TOKEN_FILE)


def disconnect():
    """Revokes this app's access at Google's end (best-effort) and always
    deletes the local token.json, whichever happens first fails. After
    this, is_authenticated() is False and the user must sign in again."""
    creds = get_credentials()
    if creds is not None:
        token = creds.token or creds.refresh_token
        if token:
            try:
                import requests

                requests.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": token},
                    headers={"content-type": "application/x-www-form-urlencoded"},
                    timeout=5,
                )
            except Exception:
                # Revoking at Google's end is best-effort; we still remove
                # the local token below regardless of network issues.
                pass

    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)


def get_credentials():
    """Load cached credentials, refreshing if needed. Returns None if the
    user hasn't connected their Google account yet."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return creds if creds and creds.valid else None


def build_auth_url(redirect_uri: str) -> str:
    """Non-blocking: builds a Google sign-in URL for the user to open
    themselves (in their own browser tab, whichever profile/window they
    choose). Nothing here waits on the user — the actual sign-in is
    completed later, asynchronously, by finish_auth_flow() when Google
    redirects back to our own /oauth2callback route."""
    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError(
            f"Missing {CREDENTIALS_FILE}. Download your OAuth Client ID "
            "JSON from Google Cloud Console and save it there. See README.md."
        )
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE, scopes=SCOPES, redirect_uri=redirect_uri
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        # "false", not "true": we always request the exact full SCOPES
        # list ourselves, so we don't need Google to also carry forward
        # older previously-granted scopes — doing so is what triggers the
        # "Scope has changed" mismatch above. This keeps the granted set
        # equal to exactly what was requested, every time.
        include_granted_scopes="false",
        prompt="consent",
    )
    _pending_flows[state] = flow
    return auth_url


def finish_auth_flow(state: str, authorization_response_url: str):
    """Called from the /oauth2callback route once Google redirects back
    with a `code`. Exchanges it for tokens and saves them to token.json."""
    flow = _pending_flows.pop(state, None)
    if flow is None:
        raise ValueError(
            "This sign-in link already expired or was already used. "
            "Go back and click \"Connect Google Account\" again."
        )
    flow.fetch_token(authorization_response=authorization_response_url)
    creds = flow.credentials
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    return creds


def _expand_name_terms(keywords) -> list[str]:
    """Turns a list of keyword phrases into the fuller set of terms to OR
    together in a Drive `name contains` query.

    Drive's `contains` operator for the name field matches on individual
    tokens (splitting the filename on non-alphanumeric characters like
    "_", "-", "."), not on an arbitrary literal substring. So a clause
    built straight from a multi-word phrase — e.g. "salary payslips"
    (with a space, from a keyword Claude extracted) — will never match a
    real filename like "salary_payslips" (underscore), even though a
    person would call that an obvious match. Splitting every phrase into
    its individual words too (in addition to keeping the phrase itself)
    fixes that, since each single word then matches its own token in the
    filename regardless of what separator the filename actually uses."""
    terms = keywords if isinstance(keywords, (list, tuple)) else [keywords]
    expanded: list[str] = []
    for phrase in terms:
        phrase = (phrase or "").strip()
        if not phrase:
            continue
        if phrase not in expanded:
            expanded.append(phrase)
        for word in re.split(r"[\s_\-.]+", phrase):
            word = word.strip()
            if word and len(word) > 2 and word not in expanded:
                expanded.append(word)
    return expanded


def _drive_name_query(keywords, extra_clause: str = "") -> str:
    """Builds a Drive `q=` string that ORs a `name contains` clause for
    every expanded term, plus any extra filter (e.g. a mimeType check)."""
    terms = _expand_name_terms(keywords)
    name_clauses = " or ".join(f"name contains '{t}'" for t in terms)
    q = f"({name_clauses}) and trashed = false"
    if extra_clause:
        q += f" and {extra_clause}"
    return q


def _gmail_service(creds):
    return build("gmail", "v1", credentials=creds)


def _drive_service(creds):
    return build("drive", "v3", credentials=creds)

def _calendar_service(creds):
    return build("calendar", "v3", credentials=creds)


def _extract_meet_link(event: dict) -> str:
    """Pulls a Google Meet video link off a Calendar event, if it has one.
    Checks the simple `hangoutLink` field first, then falls back to
    scanning `conferenceData.entryPoints` for a "video" entry point (the
    more general place Google puts it for newer/other conferencing setups)."""
    link = event.get("hangoutLink", "")
    if link:
        return link
    conference_data = event.get("conferenceData", {}) or {}
    for entry_point in conference_data.get("entryPoints", []) or []:
        if entry_point.get("entryPointType") == "video":
            return entry_point.get("uri", "")
    return ""


def search_calendar(creds, time_min, time_max, max_results=20):
    service = _calendar_service(creds)

    response = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=max_results,
        )
        .execute()
    )

    events = response.get("items", [])

    results = []

    for event in events:
        start = event.get("start", {})
        end = event.get("end", {})

        results.append(
            {
                "source": "calendar",
                "id": event.get("id", ""),
                "summary": event.get("summary", "(No title)"),
                "description": event.get("description", ""),
                "start": start.get("dateTime") or start.get("date", ""),
                "end": end.get("dateTime") or end.get("date", ""),
                "location": event.get("location", ""),
                "html_link": event.get("htmlLink", ""),
                "meet_link": _extract_meet_link(event),
            }
        )

    return results

def search_gmail(creds, keywords, max_results=5):
    service = _gmail_service(creds)
    # Deliberately loose (not phrase-quoted): exact-phrase matching missed
    # real documents whose subject used a different spelling than the
    # "correct" one Claude generates (e.g. "Aadhar Card" vs "Aadhaar
    # card") — better to over-fetch here and let summarize_results()
    # (claude_client.py) filter down to genuine matches afterwards.
    terms = keywords if isinstance(keywords, (list, tuple)) else [keywords]
    query = " OR ".join(terms)
    resp = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    messages = resp.get("messages", [])

    results = []
    for m in messages:
        # format="full" (rather than "metadata") so we can also list
        # attachment filenames/ids. We deliberately still ignore the
        # decoded body text of any non-attachment parts — only headers,
        # the auto snippet, and attachment metadata are ever used.
        msg = service.users().messages().get(userId="me", id=m["id"], format="full").execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        results.append(
            {
                "source": "gmail",
                "id": m["id"],
                "subject": headers.get("Subject", "(no subject)"),
                "from": headers.get("From", ""),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", ""),
                "link": f"https://mail.google.com/mail/u/0/#all/{m['id']}",
                "attachments": _extract_attachments(msg.get("payload", {})),
            }
        )
    return results


def _extract_attachments(payload: dict) -> list[dict]:
    """Walk a Gmail message payload and collect attachment metadata only
    (filename, attachmentId, mimeType, size) — never any decoded body
    content."""
    found = []

    def walk(part):
        body = part.get("body", {}) or {}
        filename = part.get("filename")
        if filename and body.get("attachmentId"):
            found.append(
                {
                    "filename": filename,
                    "attachment_id": body["attachmentId"],
                    "mime_type": part.get("mimeType", "application/octet-stream"),
                    "size": body.get("size", 0),
                }
            )
        for sub_part in part.get("parts", []) or []:
            walk(sub_part)

    walk(payload)
    return found


def get_attachment_bytes(creds, message_id: str, attachment_id: str) -> bytes:
    """Fetches raw attachment bytes straight from the Gmail API. This app
    streams them directly to your browser as a download — it never stores,
    parses, or forwards them anywhere else (in particular: never to the
    Claude API)."""
    import base64

    service = _gmail_service(creds)
    att = (
        service.users()
        .messages()
        .attachments()
        .get(userId="me", messageId=message_id, id=attachment_id)
        .execute()
    )
    data = att.get("data", "")
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def search_drive(creds, keywords, max_results=5):
    service = _drive_service(creds)
    q = _drive_name_query(keywords)

    resp = (
        service.files()
        .list(
            q=q,
            pageSize=max_results,
            fields="files(id,name,mimeType,modifiedTime,webViewLink)",
        )
        .execute()
    )

    results = []
    for f in resp.get("files", []):
        results.append(
            {
                "source": "drive",
                "id": f["id"],
                "name": f.get("name", ""),
                "mime_type": f.get("mimeType", ""),
                "modified": f.get("modifiedTime", ""),
                "link": f.get("webViewLink", ""),
            }
        )
    return results


_SHEET_MIME_TYPE = "application/vnd.google-apps.spreadsheet"


def _sheets_service(creds):
    return build("sheets", "v4", credentials=creds)


def search_sheets(creds, keywords, max_results=5):
    """Same idea as search_drive, but narrowed to Google Sheets files only
    (via Drive's mimeType filter — Sheets don't have their own "list by
    name" endpoint, Drive is the source of truth for file metadata)."""
    service = _drive_service(creds)
    q = _drive_name_query(keywords, extra_clause=f"mimeType = '{_SHEET_MIME_TYPE}'")

    resp = (
        service.files()
        .list(
            q=q,
            pageSize=max_results,
            fields="files(id,name,modifiedTime,webViewLink)",
        )
        .execute()
    )

    results = []
    for f in resp.get("files", []):
        results.append(
            {
                "source": "sheets",
                "id": f["id"],
                "name": f.get("name", ""),
                "mime_type": _SHEET_MIME_TYPE,
                "modified": f.get("modifiedTime", ""),
                "link": f.get("webViewLink", ""),
            }
        )
    return results


def get_sheet_tab_names(creds, spreadsheet_id: str) -> list[str]:
    """Returns the tab (worksheet) names inside a spreadsheet, e.g.
    ["Sheet1", "Q3 Budget"]. Only reads structure, not any cell values."""
    service = _sheets_service(creds)
    meta = (
        service.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets.properties.title")
        .execute()
    )
    return [
        s["properties"]["title"]
        for s in meta.get("sheets", [])
        if s.get("properties", {}).get("title")
    ]


def get_sheet_values(creds, spreadsheet_id: str, cell_range: str) -> list[list[str]]:
    """Reads a cell range (e.g. "Sheet1!A1:J50") as a 2D array of strings.
    Caller is responsible for redacting every cell before it is shown to
    the user or sent to the Claude API — same rule as Gmail snippets and
    Drive filenames elsewhere in this file."""
    service = _sheets_service(creds)
    resp = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=cell_range)
        .execute()
    )
    return resp.get("values", [])


# =====================================================================
# WRITE ACTIONS
#
# Every function below actually sends/creates/edits something on your
# real account. None of them are ever called directly from a user's raw
# message — app.py always parses the request into a proposed action,
# shows you exactly what it's about to do, and only calls one of these
# once you've explicitly confirmed. Treat that confirmation step as load-
# bearing if you ever modify the routing in app.py.
# =====================================================================


def send_email(creds, to: str, subject: str, body: str) -> dict:
    """Sends a plain-text email from the connected account. Requires the
    gmail.send scope (send-only — cannot read/modify/delete mail beyond
    what gmail.readonly separately allows for search)."""
    import base64
    from email.mime.text import MIMEText

    service = _gmail_service(creds)
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {
        "id": sent.get("id", ""),
        "link": f"https://mail.google.com/mail/u/0/#sent/{sent.get('id', '')}",
    }


def create_calendar_event(
    creds,
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str = "",
    location: str = "",
    attendees: list | None = None,
    add_meet_link: bool = False,
) -> dict:
    """Creates a new event on the primary calendar. start_iso/end_iso
    must be full ISO 8601 datetimes with a timezone offset, e.g.
    "2026-09-04T15:00:00+05:30". Requires the calendar.events scope."""
    service = _calendar_service(creds)
    body = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": {"dateTime": start_iso},
        "end": {"dateTime": end_iso},
    }
    if attendees:
        body["attendees"] = [{"email": a} for a in attendees]
    if add_meet_link:
        body["conferenceData"] = {"createRequest": {"requestId": os.urandom(8).hex()}}

    event = (
        service.events()
        .insert(
            calendarId="primary",
            body=body,
            conferenceDataVersion=1 if add_meet_link else 0,
            sendUpdates="all" if attendees else "none",
        )
        .execute()
    )
    return {
        "id": event.get("id", ""),
        "link": event.get("htmlLink", ""),
        "meet_link": _extract_meet_link(event),
    }


def create_sheet(creds, title: str, header_row: list | None = None) -> dict:
    """Creates a brand-new Google Sheet. This lands in your Drive
    automatically — creating a spreadsheet via the Sheets API only
    requires the `spreadsheets` scope, no separate Drive write scope.
    Optionally writes one header row to the new sheet's first tab."""
    service = _sheets_service(creds)
    spreadsheet = (
        service.spreadsheets().create(body={"properties": {"title": title}}).execute()
    )
    spreadsheet_id = spreadsheet["spreadsheetId"]
    link = spreadsheet.get(
        "spreadsheetUrl", f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    )
    if header_row:
        first_tab = spreadsheet["sheets"][0]["properties"]["title"]
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{first_tab}'!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [header_row]},
        ).execute()
    return {"id": spreadsheet_id, "link": link}


def append_sheet_rows(creds, spreadsheet_id: str, tab_name: str, rows: list) -> dict:
    """Appends one or more rows to the end of an existing sheet/tab.
    Uses Sheets' own `append` operation, which finds the next empty row
    itself — this app never computes row numbers or risks overwriting
    existing data. Requires the (read/write) spreadsheets scope."""
    service = _sheets_service(creds)
    resp = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab_name}'!A1",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        )
        .execute()
    )
    updates = resp.get("updates", {})
    return {
        "updated_range": updates.get("updatedRange", ""),
        "updated_rows": updates.get("updatedRows", 0),
    }