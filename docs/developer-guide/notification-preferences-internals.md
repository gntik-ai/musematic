# Notification Preferences Internals

FR-651 extends the existing `UserAlertSettings` row instead of creating a sibling preferences table.

## Data Model

The Alembic migration for UPD-042 adds four columns:

- `user_alert_settings.per_channel_preferences`: JSONB map of event type to enabled channels.
- `user_alert_settings.digest_mode`: JSONB map of channel to `immediate`, `hourly`, or `daily`.
- `user_alert_settings.quiet_hours`: nullable JSONB object with `start_time`, `end_time`, and `timezone`.
- `service_account_credentials.created_by_user_id`: nullable user FK for self-service API keys.

The existing `state_transitions`, `delivery_method`, and `webhook_url` fields remain for backward compatibility.

## Channels

The channel set is fixed by the multi-channel notifications feature:

- `in_app`
- `email`
- `webhook`
- `slack`
- `teams`
- `sms`

UI and backend validators should use the same enum. Unknown channels are rejected.

## Mandatory Events

Events matching `security.*` or `incidents.*` cannot have every channel disabled. The UI locks these rows for clarity, but the backend validator is authoritative.

## Quiet Hours

Quiet hours are stored as local wall-clock times plus an IANA timezone. Delivery logic should evaluate quiet hours in that timezone and defer non-critical delivery until the next allowed boundary.

Critical events, including `security.*` and `incidents.*`, bypass quiet hours and deliver immediately.

## Digest Mode

Digest mode is channel-scoped. The scheduler should read `digest_mode[channel]` and choose one of:

- `immediate`: deliver each alert as it arrives.
- `hourly`: group non-critical events into the next hourly digest.
- `daily`: group non-critical events into the next daily digest.

Preference changes apply to events accepted after the preference write completes. In-flight deliveries keep the previous preference snapshot.
