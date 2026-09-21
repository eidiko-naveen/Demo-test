# Phase 6B — Cross-Service Gmail + Drive + Calendar

This phase extends the working Phase 6A build with five connected workflows.

1. **Latest Gmail email -> Calendar**
   - Example: `Find the latest email from Abhay about CP4I and schedule a meeting with him tomorrow at 4 PM.`
   - The sender is resolved from verified Gmail headers.
   - The latest matching email is used as context for the meeting.
   - Calendar creation remains behind explicit confirmation.

2. **Latest email + free scheduling**
   - Example: `Find the latest email from Abhay about CP4I and schedule a meeting with him tomorrow when I'm free.`
   - Uses Mon-Fri 10 AM-7 PM IST, excluding 1-2 PM and 5-5:30 PM, and checks existing Calendar events for overlap.

3. **Drive -> Gmail + Calendar in one request**
   - Example: `Find the CP4I presentation, send it to Abhay, and schedule a meeting with him tomorrow.`
   - The exact Drive file and verified recipient are resolved first.
   - A single confirmation covers the Gmail send and Calendar creation.

4. **Conversational follow-ups**
   - After finding a Drive file, `send it to Abhay` can reuse the remembered file reference.
   - `send it to him` can reuse the remembered person when available.

5. **Security / confirmation**
   - Search operations can run automatically.
   - Gmail sends and Calendar writes require explicit confirmation.
   - The app stores only non-sensitive references in its single-user in-memory context.

## Important

The combined action executes the confirmed Gmail send first and then creates the Calendar event. If an external Google API fails between those operations, the first operation may already have completed; the UI reports the resulting error instead of claiming full success.
