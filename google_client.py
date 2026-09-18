"""
google_client.py
-----------------
Handles Google OAuth (your own account only) and search/action access over
Gmail, Drive metadata, and Google Calendar event metadata.

Gmail search is read-only; Gmail sending uses the separate `gmail.send` scope.
Calendar uses the events read/write scope for confirmed event creation, modification, and cancellation. Drive uses the full Drive scope only for explicit,
user-confirmed file organization actions.

Results returned to the rest of the app are METADATA ONLY:
  - Gmail: subject, sender, date, a short auto snippet (later redacted),
    and a link to open the message in Gmail.
  - Drive: filename, mime type, modified time, and the file's own
    webViewLink so the user opens it in Drive with their normal
    permissions/auth — this app never downloads file contents.
"""

import os
import re
import base64
import io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# Our own OAuth callback runs on plain http://localhost — allow that for
# the oauthlib token exchange (this is the standard local-dev escape
# hatch; it does not affect the actual Google-side connection, which is
# always https).
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/calendar.events",
]

CREDENTIALS_FILE = os.environ.get("GOOGLE_CREDENTIALS_FILE", os.path.join("credentials", "credentials.json"))
TOKEN_FILE = os.environ.get("TOKEN_FILE", "token.json")

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
        token_parent = os.path.dirname(os.path.abspath(TOKEN_FILE))
        os.makedirs(token_parent, exist_ok=True)
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
        include_granted_scopes="true",
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
    token_parent = os.path.dirname(os.path.abspath(TOKEN_FILE))
    os.makedirs(token_parent, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    return creds


def _gmail_service(creds):
    return build("gmail", "v1", credentials=creds)


def _download_drive_bytes(creds, file_id: str, mime_type: str) -> bytes:
    """Download the actual Drive file bytes into memory.

    Uses Google's Drive media/export endpoints directly with the current
    OAuth access token. This avoids a subtle failure mode where a generic
    Drive ``files.get`` response can be returned as metadata JSON instead of
    the binary file. Native Google Workspace files are exported first.
    """
    import requests

    export_map = {
        "application/vnd.google-apps.document": "application/pdf",
        "application/vnd.google-apps.spreadsheet": (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        "application/vnd.google-apps.presentation": (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ),
    }

    if mime_type in export_map:
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}/export"
        params = {"mimeType": export_map[mime_type]}
    else:
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
        params = {"alt": "media"}

    # Use the already-refreshed OAuth credential directly. This avoids
    # accidentally sending a metadata request through the discovery client.
    access_token = getattr(creds, "token", None)
    if not access_token:
        raise ValueError("No valid Google access token is available for the Drive download.")

    response = requests.get(
        url,
        params=params,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=60,
    )

    content_type = (response.headers.get("Content-Type") or "").lower()
    data = response.content

    if response.status_code != 200:
        # Google errors are JSON; surface a compact useful message without
        # exposing tokens or other credentials.
        try:
            detail = response.json().get("error", {}).get("message", "")
        except Exception:
            detail = ""
        raise ValueError(
            f"Google Drive download failed with HTTP {response.status_code}"
            + (f": {detail}" if detail else "")
        )

    # A successful media request must be binary. If Google returned JSON,
    # it is almost certainly file metadata or an API error accidentally
    # routed through a metadata endpoint — never attach that as a document.
    if "application/json" in content_type or data.lstrip().startswith(b"{"):
        preview = data[:120].replace(b"\r", b" ").replace(b"\n", b" ")
        raise ValueError(
            f'Drive returned JSON metadata instead of file content for "{file_id}". '
            f"Preview: {preview!r}"
        )

    if not data:
        raise ValueError("Drive returned an empty file.")

    return data

def _validate_attachment_bytes(data: bytes, filename: str, mime_type: str) -> None:
    """Reject obviously corrupt/mismatched Drive content before Gmail send."""
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise ValueError(f'Drive file "{filename}" downloaded as empty or non-binary data.')

    lower_name = filename.lower()
    if lower_name.endswith(".pdf") or mime_type == "application/pdf":
        if not data.startswith(b"%PDF-"):
            preview = data[:80].replace(b"\r", b" ").replace(b"\n", b" ")
            raise ValueError(
                f'Drive file "{filename}" did not download as a valid PDF. '
                f"The downloaded content does not start with %PDF-. Preview: {preview!r}"
            )
    elif lower_name.endswith((".docx", ".xlsx", ".pptx")):
        if not data.startswith(b"PK"):
            raise ValueError(f'Drive file "{filename}" did not download as a valid Office ZIP package.')
    elif lower_name.endswith(".zip"):
        if not data.startswith(b"PK"):
            raise ValueError(f'Drive file "{filename}" did not download as a valid ZIP file.')


def send_gmail_attachment(creds, to: str, subject: str, body: str, file_id: str, filename: str):
    """Send one Drive file as a Gmail attachment.

    Caller MUST obtain explicit confirmation immediately before calling this
    function. The file is downloaded into memory only and is never sent to
    Claude or persisted by this function.
    """
    to = (to or "").strip()
    subject = (subject or "").strip()
    body = body or ""
    filename = (filename or "").strip()
    if not to or "@" not in to:
        raise ValueError("A valid recipient email address is required.")
    if not subject:
        raise ValueError("An email subject is required.")
    if not file_id or not filename:
        raise ValueError("A Drive file and complete filename are required.")

    service = _gmail_service(creds)
    drive = _drive_service(creds)
    meta = drive.files().get(fileId=file_id, fields="id,name,mimeType").execute()
    mime_type = meta.get("mimeType", "application/octet-stream")
    actual_name = meta.get("name") or filename

    export_extensions = {
        "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
        "application/vnd.google-apps.spreadsheet": (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"
        ),
        "application/vnd.google-apps.presentation": (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"
        ),
    }

    data = _download_drive_bytes(creds, file_id, mime_type)
    attachment_mime = mime_type
    if mime_type in export_extensions:
        attachment_mime, extension = export_extensions[mime_type]
        if not actual_name.lower().endswith(extension):
            actual_name += extension

    _validate_attachment_bytes(data, actual_name, attachment_mime)

    message = MIMEMultipart()
    message["to"] = to
    message["subject"] = subject
    message.attach(MIMEText(body, _subtype="plain", _charset="utf-8"))

    maintype, subtype = (
        attachment_mime.split("/", 1)
        if "/" in attachment_mime
        else ("application", "octet-stream")
    )
    part = MIMEBase(maintype, subtype)
    part.set_payload(data)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename=actual_name)
    message.attach(part)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return service.users().messages().send(userId="me", body={"raw": raw}).execute()



