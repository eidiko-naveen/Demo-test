"""Authorize this project with your Google account and print a refresh token."""

from __future__ import annotations

import getpass
import os
import sys

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def main() -> None:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Install dependencies first: pip install -r requirements.txt", file=sys.stderr)
        raise SystemExit(1)

    client_id = os.environ.get("GOOGLE_CLIENT_ID") or input("GOOGLE_CLIENT_ID: ").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET") or getpass.getpass(
        "GOOGLE_CLIENT_SECRET (hidden): "
    ).strip()
    if not client_id or not client_secret:
        print("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are required.", file=sys.stderr)
        raise SystemExit(1)

    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        },
        SCOPES,
    )
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    if not credentials.refresh_token:
        print("Google did not return a refresh token. Revoke the app and try again.", file=sys.stderr)
        raise SystemExit(1)

    print("\nAdd these values to your local .env (never commit that file):")
    print(f"GOOGLE_CLIENT_ID={client_id}")
    print("GOOGLE_CLIENT_SECRET=<use the same secret you entered above>")
    print(f"GOOGLE_REFRESH_TOKEN={credentials.refresh_token}")


if __name__ == "__main__":
    main()
