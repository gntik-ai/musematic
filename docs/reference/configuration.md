# Configuration Reference

This page is a consolidated cross-reference for every configuration surface
musematic exposes. It is split by **audience**:

- **End-user configs** — things you author inside a workspace: agent
  manifests, workflow YAML.
- **Administrator / platform configs** — environment variables, feature
  flags, role grants, Helm values. Read at process start; require a
  restart to change.

## End-user configuration

### Agent manifest

Full field-by-field reference in [Agents](../agents.md#manifest-schema).
At a glance:

| Field | Required | Location |
|---|---|---|
| `local_name`, `version`, `purpose`, `role_types` | ✅ | Manifest top-level |
| `approach`, `maturity_level`, `reasoning_modes`, `context_profile`, `tags`, `display_name`, `custom_role_description` | — | Manifest top-level |

Registered via `POST /api/v1/registry/namespaces/{namespace}/agents/upload`.
Visibility and tags are updated with `PATCH /api/v1/registry/agents/{id}`.

### Workflow definition (YAML)

Full field-by-field reference in [Flows](../flows.md#step-shape). At a
glance:

| Field | Required | Location |
|---|---|---|
| `schema_version`, `steps[].id`, `steps[].step_type` | ✅ | YAML top-level + per step |
| `steps[].agent_fqn` | conditional | Required when `step_type: agent_task` |
| `steps[].tool_fqn` | conditional | Required when `step_type: tool_call` |
| `steps[].approval_config` | conditional | Required when `step_type: approval_gate` |
| `steps[].depends_on`, `input_bindings`, `output_schema`, `retry_config`, `timeout_seconds`, `compensation_handler`, `reasoning_mode`, `context_budget_tokens`, `parallel_group`, `condition_expression` | — | Per step |

Authoritative JSON Schema:
[`apps/control-plane/src/platform/workflows/schemas/v1.json`](https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/src/platform/workflows/schemas/v1.json).

## Administrator configuration

### Environment variables (complete index)

See [Installation › Environment variables](../installation.md#environment-variables)
for the complete 130+ variable reference grouped by category. Summary of
the categories:

- Core platform: Postgres, Redis, Kafka, S3/MinIO, Qdrant, Neo4j,
  ClickHouse, OpenSearch
- Auth: JWT, MFA, lockout, sessions
- Accounts: signup mode, email verification, invitations
- Workspaces: default limits and naming
- WebSocket hub
- Observability: OTEL
- gRPC satellites: runtime controller, reasoning engine, sandbox
  manager, simulation controller (addresses + service-specific knobs)
- Registry, memory, context engineering, interactions, connectors,
  trust, agentops, composition, discovery, simulation, analytics
- Feature flags
- Platform profile
- Operations CLI
- Web frontend

### Feature flags

Catalogue in [Administration › Enabling Features](../administration/enabling-features.md).

### RBAC roles and permissions

- 10 global roles (`RoleType`) — see
  [Administration › RBAC & Permissions](../administration/rbac-and-permissions.md).
- 4 workspace-scoped roles (`WorkspaceRole`) — owner, admin, member,
  viewer.
- Permissions seeded by Alembic migration 002.

### Helm values

The Helm chart under [`deploy/helm/platform/`][chart] exposes a
`values.yaml` file that threads through to the env vars above. Key
sections:

```yaml
controlPlane:
  replicaCount: 1
  image:
    repository: ghcr.io/gntik-ai/musematic-control-plane
    tag: ${RELEASE_TAG}
  env:
    # …see Installation for the complete list…
    POSTGRES_DSN: ...
    REDIS_URL: ...

runtimeController:
  replicaCount: 1
  image:
    repository: ghcr.io/gntik-ai/musematic-runtime-controller
    tag: ${RELEASE_TAG}
  env:
    GRPC_PORT: "50051"
    WARM_POOL_TARGETS: "executor=3,judge=1"

reasoningEngine:
  # …

sandboxManager:
  # …

simulationController:
  # …

web:
  # Next.js frontend — public env vars go here
  env:
    NEXT_PUBLIC_API_URL: https://api.example.com
```

TODO(andrea): the actual canonical `values.yaml` shape on main uses a
specific schema; this is a best-effort outline. Confirm by reading the
chart's own `values.yaml` and `Chart.yaml`.

### Kubernetes namespaces

See [Installation › Kubernetes namespaces](../installation.md#kubernetes-namespaces).

### Glossary

| Term | Meaning |
|---|---|
| **FQN** | Fully Qualified Name — `namespace:local_name` agent identifier. |
| **GID** | Goal ID — correlation dimension for workspace goals. |
| **Bounded context** | A self-contained module in the control plane owning its own tables (principle IV). |
| **Runtime profile** | One of `api`, `ws-hub`, `worker`, `scheduler`, etc. — selected via `PLATFORM_PROFILE`. |
| **Task plan** | Structured plan the agent produces before execution; persisted as `TaskPlanRecord`. |
| **Journey (tests)** | Multi-step user-persona E2E test crossing several bounded contexts (spec 072). |
| **Governance chain** | Observer → Judge → Enforcer chain gating agent output. |
| **Warm pool** | Pre-warmed agent pods held by the runtime controller for fast dispatch. |

[chart]: https://github.com/gntik-ai/musematic/tree/main/deploy/helm