def send_gmail_attachments(creds, to: str, subject: str, body: str, files: list[dict]):
    """Send one Gmail message with multiple Drive attachments.
    Downloads and validates every file before Gmail is called, so partial
    sends cannot occur when one attachment is invalid or unavailable.
    """
    to = (to or "").strip(); subject = (subject or "").strip(); body = body or ""
    if not to or "@" not in to: raise ValueError("A valid recipient email address is required.")
    if not subject: raise ValueError("An email subject is required.")
    if not files: raise ValueError("At least one Drive attachment is required.")

    drive = _drive_service(creds)
    prepared = []
    export_extensions = {
        "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
        "application/vnd.google-apps.spreadsheet": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
        "application/vnd.google-apps.presentation": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
    }
    for item in files:
        file_id = item.get("file_id"); filename = (item.get("file_name") or "").strip()
        if not file_id or not filename: raise ValueError("Every attachment needs a Drive file ID and filename.")
        meta = drive.files().get(fileId=file_id, fields="id,name,mimeType").execute()
        mime_type = meta.get("mimeType", "application/octet-stream")
        actual_name = meta.get("name") or filename
        data = _download_drive_bytes(creds, file_id, mime_type)
        attachment_mime = mime_type
        if mime_type in export_extensions:
            attachment_mime, extension = export_extensions[mime_type]
            if not actual_name.lower().endswith(extension): actual_name += extension
        _validate_attachment_bytes(data, actual_name, attachment_mime)
        prepared.append((actual_name, attachment_mime, data))

    message = MIMEMultipart(); message["to"] = to; message["subject"] = subject
    message.attach(MIMEText(body, _subtype="plain", _charset="utf-8"))
    for actual_name, attachment_mime, data in prepared:
        maintype, subtype = attachment_mime.split("/", 1) if "/" in attachment_mime else ("application", "octet-stream")
        part = MIMEBase(maintype, subtype); part.set_payload(data); encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=actual_name); message.attach(part)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return _gmail_service(creds).users().messages().send(userId="me", body={"raw": raw}).execute()

