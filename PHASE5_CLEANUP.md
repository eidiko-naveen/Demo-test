# Phase 5 Cleanup — Request Isolation & Calendar Parsing

## Fixes included

- Each new chat request clears stale pending confirmations and old conversational
  context unless the user explicitly uses a follow-up reference such as `it`,
  `that`, `this`, `him`, `her`, or `them`.
- Gmail → Calendar parsing now requires an actual `latest email from ...` clause.
  This prevents normal Calendar requests such as:
  `Schedule a 30-minute meeting with Kousik next week when I'm free`
  from being parsed as Gmail requests.
- The free-slot Calendar parser therefore receives `Kousik` as the person and
  `next week` as the time constraint.
- Normal email requests cannot accidentally reuse the previous Drive attachment.
  A previous file is reused only for explicit follow-ups such as `Send it to Abhay`.
- Existing office availability remains:
  Monday–Friday, 10:00 AM–7:00 PM IST, excluding 1:00–2:00 PM and 5:00–5:30 PM.
- Existing confirmation requirements and Gmail/Drive/Calendar/Meet actions are
  unchanged.

## Intended behavior

New request:
`Find the latest email from Yash about OCP ...`
→ starts fresh and cannot inherit an old PAN/file/person.

Explicit follow-up:
`Send it to Abhay`
→ may use the immediately preceding selected file.

Independent request:
`Schedule a meeting with Kousik next week when I'm free`
→ resolves Kousik and searches valid free Calendar slots.
