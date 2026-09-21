# Phase 6B — Person Resolution Safety Fix

## Problem fixed
A request such as "schedule a meeting with Kalyan" could incorrectly resolve
to an automated sender such as `UrbanPro-no-reply@urbanpro.com` simply because
the display name contained "Kalyan".

## New behavior
- Only verified Gmail From headers are considered.
- Automated/no-reply/notification/newsletter style senders are rejected.
- The chatbot must not invent or guess a person's email address.
- If no verified human address remains, it asks for the complete email address.
- Existing Yash/Abhay person resolution remains dynamic.