def send_gmail_message(creds, to: str, subject: str, body: str):
    """Send one plain-text Gmail message. Caller MUST obtain explicit
    confirmation immediately before calling this function.

    The function accepts only the recipient, subject, and body selected by
    the local app; it does not search the mailbox or add hidden content.
    """
    to = (to or "").strip()
    subject = (subject or "").strip()
    body = body or ""
    if not to or "@" not in to:
        raise ValueError("A valid recipient email address is required.")
    if not subject:
        raise ValueError("An email subject is required.")
    if not body.strip():
        raise ValueError("An email body is required.")

    service = _gmail_service(creds)
    message = MIMEText(body, _subtype="plain", _charset="utf-8")
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    sent = (
        service.users()
        .messages()
        .send(userId="me", body={"raw": raw})
        .execute()
    )
    return sent


def _drive_service(creds):
    return build("drive", "v3", credentials=creds)


def _calendar_service(creds):
    return build("calendar", "v3", credentials=creds)


def _sender_matches(from_header: str, person: str) -> bool:
    """Return True when a sender header matches the requested person.

    Matching is deterministic and case-insensitive. It checks the display
    name, the full email address, and the email local-part. This keeps person
    searches independent of Claude's ranking decision.
    """
    if not person or not from_header:
        return False

    person_l = person.strip().lower()
    if not person_l:
        return False

    # Normalize punctuation so names such as "Jeevan-Kumar" and
    # "Jeevan Kumar" remain easy to match.
    normalized_from = re.sub(r"[^a-z0-9]+", " ", from_header.lower()).strip()
    normalized_person = re.sub(r"[^a-z0-9]+", " ", person_l).strip()
    person_tokens = [t for t in normalized_person.split() if t]

    # Strongest check: every token in the requested name appears in the
    # sender's display/header text. This supports full or partial names.
    if person_tokens and all(re.search(r"\b" + re.escape(token) + r"\b", normalized_from) for token in person_tokens):
        return True

    # Check the address itself, including local-part aliases such as
    # jeevan.kumar or jeevan_kumar.
    email_match = re.search(r"[\w.+'-]+@[\w.-]+", from_header)
    if email_match:
        address = email_match.group(0).lower()
        local_part = address.split("@", 1)[0]
        compact_local = re.sub(r"[^a-z0-9]+", "", local_part)
        compact_person = re.sub(r"[^a-z0-9]+", "", person_l)
        if compact_person and (compact_person in compact_local or compact_local in compact_person):
            return True

    return False


def _as_term_list(keywords) -> list[str]:
    if not keywords:
        return []
    return list(keywords) if isinstance(keywords, (list, tuple)) else [keywords]


def _list_gmail_messages(service, query: str, max_results: int) -> list:
    resp = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    return resp.get("messages", [])


def search_gmail(creds, keywords=None, person=None, max_results=8):
    """Searches Gmail. `person`, if given, is a deterministically
    detected sender name (see query_intent.py / claude_client.py) — it
    is used to build a `from:` restricted query AND to verify each
    returned message's actual From header in Python (_sender_matches),
    so a genuine match is never lost just because an LLM keyword step
    didn't recognize the name.

    `keywords` are additional subject/body search terms, ORed together.
    Deliberately loose (not phrase-quoted): exact-phrase matching missed
    real documents whose subject used a different spelling than the
    "correct" one Claude generates (e.g. "Aadhar Card" vs "Aadhaar
    card") — better to over-fetch here and let summarize_results()
    (claude_client.py) filter down to genuine matches afterwards.

    max_results was raised from the original 5 to 8: with a plain
    keyword-only query 5 was enough, but once a `from:` clause narrows
    things down there's headroom to fetch a few more without drowning
    Claude's ranking step in noise.
    """
    service = _gmail_service(creds)
    terms = _as_term_list(keywords)

    query_parts = []
    if person:
        # Gmail's from: operator matches tokens in both the display name
        # and the address, e.g. from:jeevan matches
        # "Jeevan Kumar <jeevan@example.com>".
        query_parts.append(f"from:{person}")
    if terms:
        query_parts.append("(" + " OR ".join(terms) + ")")
    query = " ".join(query_parts).strip()

    messages = _list_gmail_messages(service, query, max_results)

    # Safety net: Gmail's from: operator can occasionally miss a real
    # sender (unusual header encoding, a nickname the user typed that
    # doesn't appear verbatim, etc). If a person was named and the
    # strict from: search came back empty, broaden to a plain keyword
    # search on the name itself and verify the sender match ourselves.
    if person and not messages:
        fallback_query = " OR ".join([person] + terms)
        messages = _list_gmail_messages(service, fallback_query, max(max_results, 15))

    results = []
    for m in messages:
        # format="full" (rather than "metadata") so we can also list
        # attachment filenames/ids. We deliberately still ignore the
        # decoded body text of any non-attachment parts — only headers,
        # the auto snippet, and attachment metadata are ever used.
        msg = service.users().messages().get(userId="me", id=m["id"], format="full").execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        from_header = headers.get("From", "")
        results.append(
            {
                "source": "gmail",
                "id": m["id"],
                "subject": headers.get("Subject", "(no subject)"),
                "from": from_header,
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", ""),
                "link": f"https://mail.google.com/mail/u/0/#all/{m['id']}",
                "attachments": _extract_attachments(msg.get("payload", {})),
                # True only when Python itself verified the From header
                # against the requested person — never a guess handed to
                # or made by Claude.
                "sender_match": _sender_matches(from_header, person) if person else False,
            }
        )
    return results


