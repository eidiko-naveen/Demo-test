"""
google_client.py — EIDIKO Chatbot
------------------------------------
Read-only Google OAuth + Gmail + Drive + Calendar.

Fixes in this version:
- Added get_past_events()       for "past / completed events" queries
- Added get_recent_drive_files() for "recently uploaded files" queries
- get_calendar_events() now supports time_filter="past_week"/"past_month"
  by setting timeMax=now and timeMin=N days ago (reverse time range)
- Drive search now also supports fullText search in addition to name search
- orderBy for Drive defaults to modifiedTime desc so recent files come first
"""

import os
import base64
from pathlib import Path
from datetime import datetime, timedelta, timezone

os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build


# ============================================================
# PATHS & SCOPES
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = str(BASE_DIR / "credentials" / "credentials.json")
TOKEN_FILE = str(BASE_DIR / "token.json")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

_pending_flows: dict = {}
_FLOW_TTL_SECONDS = 600


def _evict_stale_flows():
    now = datetime.now(timezone.utc).timestamp()
    stale = [k for k, (_, ts) in _pending_flows.items()
             if now - ts > _FLOW_TTL_SECONDS]
    for k in stale:
        del _pending_flows[k]


# ============================================================
# AUTHENTICATION
# ============================================================

def is_authenticated() -> bool:
    try:
        return get_credentials() is not None
    except Exception:
        return False


def get_credentials():
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        credentials = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    except Exception:
        return None
    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(credentials.to_json())
        except Exception:
            return None
    return credentials if credentials.valid else None


def build_auth_url(redirect_uri: str) -> str:
    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError(
            f"Google credentials file not found: {CREDENTIALS_FILE}"
        )
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE, scopes=SCOPES, redirect_uri=redirect_uri
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    _evict_stale_flows()
    _pending_flows[state] = (flow, datetime.now(timezone.utc).timestamp())
    return auth_url


def finish_auth_flow(state: str, authorization_response_url: str):
    if not state:
        raise ValueError("Missing OAuth state.")
    _evict_stale_flows()
    entry = _pending_flows.pop(state, None)
    if entry is None:
        raise ValueError("OAuth session expired. Click Connect Google again.")
    flow, _ = entry
    flow.fetch_token(authorization_response=authorization_response_url)
    credentials = flow.credentials
    if not credentials or not credentials.valid:
        raise RuntimeError("Google returned invalid credentials.")
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(credentials.to_json())
    return credentials


def disconnect():
    credentials = get_credentials()
    if credentials:
        token = credentials.token or credentials.refresh_token
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
                pass
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)


# ============================================================
# SERVICE BUILDERS
# ============================================================

def _gmail_service(credentials):
    if credentials is None:
        raise RuntimeError("Google credentials are missing.")
    return build("gmail", "v1", credentials=credentials)


def _drive_service(credentials):
    if credentials is None:
        raise RuntimeError("Google credentials are missing.")
    return build("drive", "v3", credentials=credentials)


def _calendar_service(credentials):
    if credentials is None:
        raise RuntimeError("Google credentials are missing.")
    return build("calendar", "v3", credentials=credentials)


# ============================================================
# DATE HELPERS
# ============================================================

def _now() -> datetime:
    return datetime.now().astimezone()


def _date_str(days_offset: int = 0) -> str:
    d = _now().date() + timedelta(days=days_offset)
    return d.strftime("%Y/%m/%d")


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _gmail_date_filter(time_filter: str) -> str:
    if time_filter == "today":
        return f"after:{_date_str(0)} before:{_date_str(1)}"
    elif time_filter == "yesterday":
        return f"after:{_date_str(-1)} before:{_date_str(0)}"
    elif time_filter in ("this_week", "past_week"):
        return f"after:{_date_str(-7)}"
    elif time_filter in ("this_month", "past_month"):
        return f"after:{_date_str(-30)}"
    return ""


# ============================================================
# GMAIL
# ============================================================

def _extract_attachments(payload: dict) -> list[dict]:
    attachments = []

    def walk(part):
        body = part.get("body", {}) or {}
        filename = part.get("filename", "")
        if filename and body.get("attachmentId"):
            attachments.append({
                "filename": filename,
                "attachment_id": body["attachmentId"],
                "mime_type": part.get("mimeType", "application/octet-stream"),
                "size": body.get("size", 0),
            })
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload)
    return attachments


