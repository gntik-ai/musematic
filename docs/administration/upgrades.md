# Upgrades

Upgrades cross three moving pieces: **Helm chart**, **Alembic
migrations**, and **feature flags**. This page walks through the
canonical upgrade flow.

## Pre-upgrade checklist

1. Read the changelog (`CHANGELOG.md`) and the commit log from the tag
   you're on to the tag you're moving to.
2. Back up **before** upgrading — see
   [Backup & Restore](backup-and-restore.md).
3. Review any new feature flags introduced since your current version
   ([Enabling Features](enabling-features.md)).
4. Read the diff in `apps/control-plane/migrations/versions/` — each
   new migration is one file; they apply in linear order.

## Upgrade flow (Kubernetes)

```bash
# 1. Pull the new chart/image
helm repo update

# 2. Run a dry run first to see what will change
helm upgrade musematic deploy/helm/platform \
  --namespace platform-control \
  --dry-run --debug \
  --values deploy/helm/platform/values.yaml \
  --version ${NEW_VERSION}

# 3. Apply
helm upgrade musematic deploy/helm/platform \
  --namespace platform-control \
  --values deploy/helm/platform/values.yaml \
  --version ${NEW_VERSION}

# 4. Run migrations (if new ones land)
make migrate

# 5. Verify
kubectl -n platform-control rollout status deployment/control-plane
curl https://your-domain/health
```

The Alembic chain is additive — migrations are numbered sequentially
and each one is reversible (`make migrate-rollback` rolls back one).

## Migration chain integrity

Always verify the chain before production upgrades:

```bash
make migrate-check
```

This runs `alembic branches --verbose` and fails if the migration graph
is non-linear (multiple heads).

## Feature-flag-gated changes

By convention (Brownfield Rule 8), every behaviour-changing upgrade
ships behind a feature flag defaulting to **off** for existing
installs. Example rollout sequence for a hypothetical "zero-trust
visibility" default change:

1. Upgrade the chart. New code runs with
   `VISIBILITY_ZERO_TRUST_ENABLED=false` — behaviour unchanged.
2. Flip the flag in a staging values file; verify.
3. Flip the flag in production values when ready.

This keeps upgrade and behaviour change as separate decisions.

## Rollback

Within one release:

```bash
helm rollback musematic <revision>
make migrate-rollback    # if a migration was applied
```

Between multiple releases, restore from backup per
[Backup & Restore](backup-and-restore.md). Alembic rollback across
multiple releases is possible with
`make migrate` or `alembic downgrade -N`, but Postgres data shapes
from newer schema versions may be lossy on older code — restore is
safer.

## Breaking changes

Principle 7 of the Brownfield Rules requires
backward-compatible APIs: new fields are optional with defaults,
existing endpoints keep working without caller changes. The project
has not (yet) shipped a release with deliberate breaking changes.

If and when one happens, it will be flagged in the `CHANGELOG.md` under
a **Breaking** heading and will come with a migration guide.

## Staying current

- Watch the GitHub releases for tagged versions.
- Subscribe to the `CHANGELOG.md` for human-readable change summary.
- Constitution amendments (rare) are published with a Sync Impact
  Report at the top of `.specify/memory/constitution.md`.

TODO(andrea): there is no consolidated "supported versions" policy
document. If you operate multiple installations, establish your own
version-skew policy (e.g. "no more than N-2 minor releases behind").