def resolve_person_emails(creds, person: str, max_results: int = 15) -> list[str]:
    """Resolve a named human to verified, usable Gmail sender addresses.

    Only actual From headers are considered. Automated/bulk/no-reply senders
    are excluded so a person name cannot accidentally resolve to an unrelated
    notification mailbox. If no verified human sender remains, callers must
    ask for the complete email address rather than guessing.
    """
    person = (person or "").strip()
    if not person:
        return []

    matches = search_gmail(creds, keywords=None, person=person, max_results=max_results)
    email_re = re.compile(
        r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
        r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
    )
    automated_markers = {
        "no-reply", "noreply", "no_reply", "donotreply", "do-not-reply",
        "mailer-daemon", "notifications", "notification", "alerts",
        "alert", "newsletter", "marketing", "updates", "support"
    }

    emails = []
    for item in matches:
        if not item.get("sender_match"):
            continue
        from_header = item.get("from", "")
        for email in email_re.findall(from_header):
            local, domain = email.lower().split("@", 1)
            if any(marker in local for marker in automated_markers):
                continue
            if "noreply" in domain or "no-reply" in domain:
                continue
            if email.lower() not in [e.lower() for e in emails]:
                emails.append(email)

    return emails[:max_results]

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



def _calendar_time_window(query: str, now=None):
    """Return a local-time window for common Calendar phrases.

    Supports:
      - today / tomorrow / yesterday
      - this week / next week
      - explicit dates such as "28th August", "August 28", "28 Aug 2026"
      - numeric dates such as "28/08/2026"
      - "upcoming" / "next meeting" as an open-ended future search

    The app is a single-user local tool, so the machine's local timezone is
    used for the Calendar API RFC3339 timestamps.
    """
    from datetime import datetime, timedelta, time

    now = now or datetime.now().astimezone()
    q = (query or "").lower()

    # Explicit date patterns. If the year is omitted, choose the next
    # occurrence of that month/day (current year when it is still upcoming).
    month_map = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }

    explicit = None

    # DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY (year optional).
    m = re.search(r"\b(\d{1,2})[\/\-.](\d{1,2})(?:[\/\-.](\d{4}))?\b", q)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now.year
        try:
            candidate = datetime(year, month, day, tzinfo=now.tzinfo)
            if not m.group(3) and candidate.date() < now.date():
                candidate = candidate.replace(year=year + 1)
            explicit = candidate
        except ValueError:
            explicit = None

    # "28th August 2026", "28 August", "28 Aug".
    if explicit is None:
        m = re.search(
            r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
            r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
            r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
            r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
            r"(?:\s*,?\s*(\d{4}))?\b",
            q,
        )
        if m:
            day = int(m.group(1))
            month = month_map[m.group(2)]
            year = int(m.group(3)) if m.group(3) else now.year
            try:
                candidate = datetime(year, month, day, tzinfo=now.tzinfo)
                if not m.group(3) and candidate.date() < now.date():
                    candidate = candidate.replace(year=year + 1)
                explicit = candidate
            except ValueError:
                explicit = None

    # "August 28 2026", "Aug 28".
    if explicit is None:
        m = re.search(
            r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
            r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
            r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
            r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4}))?\b",
            q,
        )
        if m:
            month = month_map[m.group(1)]
            day = int(m.group(2))
            year = int(m.group(3)) if m.group(3) else now.year
            try:
                candidate = datetime(year, month, day, tzinfo=now.tzinfo)
                if not m.group(3) and candidate.date() < now.date():
                    candidate = candidate.replace(year=year + 1)
                explicit = candidate
            except ValueError:
                explicit = None

    if explicit is not None:
        start = datetime.combine(explicit.date(), time.min, tzinfo=now.tzinfo)
        return start, start + timedelta(days=1)

    if "tomorrow" in q:
        day = (now + timedelta(days=1)).date()
        start = datetime.combine(day, time.min, tzinfo=now.tzinfo)
        return start, start + timedelta(days=1)

    if "today" in q:
        start = datetime.combine(now.date(), time.min, tzinfo=now.tzinfo)
        return start, start + timedelta(days=1)

    if "yesterday" in q:
        end = datetime.combine(now.date(), time.min, tzinfo=now.tzinfo)
        return end - timedelta(days=1), end

    if "this week" in q:
        start = datetime.combine(
            (now - timedelta(days=now.weekday())).date(),
            time.min,
            tzinfo=now.tzinfo,
        )
        return start, start + timedelta(days=7)

    if "next week" in q:
        start = datetime.combine(
            (now + timedelta(days=7 - now.weekday())).date(),
            time.min,
            tzinfo=now.tzinfo,
        )
        return start, start + timedelta(days=7)

    # "upcoming", "next meeting", "what's next", etc. are open-ended:
    # search from now forward rather than forcing a 7-day window.
    future_hints = (
        "upcoming", "next meeting", "next event", "what's next",
        "whats next", "future", "coming up",
    )
    if any(hint in q for hint in future_hints):
        return now.replace(second=0, microsecond=0), None

    # A generic calendar question gets a useful near-future window.
    start = now.replace(second=0, microsecond=0)
    return start, start + timedelta(days=7)


