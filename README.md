# EIDIKO — Local Document Finder Chatbot

A natural-language workspace assistant that helps you find where documents, emails, and calendar events live in **your own**
Gmail/Drive/Google Calendar (e.g. "find my PAN card", "find my Aadhaar"). It returns
**links and metadata only** — subject lines, filenames, dates — never the
actual ID number, and it refuses password/PIN/OTP/secret-style queries
outright.

## Attachment downloads

Gmail results that have an attachment show an extra "⬇ filename" link.
Clicking it streams the file straight from the Gmail API to your browser's
normal download (`/api/download` in `app.py`) — the bytes pass through
this process only, are never parsed/stored/logged, and are **never** sent
to the Claude API. This is the same as opening the email in Gmail and
clicking download yourself, just faster.

Downloaded files land wherever your browser normally saves downloads —
they are real copies of your documents (PAN card scans, Aadhaar copies,
etc.) sitting on disk from that point on. Handle them the way you'd
handle any sensitive document: don't leave them in a shared/synced
downloads folder longer than needed, and never commit them to a repo.

## What this deliberately does NOT do

- It never extracts, stores, or displays a PAN number, Aadhaar number, or
  any other ID value.
- It never searches for or returns passwords, PINs, OTPs, or API keys —
  see `redact.py::is_blocked_query`. These queries are refused before any
  search runs.
- Gmail search remains read access, while sending email requires the separate `gmail.send` scope and explicit confirmation. Drive uses `drive` for confirmed file organization. Calendar supports confirmed create/modify/cancel actions.
- Local development defaults to `127.0.0.1`; the included OCP deployment package runs behind an OpenShift Route.
- Anything sent to the Claude API for query understanding / summarizing
  is redacted metadata (subjects, filenames, short snippets with any
  ID/secret-looking text masked) — never full email/file bodies.

Please keep it this way if you extend it. This tool searches **your own**
account with **your own** consent — it should never be pointed at, or
repurposed to run against, an account that isn't yours.

## Setup

### 1. Google Cloud — enable APIs & get OAuth credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and
   create (or pick) a project.
2. Enable **Gmail API**, **Google Drive API**, and **Google Calendar API** for that project
   (APIs & Services → Library).
3. Configure the **OAuth consent screen** (External is fine; "Testing"
   mode is fine since only you will use it — add your own email as a
   test user).
4. Create credentials → **OAuth client ID** → Application type:
   **Desktop app**.
5. Download the resulting JSON and save it as:
   `eidiko-chatbot/credentials/credentials.json`

### 2. Claude API key

