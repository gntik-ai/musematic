# Migration Sequence — UPD-041 OAuth Env Bootstrap

Date: 2026-04-27

Highest migration present before UPD-041 implementation:

- `068_pending_profile_completion.py`
- revision id: `068_pending_profile_completion`
- down revision: `067_admin_workbench`

UPD-041 therefore uses:

- migration file: `apps/control-plane/migrations/versions/069_oauth_provider_env_bootstrap.py`
- revision id: `069_oauth_provider_env_bootstrap`
- down revision: `068_pending_profile_completion`

The migration adds:

- `oauth_providers.source`
- `oauth_providers.last_edited_by`
- `oauth_providers.last_edited_at`
- `oauth_providers.last_successful_auth_at`
- new table `oauth_provider_rate_limits`