def _fetch_message_metadata(service, message_id: str) -> dict:
    msg = (
        service.users().messages().get(
            userId="me", id=message_id, format="metadata",
            metadataHeaders=["Subject", "From", "To", "Date"],
        ).execute()
    )
    headers = {
        h["name"].lower(): h["value"]
        for h in msg.get("payload", {}).get("headers", [])
    }
    return {
        "source": "gmail",
        "id": message_id,
        "subject": headers.get("subject", "(no subject)"),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "date": headers.get("date", ""),
        "snippet": msg.get("snippet", ""),
        "link": f"https://mail.google.com/mail/u/0/#all/{message_id}",
        "attachments": [],
    }


def _fetch_message_full(service, message_id: str) -> dict:
    msg = (
        service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
    )
    headers = {
        h["name"].lower(): h["value"]
        for h in msg.get("payload", {}).get("headers", [])
    }
    return {
        "source": "gmail",
        "id": message_id,
        "subject": headers.get("subject", "(no subject)"),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "date": headers.get("date", ""),
        "snippet": msg.get("snippet", ""),
        "link": f"https://mail.google.com/mail/u/0/#all/{message_id}",
        "attachments": _extract_attachments(msg.get("payload", {})),
    }


def get_recent_emails(credentials, gmail_query: str = "",
                      time_filter: str = "today", max_results: int = 10) -> list[dict]:
    service = _gmail_service(credentials)
    date_clause = _gmail_date_filter(time_filter)
    parts = [p for p in [date_clause, gmail_query.strip()] if p]
    query = " ".join(parts).strip() or "in:inbox"
    response = (
        service.users().messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    return [_fetch_message_metadata(service, item["id"])
            for item in response.get("messages", [])]


def search_gmail(credentials, keywords, gmail_query: str = "",
                 time_filter: str = "all", max_results: int = 20,
                 fetch_attachments: bool = True) -> list[dict]:
    service = _gmail_service(credentials)
    if isinstance(keywords, str):
        keywords = [keywords]
    keywords = [str(k).strip() for k in keywords if str(k).strip()]
    parts = []
    if keywords:
        parts.append(" OR ".join(keywords))
    if gmail_query.strip():
        parts.append(gmail_query.strip())
    date_clause = _gmail_date_filter(time_filter)
    if date_clause:
        parts.append(date_clause)
    query = " ".join(parts).strip()
    if not query:
        return []
    response = (
        service.users().messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    fetcher = _fetch_message_full if fetch_attachments else _fetch_message_metadata
    return [fetcher(service, item["id"]) for item in response.get("messages", [])]


def count_emails(credentials, time_filter: str = "today") -> int:
    service = _gmail_service(credentials)
    date_clause = _gmail_date_filter(time_filter)
    query = date_clause or "in:inbox"
    total = 0
    page_token = None
    while True:
        kwargs = {"userId": "me", "q": query, "maxResults": 500}
        if page_token:
            kwargs["pageToken"] = page_token
        response = service.users().messages().list(**kwargs).execute()
        total += len(response.get("messages", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return total


def get_attachment_bytes(credentials, message_id: str, attachment_id: str) -> bytes:
    service = _gmail_service(credentials)
    response = (
        service.users().messages().attachments()
        .get(userId="me", messageId=message_id, id=attachment_id)
        .execute()
    )
    data = response.get("data", "")
    return base64.urlsafe_b64decode(data.encode("utf-8"))


# ============================================================
# GOOGLE DRIVE
# ============================================================

def search_drive(credentials, keywords, max_results: int = 20) -> list[dict]:
    """Search Drive by filename keywords."""
    service = _drive_service(credentials)
    if isinstance(keywords, str):
        keywords = [keywords]
    keywords = [str(k).strip() for k in keywords if str(k).strip()]
    if not keywords:
        return []
    clauses = [
        f"(name contains '{k}' or fullText contains '{k}')"
        for k in keywords
    ]
    query = "(" + " or ".join(clauses) + ") and trashed = false"
    response = (
        service.files().list(
            q=query,
            pageSize=max_results,
            fields="files(id,name,mimeType,modifiedTime,webViewLink,createdTime)",
            orderBy="modifiedTime desc",
        ).execute()
    )
    return [_format_drive_file(f) for f in response.get("files", [])]


def get_recent_drive_files(credentials, max_results: int = 20,
                           days: int = 30) -> list[dict]:
    """
    NEW — fetch recently modified/created Drive files.
    Used for 'recently uploaded files', 'new files in drive', etc.
    """
    service = _drive_service(credentials)
    since = (_now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    query = (
        f"(modifiedTime > '{since}' or createdTime > '{since}') "
        f"and trashed = false"
    )
    response = (
        service.files().list(
            q=query,
            pageSize=max_results,
            fields="files(id,name,mimeType,modifiedTime,webViewLink,createdTime)",
            orderBy="modifiedTime desc",
        ).execute()
    )
    return [_format_drive_file(f) for f in response.get("files", [])]


def _format_drive_file(file: dict) -> dict:
    return {
        "source": "drive",
        "id": file.get("id", ""),
        "name": file.get("name", ""),
        "mime_type": file.get("mimeType", ""),
        "modified": file.get("modifiedTime", ""),
        "created": file.get("createdTime", ""),
        "link": file.get(
            "webViewLink",
            f"https://drive.google.com/open?id={file.get('id', '')}",
        ),
    }


# ============================================================
# GOOGLE CALENDAR
# ============================================================

def get_calendar_events(credentials, query: str = "",
                        time_filter: str = "upcoming",
                        max_results: int = 20) -> list[dict]:
    """
    Flexible calendar fetch supporting past, today, and upcoming.

    time_filter values:
        today      - events today only
        upcoming   - from now onward (future)
        past_week  - events in the past 7 days (already happened)  ← NEW
        past_month - events in the past 30 days (already happened) ← NEW
        all        - no time filter
    """
    service = _calendar_service(credentials)
    now = _now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    params: dict = {
        "calendarId": "primary",
        "singleEvents": True,
        "maxResults": max_results,
    }

    if query:
        params["q"] = query

    if time_filter == "today":
        params["timeMin"] = _iso(today_start)
        params["timeMax"] = _iso(today_end)
        params["orderBy"] = "startTime"

    elif time_filter == "upcoming":
        params["timeMin"] = _iso(now)
        params["orderBy"] = "startTime"

    elif time_filter == "past_week":
        # Events that have ALREADY ENDED in the last 7 days
        params["timeMin"] = _iso(now - timedelta(days=7))
        params["timeMax"] = _iso(now)
        params["orderBy"] = "startTime"

    elif time_filter == "past_month":
        params["timeMin"] = _iso(now - timedelta(days=30))
        params["timeMax"] = _iso(now)
        params["orderBy"] = "startTime"

    else:
        # "all" — no time bounds; use updated ordering
        params["orderBy"] = "updated"

    response = service.events().list(**params).execute()

    results = []
    for event in response.get("items", []):
        start_data = event.get("start", {})
        end_data = event.get("end", {})
        start = start_data.get("dateTime") or start_data.get("date") or ""
        end = end_data.get("dateTime") or end_data.get("date") or ""
        results.append({
            "source": "calendar",
            "id": event.get("id", ""),
            "name": event.get("summary", "(no title)"),
            "description": event.get("description", ""),
            "start": start,
            "end": end,
            "location": event.get("location", ""),
            "link": event.get("htmlLink", "https://calendar.google.com/"),
            "organizer": event.get("organizer", {}).get("email", ""),
            "attendees": len(event.get("attendees", [])),
        })

    return results


def get_past_events(credentials, max_results: int = 20,
                    days: int = 7) -> list[dict]:
    """
    NEW convenience function for 'past events / completed meetings'.
    Returns events that ended before now, ordered newest first.
    """
    return get_calendar_events(
        credentials,
        time_filter="past_week" if days <= 7 else "past_month",
        max_results=max_results,
    )


# Backward-compat aliases
def get_upcoming_events(credentials, max_results: int = 20) -> list[dict]:
    return get_calendar_events(credentials, time_filter="upcoming",
                               max_results=max_results)


def search_calendar(credentials, query: str = "", max_results: int = 20,
                    upcoming_only: bool = False) -> list[dict]:
    tf = "upcoming" if upcoming_only else "all"
    return get_calendar_events(credentials, query=query,
                               time_filter=tf, max_results=max_results)