def _clean_calendar_keywords(keywords) -> list[str]:
    """Remove words that describe the Calendar query itself.

    LLM keyword extraction can return terms such as "upcoming events" or
    "28th August". Those are routing/date instructions, not event content.
    Keep distinctive topic/person terms such as "CP4I" or "Abhay".
    """
    generic = {
        "calendar", "calendars", "meeting", "meetings", "meet", "event",
        "events", "appointment", "appointments", "schedule", "scheduled",
        "agenda", "invite", "invitation", "google", "upcoming", "future",
        "today", "tomorrow", "yesterday", "week", "weeks", "this", "next",
        "any", "do", "does", "did", "i", "me", "my", "have", "has",
        "on", "for", "with", "at", "the", "a", "an", "what", "when",
        "show", "find", "there", "anything", "coming", "up",
    }
    cleaned = []
    for raw in keywords or []:
        text = str(raw).strip()
        if not text:
            continue
        # Split compound phrases and retain only distinctive tokens.
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        kept = [t for t in tokens if t not in generic and not t.isdigit()]
        # Month names and ordinal date fragments are temporal, not topics.
        kept = [
            t for t in kept
            if t not in {
                "jan", "january", "feb", "february", "mar", "march",
                "apr", "april", "may", "jun", "june", "jul", "july",
                "aug", "august", "sep", "sept", "september", "oct",
                "october", "nov", "november", "dec", "december",
            }
        ]
        if kept:
            cleaned.extend(kept)
    # Preserve order while de-duplicating.
    return list(dict.fromkeys(cleaned))[:8]

