# UPD-042 Audit Emission Verification

Status: blocked pending live backend and database-backed synthetic flow run.

## Required Procedure

For each state-changing self-service endpoint, run a synthetic request and assert `audit_chain_entries` grows by exactly one row with the expected event type.

| Flow | Endpoint | Expected Event |
| --- | --- | --- |
| Revoke session | `DELETE /api/v1/me/sessions/{session_id}` | `auth.session.revoked` |
| Revoke other sessions | `POST /api/v1/me/sessions/revoke-others` | `auth.session.revoked_all_others` |
| Create API key | `POST /api/v1/me/service-accounts` | `auth.api_key.created` |
| Revoke API key | `DELETE /api/v1/me/service-accounts/{sa_id}` | `auth.api_key.revoked` |
| Confirm MFA enrollment | `POST /api/v1/auth/mfa/confirm` | `auth.mfa.enrolled` |
| Regenerate backup codes | `POST /api/v1/auth/mfa/recovery-codes/regenerate` | `auth.mfa.recovery_codes_regenerated` |
| Disable MFA | `POST /api/v1/auth/mfa/disable` | `auth.mfa.disabled` |
| Revoke consent | `POST /api/v1/me/consent/revoke` | `privacy.consent.revoked` |
| Submit DSR | `POST /api/v1/me/dsr` | `privacy.dsr.submitted` |
| Update preferences | `PUT /api/v1/me/notification-preferences` | `notifications.preferences.updated` |

## Current Workspace Result

Not executed in this workspace because the task requires a live database-backed platform instance and synthetic identities with MFA, sessions, consents, and API keys.

The new E2E suite includes coverage hooks under `tests/e2e/suites/self_service/` for these flows.
