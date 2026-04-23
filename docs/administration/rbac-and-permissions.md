# RBAC & Permissions

Authentication ([spec 014][s014]) and authorisation are handled by the
`auth` and `accounts` bounded contexts. Access control has two axes:

1. **Global roles** — 10 roles declared in the `RoleType` enum.
2. **Workspace-scoped roles** — 4 roles declared in the `WorkspaceRole`
   enum, assigned via the `Membership` model.

A user may carry multiple roles across scopes (e.g. `platform_admin`
globally plus `workspace_owner` of workspace A).

## Global roles (`RoleType`)

Defined in [`apps/control-plane/src/platform/auth/schemas.py`][schemas]:

| Role | Scope | Default permissions (from migration 002) |
|---|---|---|
| `superadmin` | global | `resource_type: *`, `action: *` — wildcard across everything. |
| `platform_admin` | global | `resource_type: [workspace, user, agent, connector]`, `action: [read, write, delete, admin]`. |
| `workspace_owner` | workspace | `resource_type: [workspace, agent, workflow, connector]`, `action: [read, write, delete, admin]` within the owned workspace. |
| `workspace_admin` | workspace | `resource_type: [agent, workflow, connector, interaction]`, `action: [read, write, delete]`. |
| `creator` | workspace | `resource_type: [agent, workflow, prompt, evaluation]`, `action: [read, write]`. |
| `operator` | workspace | `resource_type: [agent, workflow, execution, fleet]`, `action: [read, write]`. |
| `viewer` | workspace | `resource_type: [agent, workflow, execution, analytics]`, `action: [read]`. |
| `auditor` | workspace | `resource_type: [audit, analytics, trust, execution]`, `action: [read]`. |
| `agent` | own | Internal identity for agent-to-agent / agent-to-service calls. `resource_type: [execution, memory, tool]`, `action: [read, write]`. |
| `service_account` | workspace (optional) | Per-credential role grants; created by `platform_admin`. |

!!! note
    The permission grants above are seeded by database migration 002
    (`apps/control-plane/migrations/versions/002_*`). Run
    `make migrate` during installation to apply them.

## Workspace-scoped membership roles (`WorkspaceRole`)

Defined in [`apps/control-plane/src/platform/workspaces/models.py`][wsmodels]
as `WorkspaceRole`, persisted on the `Membership` model:

| Role | Typical actions inside the workspace |
|---|---|
| `owner` | Full control — can delete the workspace. Auto-assigned to the creator. |
| `admin` | Add/remove members, change roles, manage agents/workflows/connectors. |
| `member` | Register agents and workflows, run executions, open goals. |
| `viewer` | Read-only access to agents, workflows, and execution history. |

A user becomes a member via:

```http
POST /api/v1/workspaces/{workspace_id}/members
Content-Type: application/json

{ "user_id": "...", "role": "member" }
```

Only `workspace_owner` and `workspace_admin` can add members
([spec 018][s018]).

## The permission model

The `RBACEngine`
([`apps/control-plane/src/platform/auth/rbac.py`][rbac]) resolves access
decisions by walking:

```
user → role assignments → role permissions → (resource_type, action, scope)
```

Scopes:

- `global` — permission applies everywhere.
- `workspace` — permission applies when the assignment's `workspace_id`
  matches the requested `workspace_id`.
- `own` — permission applies to resources owned by the principal
  (typically an agent or service account).

Wildcards: `resource_type: "*"` and `action: "*"` match anything; they
are reserved for `superadmin`.

## Admin API — user lifecycle

All of the following require `workspace_admin`, `platform_admin`, or
`superadmin`:

| Action | Endpoint |
|---|---|
| List pending approvals | `GET /api/v1/accounts/pending-approvals` |
| Approve a pending user | `POST /api/v1/accounts/{user_id}/approve` |
| Reject a pending user | `POST /api/v1/accounts/{user_id}/reject` |
| Suspend a user | `POST /api/v1/accounts/{user_id}/suspend` |
| Reactivate a suspended user | `POST /api/v1/accounts/{user_id}/reactivate` |
| Block a user | `POST /api/v1/accounts/{user_id}/block` |
| Unblock a user | `POST /api/v1/accounts/{user_id}/unblock` |
| Clear an auth lockout | `POST /api/v1/accounts/{user_id}/unlock` |
| Reset a user's MFA | `POST /api/v1/accounts/{user_id}/reset-mfa` |
| Create invitations | `POST /api/v1/accounts/invitations` |
| List invitations | `GET /api/v1/accounts/invitations` |
| Revoke an invitation | `DELETE /api/v1/accounts/invitations/{invitation_id}` |

Lifecycle state machine ([spec 016][s016]):

```
pending_verification ─▶ pending_approval ─▶ active
                                           ↕
                                          suspended
                                           ↕
                                          blocked ─▶ archived
```

## Service accounts

Created by `platform_admin` or `superadmin`:

```http
POST /api/v1/auth/service-accounts
Content-Type: application/json

{
  "name": "ci-publisher",
  "roles": ["creator"],
  "workspace_id": "..."
}
```

The response includes an API key prefixed `msk_…`. Keys are **Argon2id
hashed** at rest and returned **once** — store them in your secret
manager immediately.

Rotation:

```http
POST /api/v1/auth/service-accounts/{sa_id}/rotate
```

Returns a new key; the old key enters a grace period before expiring.

Revocation:

```http
DELETE /api/v1/auth/service-accounts/{sa_id}
```

## Creating a custom role

The platform does not currently expose a dynamic
"create-custom-role" endpoint. Roles are seeded via Alembic migrations
under `apps/control-plane/migrations/versions/`. To introduce a new
role:

1. Add the role name to the `RoleType` enum ([auth schemas][schemas]).
2. Write a new Alembic migration adding grants for that role to the
   `role_permissions` table.
3. Run `make migrate`.
4. Assign the new role to users via the existing role-assignment API.

TODO(andrea): surface this as a runtime admin API so custom roles can be
added without schema changes.

[schemas]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/src/platform/auth/schemas.py
[wsmodels]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/src/platform/workspaces/models.py
[rbac]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/src/platform/auth/rbac.py
[s014]: https://github.com/gntik-ai/musematic/tree/main/specs/014-auth-bounded-context
[s016]: https://github.com/gntik-ai/musematic/tree/main/specs/016-accounts-bounded-context
[s018]: https://github.com/gntik-ai/musematic/tree/main/specs/018-workspaces-bounded-context