def _calendar_event_matches(event: dict, keywords=None, person=None) -> bool:
    """Deterministic relevance check over safe Calendar metadata."""
    text_parts = [
        event.get("summary", ""),
        event.get("description", ""),
        event.get("location", ""),
        event.get("organizer", {}).get("displayName", ""),
        event.get("organizer", {}).get("email", ""),
    ]
    attendees = event.get("attendees", []) or []
    for a in attendees:
        text_parts.extend([a.get("displayName", ""), a.get("email", "")])
    haystack = " ".join(str(x) for x in text_parts).lower()

    if person:
        person_norm = re.sub(r"[^a-z0-9]+", " ", person.lower()).strip()
        tokens = [t for t in person_norm.split() if t]
        if tokens and not all(re.search(r"\b" + re.escape(t) + r"\b", haystack) for t in tokens):
            # Also allow compact matching for addresses such as john.smith.
            compact_haystack = re.sub(r"[^a-z0-9]+", "", haystack)
            compact_person = re.sub(r"[^a-z0-9]+", "", person.lower())
            if not compact_person or compact_person not in compact_haystack:
                return False

    terms = [str(k).strip().lower() for k in (keywords or []) if str(k).strip()]
    if terms:
        # Calendar query terms are ANDed only when a topic/person was
        # explicitly requested; this prevents "meeting" from matching
        # every event while still allowing "CP4I meeting" to work.
        if not all(term in haystack for term in terms):
            return False
    return True


def search_calendar(creds, user_query: str, keywords=None, person=None, max_results=20):
    """Read-only Calendar search returning event metadata and links only.

    Supports common natural-language windows such as today, tomorrow,
    this week and next week. It also deterministically filters person/topic
    matches so Claude cannot accidentally turn an unrelated event into a
    match.
    """
    service = _calendar_service(creds)
    start, end = _calendar_time_window(user_query)
    keywords = _clean_calendar_keywords(keywords)

    params = {
        "calendarId": "primary",
        "timeMin": start.isoformat(),
        "singleEvents": True,
        "orderBy": "startTime",
        "maxResults": max_results,
    }
    # For "upcoming" searches, leave timeMax unset so Google Calendar can
    # return future events beyond an arbitrary 7-day cutoff.
    if end is not None:
        params["timeMax"] = end.isoformat()

    resp = service.events().list(**params).execute()

    results = []
    for event in resp.get("items", []):
        if event.get("status") == "cancelled":
            continue
        if not _calendar_event_matches(event, keywords=keywords, person=person):
            continue

        start_data = event.get("start", {}) or {}
        end_data = event.get("end", {}) or {}
        organizer = event.get("organizer", {}) or {}
        attendees = event.get("attendees", []) or []

        attendee_names = []
        for attendee in attendees:
            label = attendee.get("displayName") or attendee.get("email")
            if label:
                attendee_names.append(label)

        results.append(
            {
                "source": "calendar",
                "id": event.get("id", ""),
                "name": event.get("summary") or "(untitled event)",
                "start": start_data.get("dateTime") or start_data.get("date", ""),
                "end": end_data.get("dateTime") or end_data.get("date", ""),
                "from": organizer.get("displayName") or organizer.get("email", ""),
                "organizer_email": organizer.get("email", ""),
                "attendees": attendee_names[:20],
                "location": event.get("location", ""),
                "description": event.get("description", "")[:500],
                "link": event.get("htmlLink", ""),
                "meet_link": event.get("hangoutLink", ""),
                "status": event.get("status", ""),
                "calendar_id": "primary",
                "event_match": True,
            }
        )
    return results



