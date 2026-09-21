"""
claude_client.py
-----------------
Two small, narrowly-scoped Claude API calls:

1. extract_keywords()  - turn a free-text user query into a few search
   keywords (e.g. "find my PAN card" -> ["PAN", "PAN card", "Permanent
   Account Number"]). No account data is sent for this call.

2. summarize_results()  - given ALREADY-REDACTED metadata (subjects,
   filenames, snippets with any ID/secret-looking text masked by
   redact.py), produce a short human summary pointing the user at the
   right link. The system prompt explicitly forbids repeating any
   number/secret-looking token even if one slipped through redaction.
"""

import os
import json
from anthropic import Anthropic

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set. See .env.example.")
        _client = Anthropic(api_key=api_key)
    return _client


def _extract_text(resp) -> str:
    """Pulls the text out of a Claude response. Response content can
    include non-text blocks first (e.g. a ThinkingBlock) — never assume
    content[0] is the text block, scan for the actual text block(s)."""
    parts = [block.text for block in resp.content if block.type == "text"]
    return "".join(parts).strip()


def extract_keywords(user_query: str) -> list[str]:
    client = _get_client()
    resp = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=200,
        system=(
            "You turn a user's short request into 2-5 search terms for "
            "searching their own Gmail/Drive by subject or filename. "
            "Include distinctive nouns as standalone terms (e.g. 'Aadhaar', "
            "'PAN') AND common real-world spelling variants of them (e.g. "
            "Aadhaar is very often written 'Aadhar' in India — include both "
            "spellings as separate terms). Avoid generic words alone that "
            "match far too much unrelated mail — 'card', 'ID', 'number', "
            "'document' should only appear as part of a specific phrase "
            "like 'Aadhaar card', never as a standalone term. "
            "Reply with ONLY a JSON array of strings, nothing else. "
            "Example: [\"Aadhaar\", \"Aadhar\", \"Aadhaar card\", \"Aadhar card\"]"
        ),
        messages=[{"role": "user", "content": user_query}],
    )
    text = _extract_text(resp)
    try:
        keywords = json.loads(text)
        if isinstance(keywords, list) and all(isinstance(k, str) for k in keywords):
            return keywords[:5]
    except (json.JSONDecodeError, IndexError):
        pass
    # Fallback: just use the raw query as a single keyword.
    return [user_query]


_INTENT_SYSTEM_PROMPT = """\
You analyze a user's request to find something in their own Gmail/Drive.

Reply with ONLY a JSON object, nothing else, with these fields:
{
  "person": <string or null>,
  "keywords": [<2-5 search terms as strings>],
  "target": "gmail" | "drive" | "calendar" | "both"
}

Rules:
- "person": the name of a person the user is asking about (e.g. a
  sender), or null if no person is mentioned. Only the bare name, e.g.
  "Jeevan" not "from Jeevan".
- "keywords": search terms for subject/filename/body matching. Include
  distinctive nouns as standalone terms AND common real-world spelling
  variants (e.g. Aadhaar is very often written "Aadhar" in India —
  include both as separate terms). Avoid generic words alone that match
  far too much unrelated mail ("card", "ID", "number", "document")
  unless part of a specific phrase like "Aadhaar card". If the query is
  purely about a person with no topic (e.g. "did Jeevan send me any
  mail"), keywords can be an empty array.
- "target": "gmail" if the user is clearly asking about email/mail/messages/inbox;
  "drive" if clearly asking about a document/file/card/ID/presentation/spreadsheet;
  "calendar" if clearly asking about meetings/events/appointments/schedule/agenda;
  "both" if the request explicitly spans sources or is unclear.

Examples:
"did jeevan send me any mail" -> {"person": "Jeevan", "keywords": [], "target": "gmail"}
"find emails from Abhay about CP4I" -> {"person": "Abhay", "keywords": ["CP4I"], "target": "gmail"}
"find my pan card" -> {"person": null, "keywords": ["PAN", "PAN card"], "target": "drive"}
"aadhar card" -> {"person": null, "keywords": ["Aadhaar", "Aadhar", "Aadhaar card", "Aadhar card"], "target": "drive"}
"documents about CP4I in Drive" -> {"person": null, "keywords": ["CP4I"], "target": "drive"}
"find my emails about CP4I" -> {"person": null, "keywords": ["CP4I"], "target": "gmail"}
"what meetings do I have tomorrow" -> {"person": null, "keywords": [], "target": "calendar"}
"do I have a meeting with Abhay tomorrow" -> {"person": "Abhay", "keywords": [], "target": "calendar"}
"when is my CP4I meeting" -> {"person": null, "keywords": ["CP4I"], "target": "calendar"}
"""


