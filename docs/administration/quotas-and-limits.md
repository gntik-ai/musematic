# Quotas & Limits

Every quota and rate limit in musematic is an environment-variable-driven
setting applied at startup. There is no runtime-editable quota table
(TODO(andrea): [spec 018][s018] mentions per-user workspace limits but
does not expose an admin endpoint for changing the cap — today the
default comes from `User.max_workspaces` and defaults to the global
`WORKSPACES_DEFAULT_LIMIT`).

## Per-user limits

| Limit | Default | Setting | Source |
|---|---|---|---|
| Max workspaces per user | `0` (unlimited) | `WORKSPACES_DEFAULT_LIMIT` | [`config.py` — `WorkspacesSettings`][cfg] |
| Max workspaces (per user override) | (none) | `User.max_workspaces` column | [`accounts/models.py`][accts] |

Enforcement: `WorkspacesService.create_workspace()` rejects creation with
`LimitExceededError` once the user's workspace count reaches their
configured max. The per-user override takes precedence over the global
default. `0` means unlimited.

## Per-workspace limits

The data model does not currently expose per-workspace resource caps
(agents, executions, storage). Feature [spec 018][s018] lists these as
part of the workspace settings surface but the code inspection shows
them not yet wired.

TODO(andrea): confirm whether `Workspace.settings` JSONB holds an
`agent_limit`, `execution_limit`, `storage_limit_bytes` triple, or
whether these are still pending implementation.

## Rate limits

### Authentication lockout

Failed login attempts trigger a Redis-backed lockout:

| Setting | Default | Purpose |
|---|---|---|
| `AUTH_LOCKOUT_THRESHOLD` | `5` | Failed attempts before lockout. |
| `AUTH_LOCKOUT_DURATION` | `900` seconds (15 min) | Lockout window length. |

Redis keys:

- `auth:lockout:{user_id}` — counter.
- `auth:locked:{user_id}` — lock flag (TTL = `AUTH_LOCKOUT_DURATION`).

Clear a lockout administratively with
`POST /api/v1/accounts/{user_id}/unlock`.

### Email verification resend

| Setting | Default | Purpose |
|---|---|---|
| `ACCOUNTS_RESEND_RATE_LIMIT` | `3` | Max resends per session. |

### Memory API

| Setting | Default | Purpose |
|---|---|---|
| `MEMORY_RATE_LIMIT_PER_MIN` | `60` | Per-principal memory embeddings per minute. |
| `MEMORY_RATE_LIMIT_PER_HOUR` | `500` | Per-principal memory embeddings per hour. |

### Connector delivery

| Setting | Default | Purpose |
|---|---|---|
| `CONNECTOR_DELIVERY_MAX_CONCURRENT` | `10` | Max concurrent outbound deliveries. |
| `CONNECTOR_MAX_PAYLOAD_SIZE_BYTES` | `1048576` | Max connector payload (1 MiB). |

### Registry package size

| Setting | Default | Purpose |
|---|---|---|
| `REGISTRY_PACKAGE_SIZE_LIMIT_MB` | `50` | Max agent package size (MB). |
| `REGISTRY_MAX_FILE_COUNT` | `256` | Max files per package. |
| `REGISTRY_MAX_DIRECTORY_DEPTH` | `10` | Max nesting depth in a package. |

## Timeouts

| Setting | Default | Purpose |
|---|---|---|
| `COMPOSITION_LLM_TIMEOUT_SECONDS` | `25.0` | LLM API request timeout for agent composition. |
| `DEFAULT_TIMEOUT` (sandbox-manager) | `30s` | Default sandbox exec timeout. |
| `MAX_TIMEOUT` (sandbox-manager) | `300s` | Hard ceiling on requested timeouts. |
| `DISCOVERY_EXPERIMENT_SANDBOX_TIMEOUT_SECONDS` | `120` | Discovery experiment sandbox timeout. |
| `SIMULATION_MAX_DURATION_SECONDS` | `1800` | Per-simulation wall-clock cap (30 min). |
| `HEARTBEAT_TIMEOUT` (runtime-controller) | `60s` | Pod heartbeat liveness. |

## Changing a quota or limit

All limits above are environment variables. Edit
`deploy/helm/platform/values.yaml`, apply with `helm upgrade`, and pods
pick up new values on restart.

For per-user workspace overrides (the `User.max_workspaces` column)
there is currently no admin API — the value is set at user creation via
the internal seeder. TODO(andrea): add a
`PATCH /api/v1/accounts/{user_id}` endpoint accepting `max_workspaces`
so admins can raise an individual user's cap without editing the
database directly.

[cfg]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/src/platform/common/config.py
[accts]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/src/platform/accounts/models.py
[s018]: https://github.com/gntik-ai/musematic/tree/main/specs/018-workspaces-bounded-context