def create_calendar_event(creds, summary, start_dt, end_dt, attendees=None, description="",
                          calendar_id="primary", add_google_meet=True):
    """Create a Calendar event after explicit user confirmation.
    Optionally requests a Google Meet conference using Calendar API.
    """
    service = _calendar_service(creds)
    body = {
        "summary": summary,
        "description": description or "",
        "start": {"dateTime": start_dt.isoformat(), "timeZone": str(start_dt.tzinfo)},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": str(end_dt.tzinfo)},
    }
    attendees = attendees or []
    if attendees:
        body["attendees"] = [{"email": a} for a in attendees]

    kwargs = {"calendarId": calendar_id, "body": body, "sendUpdates": "all"}
    if add_google_meet:
        import uuid as _uuid
        body["conferenceData"] = {
            "createRequest": {
                "requestId": _uuid.uuid4().hex,
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }
        kwargs["conferenceDataVersion"] = 1

    event = service.events().insert(**kwargs).execute()
    return event

def update_calendar_event(creds, event_id, start_dt=None, end_dt=None, calendar_id="primary"):
    """Update an existing timed Calendar event after explicit confirmation."""
    service = _calendar_service(creds)
    body = {}
    if start_dt is not None:
        body["start"] = {"dateTime": start_dt.isoformat(), "timeZone": str(start_dt.tzinfo)}
    if end_dt is not None:
        body["end"] = {"dateTime": end_dt.isoformat(), "timeZone": str(end_dt.tzinfo)}
    return service.events().patch(
        calendarId=calendar_id, eventId=event_id, body=body, sendUpdates="all"
    ).execute()


def cancel_calendar_event(creds, event_id, calendar_id="primary"):
    """Cancel/delete an existing Calendar event after explicit confirmation."""
    service = _calendar_service(creds)
    return service.events().delete(
        calendarId=calendar_id, eventId=event_id, sendUpdates="all"
    ).execute()

def search_drive(creds, keywords, max_results=5):
    service = _drive_service(creds)
    terms = keywords if isinstance(keywords, (list, tuple)) else [keywords]
    name_clauses = " or ".join(f"name contains '{t}'" for t in terms)
    q = f"({name_clauses}) and trashed = false"

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


def find_drive_files_by_name(creds, name: str, max_results: int = 10) -> list[dict]:
    """Find Drive files/folders by name metadata only.

    Used by Phase 3 actions to resolve a human-friendly source or destination
    before any write is attempted.
    """
    service = _drive_service(creds)
    name = (name or "").strip()
    if not name:
        return []

    safe = name.replace("\\", "\\\\").replace("'", "\\'")
    q = f"name contains '{safe}' and trashed = false"
    resp = (
        service.files()
        .list(
            q=q,
            pageSize=max_results,
            fields="files(id,name,mimeType,modifiedTime,webViewLink,parents)",
            orderBy="modifiedTime desc",
        )
        .execute()
    )
    return resp.get("files", [])


def _drive_name_terms(name: str) -> list[str]:
    """Turn a human description of a Drive file into useful filename terms.

    The action parser deliberately keeps the user's wording, but people often
    say "CP4I presentation" when the actual filename is something like
    "cp4i_escalation_presentation (1).html".  Generic file-type words are
    therefore excluded from the fallback search, while distinctive filename
    tokens are retained.
    """
    text = (name or "").strip().lower()
    text = re.sub(r"^\s*(?:the|a|an|my)\s+", "", text)
    # Drop a trailing natural-language type label when the preceding text
    # already looks like a filename or a named document.
    text = re.sub(
        r"\s+(?:presentation|document|file|pdf|spreadsheet|sheet|slide|slides)\s*$",
        "",
        text,
    )
    raw_tokens = re.findall(r"[a-z0-9]+", text)
    generic = {
        "the", "a", "an", "my", "file", "files", "document", "documents",
        "presentation", "presentations", "pdf", "spreadsheet", "spreadsheet",
        "sheet", "sheets", "slide", "slides", "html", "doc", "docs",
    }
    terms = []
    # Prefer longer, more distinctive terms first.
    for token in sorted(set(raw_tokens), key=lambda x: (-len(x), x)):
        if token in generic or len(token) < 2:
            continue
        if token not in terms:
            terms.append(token)
    return terms[:5]


def _normalise_drive_name(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"^\s*(?:the|a|an|my)\s+", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def resolve_drive_folder(creds, description: str, max_results: int = 20) -> list[dict]:
    """Resolve a human folder name, preferring an exact folder-name match.

    This avoids the common case where asking for the "AI" folder also matches
    another folder such as "GenAI". No write is performed here.
    """
    description = (description or "").strip()
    if not description:
        return []

    candidates = [
        f for f in find_drive_files_by_name(creds, description, max_results=max_results)
        if f.get("mimeType") == "application/vnd.google-apps.folder"
    ]
    wanted = _normalise_drive_name(description)

    exact = [
        f for f in candidates
        if _normalise_drive_name(f.get("name", "")) == wanted
    ]
    if exact:
        return exact[:max_results]

    # If there was no exact folder, fall back to the broader metadata match.
    return candidates[:max_results]


def resolve_drive_file(creds, description: str, max_results: int = 20) -> list[dict]:
    """Resolve a human description to likely Drive files, ranked by name.

    This is metadata-only. It never changes Drive. The caller still requires
    explicit confirmation before invoking move_drive_file().

    Resolution order:
      1. exact filename (case-insensitive)
      2. exact filename stem
      3. distinctive token overlap, e.g. "CP4I presentation" ->
         "cp4i_escalation_presentation (1).html"
      4. substring/phrase match

    Generic words such as "presentation" are not allowed to create a false
    match by themselves.
    """
    service = _drive_service(creds)
    description = (description or "").strip()
    if not description:
        return []

    normal_description = _normalise_drive_name(description)

    # First try the user's phrase as-is. This preserves exact filename
    # matching when the user gives the complete name.
    exact = find_drive_files_by_name(creds, description, max_results=max_results)
    files = list(exact)

    # If the phrase was too natural-language-heavy, search using distinctive
    # terms. This is the important fallback for requests such as
    # "the CP4I presentation".
    terms = _drive_name_terms(description)
    if terms:
        clauses = []
        for term in terms:
            safe = term.replace("\\", "\\\\").replace("'", "\\'")
            clauses.append(f"name contains '{safe}'")
        q = f"({' or '.join(clauses)}) and trashed = false"
        resp = (
            service.files()
            .list(
                q=q,
                pageSize=max_results,
                fields="files(id,name,mimeType,modifiedTime,webViewLink,parents)",
                orderBy="modifiedTime desc",
            )
            .execute()
        )
        known_ids = {f.get("id") for f in files}
        for f in resp.get("files", []):
            if f.get("id") not in known_ids:
                files.append(f)

    def stem(name: str) -> str:
        return re.sub(r"\.[a-z0-9]{1,8}$", "", _normalise_drive_name(name))

    def meaningful_tokens(value: str) -> set[str]:
        toks = set(re.findall(r"[a-z0-9]+", _normalise_drive_name(value)))
        return {
            t for t in toks
            if t not in {
                "the", "a", "an", "my", "file", "files", "document",
                "documents", "presentation", "presentations", "pdf",
                "spreadsheet", "sheet", "sheets", "slide", "slides",
                "html", "doc", "docs"
            }
        }

    wanted = meaningful_tokens(description)
    wanted_stem = stem(description)

    ranked = []
    for f in files:
        name = f.get("name", "")
        n = _normalise_drive_name(name)
        s = stem(name)
        tokens = meaningful_tokens(name)
        score = 0.0

        if n == normal_description:
            score += 1000
        if s == wanted_stem:
            score += 900

        overlap = len(wanted & tokens)
        if wanted:
            score += 100 * (overlap / len(wanted))

        # Prefer candidates containing the distinctive description as a
        # contiguous phrase, but do not require it.
        if normal_description and normal_description in n:
            score += 150

        # For "CP4I presentation", CP4I is the distinctive token and a
        # candidate named cp4i_escalation_presentation should rank highly.
        if terms:
            term_hits = sum(1 for t in terms if t in n)
            score += 25 * term_hits

        # Penalise a candidate that only matches a generic word.
        if not wanted and score < 1000:
            score = -1

        ranked.append((score, f))

    ranked.sort(key=lambda item: (item[0], item[1].get("modifiedTime", "")), reverse=True)

    # If we have an exact filename/stem match, do not let weaker token
    # matches turn a clearly identified file into a false "multiple files"
    # result. For natural descriptions such as "CP4I presentation", similarly
    # keep only a clearly dominant candidate; otherwise preserve ties so the
    # caller can ask the user to disambiguate.
    supported = [(score, f) for score, f in ranked if score > 0]
    if not supported:
        return []

    top_score = supported[0][0]
    if top_score >= 900:
        return [supported[0][1]]

    if len(supported) > 1 and (top_score - supported[1][0]) >= 50:
        return [supported[0][1]]

    return [f for _, f in supported[:max_results]]


def move_drive_file(creds, file_id: str, destination_folder_id: str) -> dict:
    """Move one existing Drive file into a destination folder.

    This is the only Drive write operation currently exposed. The caller is
    responsible for obtaining explicit user confirmation before invoking it.
    """
    service = _drive_service(creds)
    current = (
        service.files()
        .get(fileId=file_id, fields="id,name,parents,webViewLink,mimeType")
        .execute()
    )
    old_parents = ",".join(current.get("parents", []))
    params = {
        "addParents": destination_folder_id,
        "fields": "id,name,parents,webViewLink,mimeType",
    }
    if old_parents:
        params["removeParents"] = old_parents

    return (
        service.files()
        .update(fileId=file_id, body={}, **params)
        .execute()
    )
