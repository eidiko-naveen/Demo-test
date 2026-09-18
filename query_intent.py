"""
query_intent.py
----------------
Deterministic (regex-based) helpers used to figure out what a user's
query is actually asking for, WITHOUT depending on Claude to get it
right.

Why this exists:
  Claude's keyword extraction is good at generating spelling variants
  for document names ("Aadhaar" / "Aadhar") but is an unreliable judge
  of "is there a person's name in this query, and did that person send
  me mail?" — it has no way to check that against the user's actual
  inbox. So person-name detection and gmail-vs-drive routing are done
  here in plain Python first. Claude's own intent guess (see
  claude_client.extract_query_intent) is used only as a secondary
  signal when these regexes find nothing.

Nothing in this module makes network calls or touches Google/Claude —
it's pure text processing over the user's own typed query.
"""

import re

# Common filler words that occasionally get captured by the patterns
# below and should never be treated as a person's name.
_STOPWORDS = {
    "me", "my", "any", "the", "a", "an", "this", "that", "today",
    "yesterday", "gmail", "drive", "email", "emails", "mail", "mails",
    "about", "regarding", "recent", "last", "new", "old", "all",
    "some", "sent", "send", "sending", "has", "have", "did", "does",
    "her", "him", "them", "us", "please", "can", "could",
}

# Ordered so the more specific / reliable patterns run first.
_PERSON_PATTERNS = [
    # Direct email-address queries: "emails from jeevan@example.com"
    re.compile(r"\bfrom\s+([\w.\-+]+@[\w.\-]+)\b", re.IGNORECASE),
    # "emails from Jeevan", "mail from Abhay", "show mails from Sumith",
    # "emails about deployment from Jaina"
    re.compile(r"\bfrom\s+([a-zA-Z][a-zA-Z'\-]{1,25})\b", re.IGNORECASE),
    # "sent by Abhay", "shared by Jaina"
    re.compile(r"\bby\s+([a-zA-Z][a-zA-Z'\-]{1,25})\b", re.IGNORECASE),
    # "did jeevan send me any mail", "has abhay emailed me", "does sumith have mail"
    re.compile(
        r"\b(?:did|does|has|have)\s+([a-zA-Z][a-zA-Z'\-]{1,25})\s+"
        r"(?:sent|send|mail|email|emailed|write|wrote)\b",
        re.IGNORECASE,
    ),
    # Calendar/event queries: "meeting with Abhay", "event with Jeevan"
    re.compile(
        r"\b(?:meeting|meet|event|appointment|call)\s+(?:with|for)\s+"
        r"([a-zA-Z][a-zA-Z'\-]{1,25})\b",
        re.IGNORECASE,
    ),
    # "jeevan sent me", "abhay emailed me"
    re.compile(
        r"\b([a-zA-Z][a-zA-Z'\-]{1,25})\s+(?:sent|send|emailed|wrote)\s+me\b",
        re.IGNORECASE,
    ),
]

# Words that hint the user wants Gmail results.
_CALENDAR_HINTS = {
    "calendar", "calendars", "meeting", "meetings", "event", "events",
    "appointment", "appointments", "schedule", "scheduled", "agenda",
    "invite", "invitation", "google meet",
}

_GMAIL_HINTS = {
    "email", "emails", "mail", "mails", "inbox", "sent", "message",
    "messages", "wrote", "reply", "replied",
}

# Words that hint the user wants Drive results.
_DRIVE_HINTS = {
    "drive", "document", "documents", "doc", "docs", "file", "files",
    "folder", "presentation", "spreadsheet", "sheet", "slide", "slides",
    "pdf", "pan", "aadhaar", "aadhar", "card", "id", "photo", "image",
    "scan", "copy",
}


def extract_person_candidate(query: str) -> str | None:
    """Returns a best-guess person name mentioned in the query, or None.

    Deliberately conservative: only fires on a handful of common English
    phrasings ("from X", "by X", "did X send...", "X sent me..."). If
    none match, returns None rather than guessing — callers should treat
    that as "no deterministic candidate", not "no person in the query".
    """
    query = (query or "").strip()
    for pattern in _PERSON_PATTERNS:
        match = pattern.search(query)
        if not match:
            continue
        candidate = match.group(1).strip().strip("'-")
        if len(candidate) < 2:
            continue
        if candidate.lower() in _STOPWORDS:
            continue
        # Preserve an email address exactly enough for Gmail's from: query.
        if "@" in candidate:
            return candidate.lower()
        return candidate
    return None


def classify_target(query: str) -> str:
    """Returns gmail, drive, calendar, or both/combined source routing.

    Calendar words are checked first so "calendar meeting" does not get
    misrouted as a generic Gmail/Drive query.
    """
    text = (query or "").lower()
    words = set(re.findall(r"[a-zA-Z']+", text))
    has_calendar = bool(words & _CALENDAR_HINTS) or "google meet" in text
    has_gmail = bool(words & _GMAIL_HINTS)
    has_drive = bool(words & _DRIVE_HINTS)

    targets = sum([has_calendar, has_gmail, has_drive])
    if targets == 0:
        return "both"
    if targets == 1:
        if has_calendar:
            return "calendar"
        if has_gmail:
            return "gmail"
        return "drive"
    # Explicitly mentioning multiple source types means search them all.
    return "both"
