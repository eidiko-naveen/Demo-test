# Google Meet escalation setup

The feature is disabled by default. It schedules a Google Calendar event with
a Meet link only when the same eligible resource remains `CRITICAL` for the
configured number of consecutive monitoring cycles.

## What you need to provide

Use a Google account owned by your team, not credentials copied from the
reference project.

1. In your own Google Cloud project, enable the Google Calendar API.
2. Configure the OAuth consent screen and create an OAuth client of type
   **Desktop app**.
3. Put your client ID and client secret in your shell temporarily:

   ```bash
   export GOOGLE_CLIENT_ID='your-client-id'
   export GOOGLE_CLIENT_SECRET='your-client-secret'
   ```

4. Run `python get_google_refresh_token.py` and authorize the account that
   should own the meetings.
5. Add your own `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and
   `GOOGLE_REFRESH_TOKEN` to the local `.env` file.
6. Replace the placeholder attendees in `agent/escalation_owners.json`.
7. Set `ESCALATION_ENABLED=true` only after the above values are ready.

Do not commit `.env`, OAuth secrets, refresh tokens, or a real owner mapping.

## Trigger behavior

- Only `CRITICAL` failures are eligible.
- `ESCALATION_COMPONENTS` is matched case-insensitively against the component,
  resource name, and pod namespace.
- The same component and resource must be critical in every required cycle.
- One invite is created when the threshold is first reached. The agent does
  not create another invite every cycle while the same incident continues.
- A Google API failure is logged and does not stop normal report email or run
  persistence.
