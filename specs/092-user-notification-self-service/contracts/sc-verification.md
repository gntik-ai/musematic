# UPD-042 Success Criteria Verification

Status: blocked pending full platform run.

## Required Sweep

The final sweep must verify SC-001 through SC-020 from `spec.md` against a live environment with the control plane, web UI, Redis, PostgreSQL, audit chain, and WebSocket gateway running.

| SC | Measurement |
| --- | --- |
| SC-001 | Bell badge reaches 15 unread alerts within 3 seconds. |
| SC-002 | `/notifications` first paint for 50 alerts is at or below 800 ms p95. |
| SC-003 | Mark-all-read clears the local badge within 2 seconds and other tabs within 5 seconds. |
| SC-004 | Notification preference save completes within 500 ms. |
| SC-005 | Mandatory event toggles cannot disable all channels. |
| SC-006 | API key creation performs MFA step-up when enrolled. |
| SC-007 | API key value is shown once and never appears in list responses. |
| SC-008 | Max 10 personal API keys is enforced. |
| SC-009 | API key revocation propagates within 5 seconds. |
| SC-010 | MFA enrollment displays QR, text secret, and backup codes. |
| SC-011 | Backup-code regeneration shows new one-time codes. |
| SC-012 | MFA disable is refused when admin policy enforces MFA. |
| SC-013 | Session revocation propagates within 60 seconds. |
| SC-014 | 24-hour log scan shows zero secret leaks. |
| SC-015 | Consent revocation takes effect within the configured cache window. |
| SC-016 | DSR self-service creates the same row contract as admin DSR. |
| SC-017 | User activity returns actor-or-subject audit entries. |
| SC-018 | All `/api/v1/me/*` endpoints reject caller-supplied user scope. |
| SC-019 | Accessibility scan shows zero WCAG AA violations on the 9 pages. |
| SC-020 | Existing admin-equivalent surfaces continue to pass. |

## Current Workspace Result

Not executed end to end in this workspace. Static and unit-level checks should be run locally before handing the branch to CI, and the matrix CI must run the new self-service suite in `mock`, `kubernetes`, and `vault` secret modes.
