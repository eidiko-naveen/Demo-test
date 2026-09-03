"""
claude_client.py — EIDIKO Chatbot
----------------------------------
Claude API calls: intent classification, keyword extraction, summarization.

Fixes in this version:
- Added  calendar_past   intent for "past events / completed meetings"
- Added  drive_recent    intent for "recently uploaded / latest Drive files"
- Added  past_week / past_month  time filters for backward queries
- Tightened system prompt rules so Claude never falls back to "upcoming"
  when the user clearly asked for history
- Fixed markdown fence stripping (lstrip was too greedy)
"""

import os
import json
from anthropic import Anthropic

MODEL = "claude-sonnet-4-6"

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        _client = Anthropic(api_key=api_key)
    return _client


def _extract_text(resp) -> str:
    parts = [block.text for block in resp.content if block.type == "text"]
    return "".join(parts).strip()


def _strip_fences(text: str) -> str:
    """Remove markdown code fences Claude sometimes adds."""
    text = text.strip()
    if text.startswith("```"):
        # remove opening fence line
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


# ============================================================
# INTENT CLASSIFICATION
# ============================================================

_INTENT_SYSTEM_PROMPT = """\
You are an intent classifier for a personal workspace assistant connected
to Gmail, Google Drive and Google Calendar.

TODAY's date is injected at call time as {{TODAY}}.

INTENT VALUES — pick exactly one:

  gmail_recent      - show latest/new/unread/recent emails (no specific topic)
  gmail_count       - count emails in a time period
  gmail_search      - search for a specific email, sender, subject, attachment
  drive_search      - search Drive for a specific file/document by name or topic
  drive_recent      - list recently uploaded/modified files in Drive (no specific name)
  calendar_today    - list events for today only
  calendar_upcoming - list future/upcoming events (from now onward)
  calendar_past     - list PAST/completed/previous events or meetings
  calendar_search   - search calendar for a specific event/meeting/topic
  multi_search      - query spans more than one source
  unknown           - cannot map to any of the above

TIME FILTER VALUES — pick one:
  today | yesterday | this_week | this_month | past_week | past_month | all

  Use past_week / past_month for queries about things that already happened.
  Use today / this_week / this_month for things happening now or in future.

SOURCES — list all that apply from: "gmail", "drive", "calendar"

FIELD DEFINITIONS:
  gmail_query    : Ready-to-use Gmail API search string. Use operators like
                   from:x, subject:x, has:attachment, after:YYYY/MM/DD.
                   Empty string = no extra filter (date filter added by app).
  drive_query    : Keywords for Drive filename/fulltext search. Empty = recent files.
  calendar_query : Keywords for Calendar event search. Empty = list all events.
  max_results    : Integer. 5 for quick lookup, 10 default, 20 for broad queries.
  reply_hint     : Short phrase (5-10 words) describing what we're fetching.

STRICT RULES — follow exactly:
1. Reply ONLY with a valid JSON object. No markdown, no explanation.
2. "past events", "completed meetings", "previous events", "what happened",
   "events that are done", "history" → intent MUST be calendar_past,
   time_filter MUST be past_week or past_month. NEVER return calendar_upcoming.
3. "recent files", "latest uploads", "recently added", "new files in drive",
   "files uploaded recently" → intent MUST be drive_recent, drive_query = "".
4. "today's meetings", "meetings today", "events today" → calendar_today.
5. "upcoming", "next meeting", "future events" → calendar_upcoming.
6. "what meetings do I have" with no time word → calendar_upcoming.
7. For calendar_past: do NOT set timeMin in calendar_query — the app handles it.
8. For drive_recent: do NOT put keywords in drive_query — leave it empty.
   The app will sort Drive by modifiedTime desc automatically.

EXAMPLE OUTPUTS:

Query: "what are the past events that are completed"
{
  "intent": "calendar_past",
  "sources": ["calendar"],
  "gmail_query": "",
  "drive_query": "",
  "calendar_query": "",
  "time_filter": "past_week",
  "max_results": 10,
  "reply_hint": "your past and completed events"
}

Query: "what are the files which are uploaded recently in google drive"
{
  "intent": "drive_recent",
  "sources": ["drive"],
  "gmail_query": "",
  "drive_query": "",
  "calendar_query": "",
  "time_filter": "this_week",
  "max_results": 10,
  "reply_hint": "recently uploaded files in Drive"
}

Query: "what meetings do I have today"
{
  "intent": "calendar_today",
  "sources": ["calendar"],
  "gmail_query": "",
  "drive_query": "",
  "calendar_query": "",
  "time_filter": "today",
  "max_results": 10,
  "reply_hint": "your meetings for today"
}

Query: "what were the past events"
{
  "intent": "calendar_past",
  "sources": ["calendar"],
  "gmail_query": "",
  "drive_query": "",
  "calendar_query": "",
  "time_filter": "past_week",
  "max_results": 10,
  "reply_hint": "your recent past events"
}
"""


