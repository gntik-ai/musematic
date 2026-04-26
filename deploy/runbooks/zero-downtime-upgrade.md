# Zero-Downtime Upgrade Procedure

Use this procedure for service, schema, and runtime changes that should not require maintenance mode. Maintenance mode is reserved for rollback-fails-too cases or known write-incompatible work.

## Rolling stateless services

- Use Kubernetes rolling updates with readiness probes enabled for `api`, `scheduler`, `worker`, `projection-indexer`, `ws-hub`, and other stateless profiles.
- Set `maxUnavailable: 0` for API-facing profiles and allow controlled `maxSurge` so at least one healthy replica serves traffic throughout the rollout.
- Verify `/health`, core API reads, websocket connection establishment, and queue processing after each profile rolls.
- Roll back with `kubectl rollout undo deployment/<name>` and repeat the same readiness checks.

## Expand-migrate-contract

1. Expand: add new tables or nullable/additive columns with Alembic before code writes to them.
2. Migrate: deploy code that dual-writes or backfills the old and new shapes. Verify with the Helm migration check and read-side probes.
3. Contract: drop the old shape in a later release only after both old and new code can read the new shape and the rollback window has closed.

For renames, never rename in place. Add the new column, dual-write both names, migrate readers, then drop the old column in a later migration.

## Agent runtime versioning

- Deploy the new runtime alongside the existing runtime through the runtime-controller and warm-pool routing surface.
- Keep existing executions pinned to their original runtime version.
- Route new executions to the new version only after readiness and sandbox checks pass.
- Keep the coexistence window documented in the operator dashboard upgrade status.

## Rollback

- Service rollback: `kubectl rollout undo`, then verify health and queue drain.
- Schema rollback: stop new writes to the expanded shape, keep dual-write compatibility, and revert application readers before any contract step.
- Runtime rollback: route new executions back to the previous runtime and let already-started executions finish on their pinned version.

## Rollback-fails-too

If a rollback step fails, schedule or enable maintenance mode with an explicit announcement, keep reads available, and stop initiating new writes until the failed rollback branch is resolved. Record the incident, link the failed run, and attach the operator decision to the audit chain.

