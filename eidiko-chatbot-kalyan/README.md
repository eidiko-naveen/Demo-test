# EIDIKO — Local Document Finder Chatbot

A local chatbot that helps you find where a document lives in **your own**
Gmail/Drive (e.g. "find my PAN card", "find my Aadhaar"). It returns
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
- Search (Gmail/Drive/Calendar/Sheets listing) is still read-only
  metadata only, same as before.
- **Write actions are opt-in per request, never automatic.** EIDIKO can
  now send an email, create a calendar event, or create/update a Google
  Sheet — but only after it shows you exactly what it's about to do and
  you type `confirm`. Typing anything else (or `cancel`) drops the
  proposed action without touching Google at all. See `PENDING_ACTION` /
  `handle_write_request` / `execute_pending_action` in `app.py` — this
  confirm-first flow is the safety boundary for every write feature.
- Scopes are still as narrow as each feature allows: `gmail.readonly`
  (search) + `gmail.send` (send-only — cannot read/modify/delete mail
  beyond what readonly already allows), `drive.readonly` (search only —
  no Drive write scope at all; creating a new Sheet needs only the
  Sheets scope, not Drive), `calendar.events` (read/write events only,
  not calendar management), `spreadsheets` (full read/write, needed so
  an existing sheet — like a PF sheet you didn't create with this app —
  can be edited, not just brand-new ones).
- Sheets: cell values are only ever read from a small, bounded range
  (first tab, `A1:J50`) — never a whole large sheet — and every cell is
  redacted the same way Gmail snippets and filenames are before it's
  shown to you or sent to Claude. Writes (new sheet creation, appending
  rows) use Sheets' own `append` operation, which finds the next empty
  row itself.
- Meet: it never calls a separate "Meet" API — it just reads the Google
  Meet link already attached to your Calendar events.
- It runs only on `127.0.0.1` (your own machine). It is not deployed
  anywhere public.
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
2. Enable **Gmail API**, **Google Drive API**, **Google Calendar API**,
   and **Google Sheets API** for that project (APIs & Services → Library).
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
window opens for Google's own consent screen — you approve access to
your own account), then start chatting.

**Already had this running before write actions were added?** Your old
`token.json` doesn't include the new `gmail.send`, `calendar.events`, or
full `spreadsheets` scopes, so sending/creating/updating will fail with
a permissions error until you reconnect. Click **Disconnect**, then
**Connect Google Account** again to re-consent with the new scopes.

### Example write requests

```
create a meeting on 4 september
send a mail to charan@gmail.com
schedule an event on 2nd september
create a google sheet and put meeting information on that sheet
update the pf sheet, add this information
```

Each one gets parsed into a proposed action and a one-line summary of
exactly what will happen — nothing is sent/created until you reply
`confirm` (or click the Confirm button). Replying with anything else, or
`cancel`, drops it.

## Files

| File | Purpose |
|---|---|
| `app.py` | Flask routes: `/`, `/api/status`, `/api/authorize`, `/api/chat` — query routing (search vs write), plus the confirm/cancel flow for write actions |
| `google_client.py` | OAuth flow + Gmail/Drive/Calendar/Sheets search (read-only) + send email / create event / create sheet / append rows (write) |
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