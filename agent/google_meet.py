"""Create Google Calendar events with automatically generated Meet links."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from agent.config import get_settings
from agent.logger import get_logger

log = get_logger(__name__)
cfg = get_settings()

_TOKEN_URI = "https://oauth2.googleapis.com/token"
_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class GoogleMeetDispatchError(RuntimeError):
    """Raised when authentication or Calendar event creation fails."""


def _get_credentials():
    """Build and refresh OAuth credentials without storing an access token."""
    if not all(
        [cfg.google_client_id, cfg.google_client_secret, cfg.google_refresh_token]
    ):
        raise GoogleMeetDispatchError(
            "Google Calendar credentials are incomplete; configure "
            "GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN."
        )

    try:
        from google.auth.transport.requests import Request as GoogleAuthRequest
        from google.oauth2.credentials import Credentials

        credentials = Credentials(
            token=None,
            refresh_token=cfg.google_refresh_token,
            token_uri=_TOKEN_URI,
            client_id=cfg.google_client_id,
            client_secret=cfg.google_client_secret,
            scopes=_SCOPES,
        )
        credentials.refresh(GoogleAuthRequest())
        return credentials
    except ImportError as exc:
        raise GoogleMeetDispatchError(
            "Google Meet dependencies are not installed; run pip install -r requirements.txt"
        ) from exc
    except Exception as exc:
        raise GoogleMeetDispatchError(f"Google OAuth token refresh failed: {exc}") from exc


def _build_event_body(
    subject: str,
    body_text: str,
    attendees: List[str],
    duration_minutes: int,
) -> Dict[str, Any]:
    start = datetime.now(timezone.utc) + timedelta(minutes=2)
    end = start + timedelta(minutes=duration_minutes)
    return {
        "summary": subject,
        "description": body_text,
        "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
        "attendees": [{"email": address} for address in attendees],
        "conferenceData": {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
    }


def schedule_meeting(
    subject: str,
    body_text: str,
    attendees: List[str],
    duration_minutes: Optional[int] = None,
) -> Dict[str, Any]:
    """Create an event, email attendees, and return its event ID and Meet URL."""
    attendees = list(dict.fromkeys(address.strip() for address in attendees if address.strip()))
    if not attendees:
        raise GoogleMeetDispatchError("Cannot schedule a meeting without attendees.")

    duration = duration_minutes or cfg.escalation_meeting_duration_minutes
    credentials = _get_credentials()
    event_body = _build_event_body(subject, body_text, attendees, duration)

    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError

        service = build("calendar", "v3", credentials=credentials, cache_discovery=False)
        event = (
            service.events()
            .insert(
                calendarId=cfg.google_calendar_id,
                body=event_body,
                conferenceDataVersion=1,
                sendUpdates="all",
            )
            .execute()
        )
    except ImportError as exc:
        raise GoogleMeetDispatchError(
            "Google Meet dependencies are not installed; run pip install -r requirements.txt"
        ) from exc
    except HttpError as exc:
        raise GoogleMeetDispatchError(f"Google Calendar API error: {exc}") from exc
    except Exception as exc:
        raise GoogleMeetDispatchError(f"Google Calendar event creation failed: {exc}") from exc

    join_url = event.get("hangoutLink", "")
    if not join_url:
        for entry_point in event.get("conferenceData", {}).get("entryPoints", []):
            if entry_point.get("entryPointType") == "video":
                join_url = entry_point.get("uri", "")
                break

    result = {
        "event_id": event.get("id", ""),
        "join_url": join_url,
        "attendees": attendees,
    }
    log.info("google_meet_created", **result)
    return result
