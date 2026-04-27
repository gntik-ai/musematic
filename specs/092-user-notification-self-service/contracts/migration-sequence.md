# UPD-042 Migration Sequence

Date: 2026-04-27

## Current Sequence

The highest existing Alembic migration in `apps/control-plane/migrations/versions/` is:

- `069_oauth_provider_env_bootstrap.py`

## UPD-042 Assignment

UPD-042 uses:

- `070_user_self_service_extensions.py`

The migration must add:

- `user_alert_settings.per_channel_preferences` as JSONB with default `{}`.
- `user_alert_settings.digest_mode` as JSONB with default `{}`.
- `user_alert_settings.quiet_hours` as nullable JSONB.
- `service_account_credentials.created_by_user_id` as nullable UUID FK to `users.id` with `ON DELETE SET NULL`.

Downgrade must remove all four columns.
