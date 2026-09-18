# Phase 4D — Calendar Modify & Cancel

Implemented on top of Phase 4C. Existing Gmail, Drive, multi-attachment, Calendar search/create, Meet, and named/multiple attendee features are preserved.

## Test 1
`Change my "Meeting with Abhay" to 5 PM tomorrow`

Expected: existing event is found, new time is shown, confirmation required, then Calendar event is patched and attendees are notified.

## Test 2
`Cancel my "Meeting with Abhay"`

Expected: exact event is found, cancellation confirmation shown, then event is deleted/cancelled and attendees are notified.

If multiple events have similar titles, the chatbot asks for the exact event name instead of guessing.