def classify_intent(user_query: str) -> dict:
    """
    Use Claude to classify intent. Returns a structured routing dict.
    Falls back to a safe gmail_search default if parsing fails.
    """
    from datetime import date
    today_str = date.today().strftime("%Y-%m-%d")

    client = _get_client()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=400,
        system=_INTENT_SYSTEM_PROMPT.replace("{{TODAY}}", today_str),
        messages=[{"role": "user", "content": user_query}],
    )
    text = _strip_fences(_extract_text(resp))

    try:
        result = json.loads(text)
        result.setdefault("intent", "unknown")
        result.setdefault("sources", ["gmail"])
        result.setdefault("gmail_query", "")
        result.setdefault("drive_query", "")
        result.setdefault("calendar_query", "")
        result.setdefault("time_filter", "all")
        result.setdefault("max_results", 10)
        result.setdefault("reply_hint", "your search results")
        return result
    except (json.JSONDecodeError, AttributeError):
        return {
            "intent": "gmail_search",
            "sources": ["gmail"],
            "gmail_query": user_query,
            "drive_query": user_query,
            "calendar_query": user_query,
            "time_filter": "all",
            "max_results": 10,
            "reply_hint": "results matching your query",
        }


# ============================================================
# KEYWORD EXTRACTION
# ============================================================

def extract_keywords(user_query: str) -> list[str]:
    """Turn a user query into 2-5 search keywords."""
    client = _get_client()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=200,
        system=(
            "You turn a user's short request into 2-5 search terms for "
            "searching their Gmail/Drive by subject or filename. "
            "Include distinctive nouns AND common spelling variants. "
            "Avoid generic filler words on their own. "
            "Reply with ONLY a JSON array of strings, nothing else. "
            'Example: ["Aadhaar", "Aadhar", "Aadhaar card"]'
        ),
        messages=[{"role": "user", "content": user_query}],
    )
    text = _strip_fences(_extract_text(resp))
    try:
        keywords = json.loads(text)
        if isinstance(keywords, list) and all(isinstance(k, str) for k in keywords):
            return keywords[:5]
    except (json.JSONDecodeError, IndexError):
        pass
    return [user_query]


# ============================================================
# RESULT SUMMARIZATION
# ============================================================

_SUMMARY_SYSTEM_PROMPT = """\
You help a user find their emails, files and calendar events.

You receive a JSON array of search results, each with an "index".
All snippets are already redacted of sensitive numbers.

Rules:
- NEVER output digit sequences longer than 3.
- Keep reply to 1-3 short sentences.
- Separate genuine matches from noise.
- If nothing matches, say so and return empty list.
- Be conversational and helpful.

Reply ONLY with this JSON — no markdown, no extra text:
{"reply": "<short summary>", "relevant_indices": [<matching index values>]}
"""


def summarize_results(user_query: str, results: list[dict]) -> dict:
    """Returns {"reply": str, "relevant_indices": list[int]}."""
    indexed = [{"index": i, **r} for i, r in enumerate(results)]
    client = _get_client()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=500,
        system=_SUMMARY_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"User's request: {user_query!r}\n\n"
                    f"Results (JSON): {json.dumps(indexed)}"
                ),
            }
        ],
    )
    text = _strip_fences(_extract_text(resp))
    try:
        parsed = json.loads(text)
        reply = parsed.get("reply", "").strip()
        relevant = parsed.get("relevant_indices")
        if reply and isinstance(relevant, list):
            valid = set(range(len(results)))
            return {
                "reply": reply,
                "relevant_indices": [i for i in relevant if i in valid],
            }
    except (json.JSONDecodeError, AttributeError):
        pass
    return {
        "reply": text or "Here's what I found.",
        "relevant_indices": list(range(len(results))),
    }