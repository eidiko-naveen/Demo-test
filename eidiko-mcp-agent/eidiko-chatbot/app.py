"""
EIDIKO Chatbot — app.py
------------------------
Flask application: Gmail · Google Drive · Google Calendar · Claude AI

Fixes in this version:
- Added  calendar_past  handler  → "what are past / completed events"
- Added  drive_recent   handler  → "recently uploaded files in Drive"
- Fixed  format_calendar_reply() to show proper IST datetime, not raw ISO
- Fixed  make_display_results()  date formatting for calendar events
- Added  "modified" field display for Drive results
"""

import os
from datetime import datetime, timedelta
from urllib.parse import quote

from flask import Flask, request, jsonify, render_template, url_for, Response
from markupsafe import escape
from dotenv import load_dotenv

import google_client
import claude_client
from redact import redact, is_blocked_query


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)


# ============================================================
# SECURITY HEADERS
# ============================================================

@app.after_request
def set_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


# ============================================================
# BASIC ROUTES
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def status():
    authenticated = google_client.is_authenticated()
    return jsonify({"authenticated": authenticated, "connected": authenticated})


# ============================================================
# GOOGLE OAUTH
# ============================================================

@app.route("/api/authorize")
def authorize():
    try:
        redirect_uri = url_for("oauth2callback", _external=True)
        auth_url = google_client.build_auth_url(redirect_uri)
        return jsonify({"ok": True, "authUrl": auth_url})
    except FileNotFoundError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Could not start Google sign-in: {exc}"}), 500


@app.route("/oauth2callback")
def oauth2callback():
    error = request.args.get("error")
    if error:
        safe_error = escape(error)
        return f"""<!doctype html><html><body style="font-family:Arial;padding:60px;text-align:center">
        <h2>Google sign-in was cancelled</h2><p>{safe_error}</p>
        <p>Close this tab and return to EIDIKO.</p></body></html>""", 400

    state = request.args.get("state", "")
    if not state:
        return "<h2>Google sign-in failed</h2><p>Missing OAuth state.</p>", 400

    try:
        credentials = google_client.finish_auth_flow(state, request.url)
        if credentials is None:
            raise RuntimeError("Google did not return valid credentials.")
        return """<!doctype html><html><head><title>EIDIKO - Connected</title>
        <style>body{margin:0;background:#f5f7fb;font-family:Arial;
        display:grid;place-items:center;min-height:100vh}
        .card{background:#fff;padding:40px;border-radius:18px;
        box-shadow:0 15px 50px rgba(0,0,0,.08);text-align:center}</style></head>
        <body><div class="card"><div style="font-size:50px">✓</div>
        <h2>Google connected successfully</h2>
        <p>Gmail, Drive and Calendar connected with read-only access.</p>
        <p>You can close this tab.</p></div></body></html>"""
    except Exception as exc:
        safe_msg = escape(redact(str(exc)))
        return f"""<!doctype html><html><body style="font-family:Arial;padding:60px;text-align:center">
        <h2>Google sign-in failed</h2><p>{safe_msg}</p>
        <p>Close this tab and click Connect Google again.</p></body></html>""", 400


@app.route("/api/disconnect", methods=["POST"])
def disconnect():
    try:
        google_client.disconnect()
        return jsonify({"ok": True, "connected": False})
    except Exception as exc:
        return jsonify({"ok": False, "error": redact(str(exc))}), 500


# ============================================================
# HELPERS
# ============================================================

def _pretty_datetime(iso_str: str) -> str:
    """
    Convert ISO 8601 datetime to a readable string.
    e.g. '2026-08-27T16:00:00+05:30'  →  'Thu, Aug 27 at 04:00 PM'
    e.g. '2026-08-27'                  →  'Thu, Aug 27 (all day)'
    """
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        if "T" in iso_str:
            return dt.strftime("%a, %b %d at %I:%M %p")
        else:
            return dt.strftime("%a, %b %d (all day)")
    except (ValueError, TypeError):
        return iso_str


