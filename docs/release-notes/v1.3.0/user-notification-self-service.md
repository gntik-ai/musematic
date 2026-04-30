# User Notification Center And Self-Service Security

UPD-042 adds user-facing surfaces for FR-649 through FR-657. The change is additive and does not remove existing admin or backend APIs.

## User-Facing Pages

- `/notifications`: persistent alert inbox with filtering and mark-all-read.
- Global notification bell: five most recent alerts and a link to the inbox.
- `/settings/notifications`: event-channel matrix, digest mode, quiet hours, and test notification.
- `/settings/api-keys`: personal API keys with MFA step-up, one-time display, and revoke.
- `/settings/security/mfa`: MFA enrollment, backup-code regeneration, and disable flow when policy permits it.
- `/settings/security/sessions`: session list, per-session revoke, and revoke-other-sessions.
- `/settings/security/activity`: user-scoped audit trail.
- `/settings/privacy/consent`: consent revoke and history.
- `/settings/privacy/dsr`: self-service GDPR DSR submission and status.

## API Additions

Seventeen self-service endpoints were added under `/api/v1/me/*` or the existing `/me/alerts*` notification namespace. They are scoped to the authenticated principal and do not accept a caller-supplied `user_id`.

## Database Changes

Migration `070_user_self_service_extensions.py` adds:

- `user_alert_settings.per_channel_preferences`
- `user_alert_settings.digest_mode`
- `user_alert_settings.quiet_hours`
- `service_account_credentials.created_by_user_id`

Existing notification preference fields remain backward compatible.

## Audit Events

New user-visible flows emit:

- `auth.session.revoked`
- `auth.session.revoked_all_others`
- `auth.api_key.created`
- `auth.api_key.revoked`
- `auth.mfa.enrolled`
- `auth.mfa.disabled`
- `auth.mfa.recovery_codes_regenerated`
- `privacy.consent.revoked`
- `privacy.dsr.submitted`
- `notifications.preferences.updated`

## Compatibility

No breaking changes. Admin service-account endpoints, admin DSR paths, existing MFA enrollment endpoints, and existing `/me/alerts*` read endpoints remain available.
