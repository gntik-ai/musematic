# Session Revocation Incident

Use this runbook when a user reports a stolen device, suspicious active session, or account session they do not recognize. This covers FR-654.

## Symptom

- The user sees an unknown device or location in `/settings/security/sessions`.
- The user reports a stolen laptop, phone, or browser profile.
- Security monitoring detects suspicious activity tied to an active session.

## Diagnosis

1. Ask the user to open `/settings/security/sessions` and identify sessions they do not recognize.
2. Confirm the current session is marked as "This session"; it cannot be revoked through the per-session endpoint.
3. Review `/settings/security/activity` for recent `auth.session.*` events.
4. If available, correlate city-level geolocation, user-agent, creation time, and last-active time.

## Remediation

1. Revoke individual suspicious sessions with `DELETE /api/v1/me/sessions/{session_id}`.
2. If compromise is likely, use `POST /api/v1/me/sessions/revoke-others` to revoke every session except the current one.
3. Require password rotation and MFA enrollment when account takeover risk is material.
4. Escalate to incident response if suspicious activity includes data access, API key creation, consent changes, or DSR requests.

## Verification

- Revoked sessions receive 401 on their next API call.
- "Revoke all other sessions" reports the expected `sessions_revoked` count.
- Revocation propagates across pods within 60 seconds.
- `auth.session.revoked` or `auth.session.revoked_all_others` appears in the user's audit trail.
