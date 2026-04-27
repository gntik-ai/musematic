# UPD-043 Migration Sequence

Date: 2026-04-27

## Current Sequence

The highest existing Alembic migration in `apps/control-plane/migrations/versions/` is:

- `070_user_self_service_extensions.py`

## UPD-043 Assignment

UPD-043 uses:

- `071_workspace_owner_workbench.py`

The migration must add the workspace-owner settings columns:

- `workspaces_settings.quota_config` as JSONB with default `{}`.
- `workspaces_settings.dlp_rules` as JSONB with default `{}`.
- `workspaces_settings.residency_config` as JSONB with default `{}`.

2PA migration handling needs care because `067_admin_workbench.py` already created `two_person_auth_requests`. A new table must be justified against that existing schema before it is added.