Get an API key from the [Anthropic Console](https://console.anthropic.com/),
then:

```bash
cd eidiko-chatbot
cp .env.example .env
# edit .env and paste your key into ANTHROPIC_API_KEY=
```

### 3. Install & run

```bash
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`, click **Connect Google Account** (a browser
window opens for Google's own consent screen — you approve read-only
access to your own account), then start chatting.

## Files

| File | Purpose |
|---|---|
| `app.py` | Flask routes: `/`, `/api/status`, `/api/authorize`, `/api/chat` |
| `google_client.py` | OAuth flow + read-only Gmail/Drive/Calendar metadata search |
| `claude_client.py` | Claude API calls for keyword extraction + result summarizing |
| `redact.py` | Masks ID numbers/secrets in any text before it's shown or sent anywhere; blocks password-style queries |
| `templates/index.html`, `static/*` | Chat UI with the EIDIKO logo |

## Swapping in your real EIDIKO logo

`static/logo.svg` is a placeholder mark I generated — replace it with your
actual brand asset (same filename, or update the `<img src>` in
`templates/index.html`).

## Local secrets — do not commit or share

`credentials/credentials.json`, `token.json`, and `.env` all contain
sensitive OAuth/API secrets. They're already in `.gitignore`. Never paste
their contents into chat, a repo, or anywhere else.

## Changelog — search accuracy improvements

This update improves Gmail/Drive search accuracy without changing OAuth
scopes, routes, or the existing UI. Summary (see the accompanying chat
response for full detail):

- Added `query_intent.py`: deterministic (regex-only, no LLM, no
  network call) detection of (a) a person's name mentioned in the
  query (e.g. "emails from Jeevan", "did Abhay send me mail") and
  (b) whether the query is aimed at Gmail, Drive, or both.
- `google_client.search_gmail()` now accepts a `person` argument. When
  given, it builds a Gmail `from:` query AND independently verifies
  every returned message's actual `From` header in Python
  (`_sender_matches`) — so a real sender match is never dropped just
  because an LLM-based keyword step failed to recognize the name. A
  broadened fallback search runs automatically if the strict `from:`
  query comes back empty.
- `claude_client.py` gained `extract_query_intent()`, a richer version
  of the existing `extract_keywords()` that also guesses a person name
  and a gmail/drive target — used as a secondary signal only, never
  the sole source of truth for "does this person exist in my inbox".
- `app.py`'s `/api/chat` now routes to Gmail and/or Drive based on the
  detected intent (with a safety-net fallback to check the other
  source if the routed one finds nothing), and always keeps any
  Python-verified sender match in the final results even if Claude's
  own ranking step would have otherwise excluded it.
- No OAuth scopes, routes, environment variable names, or UI changed.
  `requirements.txt` is unchanged (no new dependencies — the new logic
  uses only the Python standard library `re` module).
\n## Calendar search\n\nPhase 2 adds read-only Google Calendar search. Example questions include:\n\n- "What meetings do I have tomorrow?"\n- "Show my meetings today"\n- "Do I have a meeting with Abhay tomorrow?"\n- "When is my CP4I meeting?"\n\nCalendar results return event title, time, organizer/attendee metadata, Calendar link, and a Google Meet link when the event already has one. This phase does **not** create, edit, cancel, or invite anyone to meetings.\n\nAfter adding the Calendar read/write scope, reconnect the Google account once so a fresh token containing the new scope is issued.\n
## Changelog — Phase 2 Calendar search

- Added the read-only Google Calendar scope `calendar.events.readonly`.
- Added Google Calendar API access and deterministic event search for today,
  tomorrow, this week, next week, and a default 7-day window.
- Added Calendar routing to `query_intent.py` and `claude_client.py`.
- Added deterministic person/topic filtering for Calendar events.
- Calendar results expose event title, start/end time, organizer/attendees,
  Calendar link, location, and an existing Google Meet link when available.
- The UI now renders Calendar details and an existing Google Meet link.
- No Calendar create/edit/delete/invite functionality was added.
- No Gmail/Drive write permissions were added.


## Phase 2 Calendar search fixes
- Supports explicit dates such as `28th August`, `August 28`, and `28/08/2026`.
- Supports open-ended upcoming searches such as `Do I have any upcoming events?`.
- Calendar routing words and date phrases are not treated as event-content keywords.
- Empty Calendar results return a Calendar-specific message instead of a Gmail/Drive fallback.


## Phase 3A — Confirmed Google Drive file move

The chatbot now supports one write action: moving an existing Drive file into
an existing Drive folder. Example:

    Take the CP4I presentation and store it in my AI folder

The app first resolves the source file and destination folder using Drive
metadata. It then shows a confirmation button. **Nothing is moved until the
user explicitly clicks Confirm.** If there are multiple matching files or
folders, the app refuses to guess and asks for a more specific name. Exact
folder names are preferred, so an "AI" request resolves to the folder named
"AI" rather than a broader match such as "GenAI". File descriptions are also
resolved by distinctive filename tokens, so "CP4I presentation" can resolve
to a filename such as "cp4i_escalation_presentation (1).html".

### OAuth scope change

Phase 3A changes the Drive scope from `drive.readonly` to the broader
`drive` scope because Google requires write permission to move existing files.
Gmail remains `gmail.readonly` and Calendar remains
`calendar.events.readonly`.

After installing this Phase 3 build, delete/rename the old `token.json` and
click **Connect Google Account** again. Approve the new Drive permission.
Do not reuse an old read-only token.

The action endpoints are local Flask routes:

- `POST /api/action/confirm`
- `POST /api/action/cancel`

The pending action is stored only in memory and disappears when the local
process restarts. The confirmation is required before `files.update` is
called.


## Phase 3B — Confirmed Gmail email sending

The chatbot can now prepare and send a plain-text Gmail message when the user provides an explicit recipient email address, subject, and body. Example:

    send an email to abhay@example.com subject: CP4I update body: The latest build is ready for testing.

The app first shows a confirmation action. **Nothing is sent until the user explicitly clicks Confirm.** The message body is kept only in the in-memory pending action until confirmation or process restart.

For safety, Phase 3B does not guess a recipient from a person's name. Use an explicit email address. Recipient/contact lookup can be added as a separate phase after this flow is validated.

### OAuth scope change

Phase 3B adds `gmail.send`. After installing this build, remove the existing `token.json` and reconnect Google so Google issues a fresh token containing the new scope. The Drive write scope and Calendar read/write scope remain.


### Attachment integrity fix
Drive attachments now use MediaIoBaseDownload and are validated before Gmail sends them. Invalid/empty PDFs and Office files are rejected and never emailed.


## Phase 4C — Multiple named Calendar attendees

Calendar creation now supports multiple named attendees in natural language, for example:

    Create a meeting with Abhay and Jaina tomorrow at 4 PM for 30 minutes

The app resolves each named person independently against verified Gmail sender headers, refuses ambiguous or missing matches instead of guessing, shows all resolved email addresses in the confirmation, and only after confirmation creates one Calendar event with all attendees and one Google Meet link.

Existing Gmail search/send, Drive organization, multi-attachment email, Calendar search, single-attendee resolution, confirmation, and Google Meet behavior remain unchanged.


## Phase 4D — Calendar modify/cancel
- Reschedule an existing timed event, e.g. `Change my "Meeting with Abhay" to 5 PM tomorrow`.
- Cancel an existing event, e.g. `Cancel my "Meeting with Abhay"`.
- Existing event is resolved from Google Calendar; ambiguous matches require an exact event name.
- Every write requires explicit confirmation. Reschedules preserve the original duration, attendees, and Meet conference. Calendar updates use `sendUpdates=all`; cancellation notifies attendees through Google Calendar.


## Phase 5 — Calendar Intelligence

Phase 5 adds four Calendar workflows:
- Move an existing event using natural language (existing Phase 4D behavior), e.g. `Move my OCP meeting to tomorrow at 5 PM`.
- List meetings/events for a natural time window such as `What meetings do I have this week?` (existing Calendar search behavior).
- Cancel all events for a day, e.g. `Cancel all my meetings tomorrow`. The app lists the number and names of events and requires confirmation before cancelling each event.
- Schedule a meeting with a named attendee in the first free 30-minute slot next week, e.g. `Schedule a 30-minute meeting with Abhay next week when I'm free`. The app resolves the attendee from verified Gmail sender data, searches Mon-Fri 10 AM-7 PM IST, excluding 1-2 PM and 5-5:30 PM breaks for the first free slot, asks for confirmation, then creates the Calendar event with a Google Meet link.


### Free-slot availability rules
- Monday-Friday only
- Office hours: 10:00 AM-7:00 PM IST
- Breaks: 1:00-2:00 PM and 5:00-5:30 PM
- Existing Calendar events are checked for overlap before proposing a slot.


## Phase 6B — Cross-Service Gmail + Drive + Calendar

The chatbot now supports connected Gmail/Drive/Calendar workflows:
- Find the latest email from a verified person about a topic and prepare a follow-up Calendar meeting.
- Schedule the follow-up at an explicit time or the first free slot on a requested day. Free-slot scheduling respects Mon-Fri 10 AM-7 PM IST and excludes 1-2 PM and 5-5:30 PM.
- Find a Drive presentation/file, email it to a verified person, and schedule a meeting in the same confirmed action.
- Reuse a remembered non-sensitive file/person reference for short follow-ups such as `send it to Abhay`.
- Gmail sends and Calendar writes always require explicit confirmation.


## OCP deployment

See `OCP-DEPLOYMENT-README.md` and `OCP-C01-C23-Checklist.md` for the C01–C23 deployment handoff. The OCP image uses Gunicorn, configurable environment variables, Kubernetes ConfigMap/Secret integration, health probes, resource requests/limits, a Service/Route, and a PVC for OAuth token state.
