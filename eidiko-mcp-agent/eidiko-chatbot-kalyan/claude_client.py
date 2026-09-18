"""
claude_client.py
-----------------
NOTE: despite the filename (kept as-is so app.py and every other module
needed ZERO changes), this now calls Groq's API, not Anthropic's. This is
the ONLY file in the project that talks to the LLM provider — swapping
providers again in the future only ever means editing this one file plus
GROQ_API_KEY in .env / requirements.txt.

Four narrowly-scoped calls, each given only what it needs and nothing more:

1. extract_keywords()        - turn a free-text query into 2-5 search
   terms. No account data is sent for this call — just your own typed
   question.
2. summarize_results()       - given ALREADY-REDACTED Gmail/Drive result
   metadata (subjects, filenames, snippets with any ID/secret-looking
   text masked by redact.py), rank + summarize in plain English.
3. summarize_sheet_preview() - given an already-redacted preview of a
   Sheet's rows, answer a question about its content.
4. extract_write_action()    - parse a write request ("send an email to
   X", "create a meeting on...") into a structured, confirmable action.
   Never executes anything itself.

Every system prompt below explicitly forbids repeating any number/secret-
looking token even if one slipped through redaction — that instruction is
provider-agnostic and stays true regardless of which model answers it.
"""

import os
import json
from datetime import datetime
from groq import Groq

# Any Groq-hosted model works here — see https://console.groq.com/docs/models
# for the current list. openai/gpt-oss-120b is Groq's recommended
# replacement for the now-deprecated llama-3.3-70b-versatile, and is a
# solid default for the structured-JSON, moderate-reasoning tasks this
# file does; swap to openai/gpt-oss-20b if you want lower latency and
# don't mind slightly less careful JSON formatting.
MODEL = "openai/gpt-oss-120b"

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set. See .env.example.")
        _client = Groq(api_key=api_key)
    return _client


def _chat_json(system_prompt: str, user_content: str, max_tokens: int) -> str:
    """One JSON-mode chat completion. Returns the raw JSON text content.

    Any failure here (bad/missing key, low balance, rate limit, network
    error, etc.) is converted into a single plain RuntimeError with the
    provider's own message inside it, instead of letting a Groq-specific
    exception type escape uncaught up to Flask as an unhandled 500 — every
    caller below already expects to catch RuntimeError, and so does
    app.py at each call site."""
    client = _get_client()
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            # openai/gpt-oss-120b is a REASONING model: it spends tokens
            # "thinking" before it writes the JSON answer, and those
            # reasoning tokens are deducted from this same max_tokens
            # budget. "low" keeps that thinking short so the budget below
            # is actually spent on the JSON output, not burned before it.
            reasoning_effort="low",
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
    except Exception as e:  # noqa: BLE001 — deliberately broad, see docstring
        raise RuntimeError(f"The AI request failed: {e}") from e
    content = (resp.choices[0].message.content or "").strip()
    finish_reason = resp.choices[0].finish_reason
    if finish_reason == "length" and not content:
        # Reasoning + output together still hit the cap before any JSON
        # came out. Retrying with a larger budget is cheap and usually
        # succeeds — this is the exact case behind "max completion
        # tokens reached before generating a valid document".
        resp = client.chat.completions.create(
            model=MODEL,
            reasoning_effort="low",
            max_tokens=max_tokens * 2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        content = (resp.choices[0].message.content or "").strip()
    return content


def extract_keywords(user_query: str) -> list[str]:
    system_prompt = (
        "You turn a user's short request into 2-5 search terms for "
        "searching their own Gmail/Drive by subject or filename. "
        "Include distinctive nouns as standalone terms (e.g. 'Aadhaar', "
        "'PAN') AND common real-world spelling variants of them (e.g. "
        "Aadhaar is very often written 'Aadhar' in India — include both "
        "spellings as separate terms). Avoid generic words alone that "
        "match far too much unrelated mail — 'card', 'ID', 'number', "
        "'document' should only appear as part of a specific phrase like "
        "'Aadhaar card', never as a standalone term.\n\n"
        "Reply with ONLY a JSON object, nothing else: "
        '{"keywords": ["term1", "term2", ...]}'
    )
    # Not wrapped in try/except here: a RuntimeError from a real API
    # failure should propagate to the caller (app.py catches it and shows
    # a friendly message), not get silently swallowed into the fallback.
    text = _chat_json(system_prompt, user_query, max_tokens=400)
    try:
        parsed = json.loads(text)
        keywords = parsed.get("keywords")
        if isinstance(keywords, list) and all(isinstance(k, str) for k in keywords):
            return keywords[:5]
    except (json.JSONDecodeError, AttributeError):
        pass
    # Fallback: just use the raw query as a single keyword.
    return [user_query]


_SUMMARY_SYSTEM_PROMPT = """\
You help a user locate their own documents/emails in Gmail and Drive.

You are given a JSON array of search results, each with an "index". Every
snippet/filename in that array has ALREADY been redacted of ID numbers,
card numbers, passwords, and similar secrets (masked as [REDACTED-...]).
The underlying search is a loose full-text match, so it often includes
results that share a common word but are NOT actually what the user
asked for (e.g. an insurance "e-card" email when they asked for their
Aadhaar card) — your job is to separate genuine matches from noise.

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


def summarize_results(user_query: str, results: list[dict]) -> dict:
    """Returns {"reply": str, "relevant_indices": list[int]}. Falls back to
    treating every result as relevant if the model's output can't be
    parsed — erring toward showing more, never toward silently hiding a
    real match."""
    # Cap how many results the model has to reason over/reference in its
    # JSON output. A broad query like "recent mails" can otherwise return
    # dozens of hits, which inflates both the prompt and the required
    # output (every kept index has to be named) enough to blow even a
    # generous token budget on a reasoning model.
    capped = results[:25]
    indexed = [{"index": i, **r} for i, r in enumerate(capped)]
    text = _chat_json(
        _SUMMARY_SYSTEM_PROMPT,
        f"User's request: {user_query!r}\n\n"
        f"Redacted search results (JSON, showing the {len(capped)} most "
        f"relevant of {len(results)} matches): {json.dumps(indexed)}",
        max_tokens=900,
    )
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


_SHEET_SYSTEM_PROMPT = """\
You help a user understand a preview of their own Google Sheet.

You are given the sheet's name, its tab names, and a preview of rows from
one tab (as a JSON 2D array). Every cell has ALREADY been redacted of ID
numbers, account numbers, and secret-looking tokens (masked as
[REDACTED-...]).

Rules, no exceptions:
- NEVER output any sequence of digits longer than 3, and never output
  anything that looks like an ID number, account number, password, PIN,
  or OTP, even if you believe you can reconstruct one from context.
- Do not guess or reconstruct a redacted value.
- Answer the user's actual question about the sheet (e.g. "what's in it",
  "how many rows", "what are the column headers") using only the visible,
  non-redacted cell text.
