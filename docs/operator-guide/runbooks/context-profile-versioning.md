# Context Profile Versioning

## Rollback Flow

Each create or update writes a row in `context_engineering_profile_versions`.
Rollback is non-destructive: the selected historical snapshot is copied into a
new version, and previous versions remain unchanged.

## Revision Pinning

Agent revisions should reference the intended profile version at publication
time. Rolling back a profile creates a new current version but does not mutate
already-published revision snapshots.

## Storage Growth

Version rows store JSONB snapshots. Watch table growth for workspaces with
frequent profile edits and archive old profiles only after confirming no active
revision depends on them.

## Verification

Use the profile history endpoint to confirm monotonic version numbers and the
diff endpoint to inspect changes before rollback.