def _pretty_drive_date(iso_str: str) -> str:
    """Convert Drive modifiedTime ISO to readable string."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %Y %I:%M %p")
    except (ValueError, TypeError):
        return iso_str


def make_display_results(results: list[dict]) -> list[dict]:
    """Convert raw Google API results into uniform display format."""
    display = []
    for result in results:
        source = result.get("source", "")

        title = (
            result.get("subject")
            or result.get("name")
            or result.get("title")
            or "Untitled"
        )

        meta = (
            result.get("from")
            or result.get("mime_type", "").replace("application/vnd.google-apps.", "").replace(".", " ").title()
            or result.get("location")
            or result.get("organizer")
            or ""
        )

        # ── Properly formatted date ──────────────────────────────
        if source == "calendar":
            date = _pretty_datetime(result.get("start", ""))
        elif source == "drive":
            date = _pretty_drive_date(result.get("modified", ""))
        else:
            date = result.get("date", "")

        snippet = result.get("snippet") or result.get("description") or ""

        item = {
            "title": redact(title),
            "meta": redact(meta),
            "date": redact(date),
            "snippet": redact(snippet),
            "link": result.get("link", ""),
            "source": source,
            "attachments": [],
        }

        for att in result.get("attachments", []):
            if att.get("attachment_id"):
                item["attachments"].append({
                    "filename": redact(att.get("filename", "Attachment")),
                    "download_url": (
                        "/api/download"
                        f"?message_id={quote(result.get('id', ''))}"
                        f"&attachment_id={quote(att.get('attachment_id', ''))}"
                        f"&filename={quote(att.get('filename', 'attachment'))}"
                    ),
                })

        display.append(item)
    return display


def format_calendar_reply(events: list[dict], hint: str) -> str:
    """Build a human-readable reply string listing calendar events."""
    if not events:
        return f"I couldn't find any {hint}."

    lines = []
    for event in events:
        name = redact(event.get("name", "(no title)"))
        start = _pretty_datetime(event.get("start", ""))
        location = redact(event.get("location", ""))
        line = f"• {name}"
        if start:
            line += f" — {start}"
        if location:
            line += f" @ {location}"
        lines.append(line)

    count = len(lines)
    return f"I found {count} {hint}.\n\n" + "\n".join(lines)


def _redact_gmail(results):
    for r in results:
        r["subject"] = redact(r.get("subject", ""))
        r["snippet"] = redact(r.get("snippet", ""))
        r["from"] = redact(r.get("from", ""))
    return results


def _redact_drive(results):
    for r in results:
        r["name"] = redact(r.get("name", ""))
    return results


def _redact_calendar(results):
    for r in results:
        r["name"] = redact(r.get("name", ""))
        r["description"] = redact(r.get("description", ""))
        r["location"] = redact(r.get("location", ""))
    return results


def _summarize(user_query, results):
    """Run Claude summarization and filter results. Returns (reply, filtered_results)."""
    try:
        outcome = claude_client.summarize_results(user_query, results)
        reply = redact(outcome.get("reply", f"Found {len(results)} result(s)."))
        indices = outcome.get("relevant_indices", list(range(len(results))))
        filtered = [results[i] for i in indices
                    if isinstance(i, int) and 0 <= i < len(results)]
        return reply, filtered or results
    except Exception:
        return f"Found {len(results)} result(s).", results


# ============================================================
# CHAT — main route, Claude-intent-driven
# ============================================================

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True) or {}
    user_query = (data.get("message") or "").strip()[:1000]

    if not user_query:
        return jsonify({"reply": "Ask me about your emails, files or calendar.", "results": []})

    if is_blocked_query(user_query):
        return jsonify({
            "reply": "I won't search for passwords, PINs, OTPs or similar secrets.",
            "results": [],
        })

    credentials = google_client.get_credentials()
    if credentials is None:
        return jsonify({
            "reply": "Your Google account isn't connected yet. Click Connect Google above.",
            "results": [],
        }), 401

    # ── Step 1: Ask Claude what the user wants ──────────────
    try:
        intent_obj = claude_client.classify_intent(user_query)
    except Exception:
        intent_obj = {
            "intent": "gmail_search", "sources": ["gmail"],
            "gmail_query": user_query, "drive_query": user_query,
            "calendar_query": "", "time_filter": "all",
            "max_results": 10, "reply_hint": "results matching your query",
        }

    intent        = intent_obj.get("intent", "gmail_search")
    sources       = intent_obj.get("sources", ["gmail"])
    gmail_query   = intent_obj.get("gmail_query", "")
    drive_query   = intent_obj.get("drive_query", "")
    calendar_query= intent_obj.get("calendar_query", "")
    time_filter   = intent_obj.get("time_filter", "all")
    max_results   = max(1, min(int(intent_obj.get("max_results", 10)), 50))
    reply_hint    = intent_obj.get("reply_hint", "your results")

    # ── Step 2: Dispatch ────────────────────────────────────

    # ── EMAIL COUNT ─────────────────────────────────────────
    if intent == "gmail_count":
        try:
            count = google_client.count_emails(credentials, time_filter=time_filter)
            period = {
                "today": "today", "yesterday": "yesterday",
                "this_week": "this week", "past_week": "the past 7 days",
                "this_month": "this month", "past_month": "the past 30 days",
            }.get(time_filter, "")
            return jsonify({
                "reply": f"You have {count} email{'s' if count != 1 else ''} {period}.",
                "results": [],
            })
        except Exception as exc:
            return jsonify({"reply": f"Couldn't count emails: {redact(str(exc))}", "results": []}), 500

    # ── RECENT EMAILS ───────────────────────────────────────
    if intent == "gmail_recent":
        try:
            tf = time_filter if time_filter != "all" else "today"
            results = google_client.get_recent_emails(
                credentials, gmail_query=gmail_query,
                time_filter=tf, max_results=max_results,
            )
            results = _redact_gmail(results)
            if not results:
                return jsonify({"reply": f"No emails found for {reply_hint}.", "results": []})
            period = {"today": "today", "yesterday": "yesterday",
                      "this_week": "the past week", "past_week": "the past week",
                      "this_month": "the past month"}.get(tf, "recently")
            return jsonify({
                "reply": f"Here are your {len(results)} most recent emails from {period}.",
                "results": make_display_results(results),
            })
        except Exception as exc:
            return jsonify({"reply": f"Couldn't fetch recent emails: {redact(str(exc))}", "results": []}), 500

    # ── GMAIL SEARCH ────────────────────────────────────────
    if intent == "gmail_search":
        try:
            keywords = claude_client.extract_keywords(user_query)
            results = google_client.search_gmail(
                credentials, keywords=keywords, gmail_query=gmail_query,
                time_filter=time_filter, max_results=max_results,
                fetch_attachments=True,
            )
            results = _redact_gmail(results)
            if not results:
                return jsonify({"reply": f"No emails found matching '{reply_hint}'.", "results": []})
            reply, filtered = _summarize(user_query, results)
            return jsonify({"reply": reply, "results": make_display_results(filtered)})
        except Exception as exc:
            return jsonify({"reply": f"Couldn't search Gmail: {redact(str(exc))}", "results": []}), 500

    # ── DRIVE SEARCH ────────────────────────────────────────
    if intent == "drive_search":
        try:
            keywords = claude_client.extract_keywords(drive_query or user_query)
            results = google_client.search_drive(credentials, keywords=keywords,
                                                  max_results=max_results)
            results = _redact_drive(results)
            if not results:
                return jsonify({"reply": f"No files found matching '{reply_hint}'.", "results": []})
            reply, filtered = _summarize(user_query, results)
            return jsonify({"reply": reply, "results": make_display_results(filtered)})
        except Exception as exc:
            return jsonify({"reply": f"Couldn't search Drive: {redact(str(exc))}", "results": []}), 500

    # ── DRIVE RECENT  (NEW) ──────────────────────────────────
    if intent == "drive_recent":
        try:
            days = 30 if time_filter in ("this_month", "past_month") else 7
            results = google_client.get_recent_drive_files(
                credentials, max_results=max_results, days=days
            )
            results = _redact_drive(results)
            if not results:
                return jsonify({
                    "reply": f"No recently uploaded files found in the past {days} days.",
                    "results": [],
                })
            return jsonify({
                "reply": f"Here are the {len(results)} most recently uploaded or modified files in your Drive.",
                "results": make_display_results(results),
            })
        except Exception as exc:
            return jsonify({"reply": f"Couldn't fetch Drive files: {redact(str(exc))}", "results": []}), 500

    # ── CALENDAR TODAY ──────────────────────────────────────
    if intent == "calendar_today":
        try:
            events = google_client.get_calendar_events(
                credentials, query=calendar_query,
                time_filter="today", max_results=max_results,
            )
            events = _redact_calendar(events)
            return jsonify({
                "reply": format_calendar_reply(events, "events scheduled for today"),
                "results": make_display_results(events),
            })
        except Exception as exc:
            return jsonify({"reply": f"Couldn't access Calendar: {redact(str(exc))}", "results": []}), 500

    # ── CALENDAR UPCOMING ───────────────────────────────────
    if intent == "calendar_upcoming":
        try:
            events = google_client.get_calendar_events(
                credentials, query=calendar_query,
                time_filter="upcoming", max_results=max_results,
            )
            events = _redact_calendar(events)
            return jsonify({
                "reply": format_calendar_reply(events, "upcoming events"),
                "results": make_display_results(events),
            })
        except Exception as exc:
            return jsonify({"reply": f"Couldn't access Calendar: {redact(str(exc))}", "results": []}), 500

    # ── CALENDAR PAST  (NEW) ─────────────────────────────────
    if intent == "calendar_past":
        try:
            # Choose window based on time_filter Claude returned
            days = 30 if time_filter == "past_month" else 7
            tf = "past_month" if days == 30 else "past_week"
            events = google_client.get_calendar_events(
                credentials, query=calendar_query,
                time_filter=tf, max_results=max_results,
            )
            events = _redact_calendar(events)
            window = "past 30 days" if days == 30 else "past 7 days"
            return jsonify({
                "reply": format_calendar_reply(
                    events, f"completed events from the {window}"
                ),
                "results": make_display_results(events),
            })
        except Exception as exc:
            return jsonify({"reply": f"Couldn't fetch past events: {redact(str(exc))}", "results": []}), 500

    # ── CALENDAR SEARCH ─────────────────────────────────────
    if intent == "calendar_search":
        try:
            events = google_client.get_calendar_events(
                credentials, query=calendar_query,
                time_filter="upcoming", max_results=max_results,
            )
            events = _redact_calendar(events)
            return jsonify({
                "reply": format_calendar_reply(events, reply_hint),
                "results": make_display_results(events),
            })
        except Exception as exc:
            return jsonify({"reply": f"Couldn't search Calendar: {redact(str(exc))}", "results": []}), 500

    # ── MULTI SEARCH ────────────────────────────────────────
    if intent == "multi_search":
        try:
            all_results = []
            per = max(5, max_results // 3)

            if "gmail" in sources:
                kw = claude_client.extract_keywords(user_query)
                gr = google_client.search_gmail(credentials, keywords=kw,
                                                 gmail_query=gmail_query,
                                                 time_filter=time_filter,
                                                 max_results=per,
                                                 fetch_attachments=False)
                all_results.extend(_redact_gmail(gr))

            if "drive" in sources:
                dk = claude_client.extract_keywords(drive_query or user_query)
                dr = google_client.search_drive(credentials, keywords=dk,
                                                 max_results=per)
                all_results.extend(_redact_drive(dr))

            if "calendar" in sources:
                cr = google_client.get_calendar_events(credentials,
                                                        query=calendar_query,
                                                        time_filter="upcoming",
                                                        max_results=per)
                all_results.extend(_redact_calendar(cr))

            if not all_results:
                return jsonify({"reply": "Nothing found across Gmail, Drive or Calendar.", "results": []})

            reply, filtered = _summarize(user_query, all_results)
            return jsonify({"reply": reply, "results": make_display_results(filtered)})
        except Exception as exc:
            return jsonify({"reply": f"Multi-search failed: {redact(str(exc))}", "results": []}), 500

    # ── UNKNOWN — safe fallback ─────────────────────────────
    try:
        keywords = claude_client.extract_keywords(user_query)
        results = google_client.search_gmail(credentials, keywords=keywords,
                                              max_results=10, fetch_attachments=False)
        results = _redact_gmail(results)
        if results:
            return jsonify({
                "reply": "Here's what I found that might be relevant.",
                "results": make_display_results(results),
            })
    except Exception:
        pass

    return jsonify({
        "reply": (
            "I wasn't sure what you were looking for. "
            "Try: 'show recent emails', 'find a file in Drive', "
            "'what meetings do I have today', or 'what are my past events'."
        ),
        "results": [],
    })


# ============================================================
# ATTACHMENT DOWNLOAD
# ============================================================

@app.route("/api/download")
def download_attachment():
    credentials = google_client.get_credentials()
    if credentials is None:
        return jsonify({"error": "Google account not connected."}), 401

    message_id    = request.args.get("message_id", "")
    attachment_id = request.args.get("attachment_id", "")
    filename      = request.args.get("filename", "attachment")

    if not message_id or not attachment_id:
        return jsonify({"error": "Missing attachment information."}), 400

    try:
        data = google_client.get_attachment_bytes(credentials, message_id, attachment_id)
        from werkzeug.utils import secure_filename
        safe_name = secure_filename(filename) or "attachment"
        return Response(
            data,
            mimetype="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
        )
    except Exception as exc:
        return jsonify({"error": "Couldn't download: " + redact(str(exc))}), 500


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true",
        use_reloader=False,
    )