- Keep the reply short and practical: a few sentences, or a tiny bullet
  list of column headers / notable rows if that's what's being asked.
- If the preview doesn't contain enough to answer, say so plainly and
  suggest opening the sheet link instead of guessing.

Reply with ONLY a JSON object, nothing else:
{"reply": "<your short answer>"}
"""


def summarize_sheet_preview(
    user_query: str, sheet_name: str, tab_names: list[str], rows: list[list[str]]
) -> str:
    """Given an already-redacted preview of one Sheet's rows, answers the
    user's question about its content. Returns plain reply text."""
    text = _chat_json(
        _SHEET_SYSTEM_PROMPT,
        f"User's request: {user_query!r}\n\n"
        f"Sheet name: {sheet_name!r}\n"
        f"Tab names: {json.dumps(tab_names)}\n"
        f"Redacted preview rows (JSON 2D array): {json.dumps(rows)}",
        max_tokens=800,
    )
    try:
        parsed = json.loads(text)
        reply = parsed.get("reply", "").strip()
        if reply:
            return reply
    except (json.JSONDecodeError, AttributeError):
        pass
    return text or "Here's a preview of that sheet."


_ACTION_SYSTEM_PROMPT_TEMPLATE = """\
You parse a user's request to perform a WRITE action in Gmail, Google
Calendar, or Google Sheets into a single structured action. You never
execute anything — you only propose it for the user to confirm. Today's
date is {today} ({weekday}).

Supported actions:
- "send_email": needs "to" (email address), "subject", "body". If the
  user didn't give a subject/body, write a short reasonable one yourself
  from context — the user will see and can cancel it before anything is
  actually sent.
- "create_event": needs "summary" (title), "date" (YYYY-MM-DD, resolved
  from today's date above — assume the nearest upcoming occurrence of a
  bare day/month), "start_time" (24h "HH:MM", default "10:00" if not
  given), "end_time" (24h "HH:MM", default one hour after start_time if
  not given). Optionally "description", "location", "attendees" (list of
  email addresses actually mentioned — never invent one), "add_meet_link"
  (true only if the user asked for a Meet link / video call).
- "create_sheet": needs "title" for the new sheet. Optionally
  "header_row" (list of column header strings) and "initial_rows" (list
  of row arrays) if the user described specific information to put in it
  right away.
- "update_sheet": needs "sheet_name_query" (a short phrase to search for
  the EXISTING sheet by name, e.g. "PF" for "the PF sheet") and "rows"
  (list of row arrays — each row itself a list of cell strings) to
  append to it.

If the request doesn't clearly match one of these, or is missing
something essential you truly cannot infer (e.g. no recipient email at
all for send_email), set "action" to "unsupported" and explain what's
missing in "summary".

Always include a "summary" field: one short, concrete sentence describing
EXACTLY what will happen if confirmed — this is the ONLY thing the user
reads to decide whether to confirm, e.g. "Send an email to
charan@gmail.com with subject 'Quick update'." or "Create a calendar
event 'Team sync' on 2026-09-04 from 10:00 to 11:00.".

Reply with ONLY a JSON object, nothing else:
{{"action": "<one of the above, or 'unsupported'>", "summary": "<short sentence>", "params": {{...action-specific fields above...}}}}
"""


def extract_write_action(user_query: str) -> dict:
    """Parses a natural-language write request (send an email, create an
    event, create/update a sheet) into a structured, confirmable action.
    Returns {"action": str, "summary": str, "params": dict}. This
    function never executes anything itself — app.py shows "summary" to
    the user and only calls the matching google_client write function
    after they explicitly confirm."""
    today = datetime.now().astimezone()
    text = _chat_json(
        _ACTION_SYSTEM_PROMPT_TEMPLATE.format(
            today=today.strftime("%Y-%m-%d"), weekday=today.strftime("%A")
        ),
        user_query,
        max_tokens=800,
    )
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and parsed.get("action") and parsed.get("summary"):
            parsed.setdefault("params", {})
            return parsed
    except (json.JSONDecodeError, AttributeError):
        pass
    return {
        "action": "unsupported",
        "summary": (
            "I couldn't understand exactly what you want me to do — "
            "could you rephrase it as one clear instruction?"
        ),
        "params": {},
    }