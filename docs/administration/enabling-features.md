# Enabling Features

musematic uses **environment-variable-driven feature flags** declared on
Pydantic Settings classes in
[`apps/control-plane/src/platform/common/config.py`][cfg]. There is no
database-backed feature-flag table — every toggle is set at process
start and requires a restart to change.

## Feature-flag catalogue

| Flag | Default | Scope | Where it lives |
|---|---|---|---|
| `CONNECTOR_WORKER_ENABLED` | `true` | platform | `config.py` — `ConnectorsSettings` |
| `MEMORY_CONSOLIDATION_ENABLED` | `true` | platform | `config.py` — `MemorySettings` |
| `MEMORY_CONSOLIDATION_LLM_ENABLED` | `false` | platform | `config.py` — `MemorySettings` |
| `MEMORY_DIFFERENTIAL_PRIVACY_ENABLED` | `false` | platform | `config.py` — `MemorySettings` |
| `SIMULATION_DEFAULT_STRICT_ISOLATION` | `true` | platform | `config.py` — `SimulationSettings` |
| `VISIBILITY_ZERO_TRUST_ENABLED` | `false` | platform | `config.py` — `VisibilitySettings` |

See [Installation › Environment variables](../installation.md#environment-variables)
for the complete variable reference.

## How to toggle a feature

### Kubernetes / Helm

Edit `deploy/helm/platform/values.yaml`:

```yaml
controlPlane:
  env:
    VISIBILITY_ZERO_TRUST_ENABLED: "true"
    MEMORY_CONSOLIDATION_LLM_ENABLED: "false"
```

Apply with `helm upgrade`. Pods roll out and pick up the new values on
restart.

### Docker / local

Export before starting the process:

```bash
export VISIBILITY_ZERO_TRUST_ENABLED=true
uvicorn src.platform.main:app --port 8000
```

## Key feature-flag details

### `VISIBILITY_ZERO_TRUST_ENABLED`

Disabled by default for backward compatibility. When `true`, a newly
registered agent sees zero agents and zero tools until its
`visibility_agents` / `visibility_tools` patterns are configured.
Principle IX of the [constitution][const] mandates this for new
deployments; existing deployments are expected to enable this during
gradual rollout.

See [spec 053][s053].

### `MEMORY_CONSOLIDATION_ENABLED` / `MEMORY_CONSOLIDATION_LLM_ENABLED`

- `MEMORY_CONSOLIDATION_ENABLED=true` (default) — the consolidation
  worker runs every `MEMORY_CONSOLIDATION_INTERVAL_MINUTES` (default 15)
  and merges similar memories when clusters exceed
  `MEMORY_CONSOLIDATION_MIN_CLUSTER_SIZE` (default 3) with similarity
  above `MEMORY_CONSOLIDATION_CLUSTER_THRESHOLD` (default 0.85).
- `MEMORY_CONSOLIDATION_LLM_ENABLED=true` — uses an LLM for
  summarisation during consolidation. Costs tokens; off by default.

### `MEMORY_DIFFERENTIAL_PRIVACY_ENABLED`

Disabled by default. When `true`, memory queries have differential
privacy noise applied at `MEMORY_DIFFERENTIAL_PRIVACY_EPSILON` (default
`1.0`). Affects retrieval accuracy — enable deliberately.

### `CONNECTOR_WORKER_ENABLED`

Enabled by default. Disable to stop the outbound connector delivery
worker from running — useful during maintenance or when draining
Kafka backlog manually.

### `SIMULATION_DEFAULT_STRICT_ISOLATION`

Enabled by default. Controls whether simulations default to strict
network isolation (no egress). Principle VII of the constitution
forbids simulation code from reaching production namespaces.

## Signup mode — a non-flag toggle that admins should know

`ACCOUNTS_SIGNUP_MODE` (not a boolean flag but commonly conflated)
switches the account-registration flow:

| Value | Behaviour |
|---|---|
| `open` (default) | Self-registration without approval. |
| `invite_only` | Only invited users can register. |
| `admin_approval` | Users register but land in a pending-approval queue; `workspace_admin` or `platform_admin` approves via `POST /api/v1/accounts/{user_id}/approve`. |

## Things that are NOT feature-flagged

The following are not admin-togglable; they are compile-time or
principle-time decisions:

- Principle enforcement (bounded-context isolation, append-only journal,
  etc.) — see [`.specify/memory/constitution.md`][const].
- Kafka event envelope format.
- Core RBAC model (the 10 global roles and 4 workspace-scoped roles).
- Agent FQN format.
- S3 generic-protocol object storage (principle XVI forbids alternatives
  in app code).

Changing any of these is a constitutional amendment, not a flag flip.

[cfg]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/src/platform/common/config.py
[const]: https://github.com/gntik-ai/musematic/blob/main/.specify/memory/constitution.md
[s053]: https://github.com/gntik-ai/musematic/tree/main/specs/053-zero-trust-visibility