def extract_query_intent(user_query: str) -> dict:
    """Richer version of extract_keywords(): also guesses a person name
    and which source (gmail/drive/both) the query is aimed at.

    This is ONE signal among several — app.py combines it with the
    deterministic regex-based guesses from query_intent.py, and never
    lets this call alone decide whether a person "exists" in the
    mailbox (that's verified against actual sender headers in
    google_client.py). If parsing fails, returns a safe default that
    searches both sources with the raw query as a keyword.
    """
    client = _get_client()
    resp = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=300,
        system=_INTENT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_query}],
    )
    text = _extract_text(resp)
    default = {"person": None, "keywords": [user_query], "target": "both"}
    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return default
        person = parsed.get("person")
        person = person.strip() if isinstance(person, str) and person.strip() else None
        keywords = parsed.get("keywords")
        if not isinstance(keywords, list) or not all(isinstance(k, str) for k in keywords):
            keywords = [user_query]
        target = parsed.get("target")
        if target not in ("gmail", "drive", "calendar", "both"):
            target = "both"
        return {"person": person, "keywords": keywords[:5], "target": target}
    except (json.JSONDecodeError, AttributeError):
        return default


_SUMMARY_SYSTEM_PROMPT = """\
You help a user locate their own emails, documents, and calendar events in Gmail, Drive, and Google Calendar.

You are given a JSON array of search results, each with an "index". Every
snippet/filename in that array has ALREADY been redacted of ID numbers,
card numbers, passwords, and similar secrets (masked as [REDACTED-...]).
The underlying search is a loose full-text match, so it often includes
results that share a common word but are NOT actually what the user
asked for (e.g. an insurance "e-card" email when they asked for their
Aadhaar card) — your job is to separate genuine matches from noise.

Some Gmail results carry a "sender_match": true field. That means the
application already deterministically verified (by matching the actual
From header, not by asking you) that this message is from the person
the user asked about — always keep these in relevant_indices, they are
confirmed, not a guess.

Rules, no exceptions:
- NEVER output any sequence of digits longer than 3, and never output
  anything that looks like an ID number, account number, password, PIN,
  or OTP, even if you believe you see one in the input — treat any such
  token as [REDACTED] and do not repeat it.
- Do not guess or reconstruct a redacted value.
- Keep the reply short: 1-3 sentences. Don't repeat raw links, the app
  shows those separately.
- If nothing genuinely matches, say so plainly and return an empty list.

Reply with ONLY a JSON object, nothing else:
{"reply": "<your short summary>", "relevant_indices": [<the "index" values of results that genuinely match, most relevant first>]}
"""


def summarize_results(user_query: str, results: list[dict], intent_context: str | None = None) -> dict:
    """Returns {"reply": str, "relevant_indices": list[int]}. Falls back to
    treating every result as relevant if Claude's output can't be parsed —
    erring toward showing more, never toward silently hiding a real match.

    intent_context is an optional short string (e.g. "Detected intent:
    person=Jeevan, target=gmail") describing what app.py's deterministic
    query-intent logic already figured out, so Claude's ranking agrees
    with — rather than second-guesses — that detection. Purely additive;
    omitting it preserves the previous behavior exactly."""
    indexed = [{"index": i, **r} for i, r in enumerate(results)]
    client = _get_client()
    user_content = (
        f"User's request: {user_query!r}\n\n"
        f"Redacted search results (JSON): {json.dumps(indexed)}"
    )
    if intent_context:
        user_content = f"{intent_context}\n\n{user_content}"
    resp = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=400,
        system=_SUMMARY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    text = _extract_text(resp)
    try:
        parsed = json.loads(text)
        reply = parsed.get("reply", "").strip()
        relevant = parsed.get("relevant_indices")
        if reply and isinstance(relevant, list):
            valid = {i for i in range(len(results))}
            return {"reply": reply, "relevant_indices": [i for i in relevant if i in valid]}
    except (json.JSONDecodeError, AttributeError):
        pass
    # Fallback: show everything rather than risk hiding a real match.
    return {"reply": text or "Here's what I found.", "relevant_indices": list(range(len(results)))}
