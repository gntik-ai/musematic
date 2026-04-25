# Provider Credentials + Rotation Contract

**Feature**: 075-model-catalog-fallback
**Module**: `apps/control-plane/src/platform/model_catalog/services/credential_service.py`

## Purpose

Per-workspace provider credentials stored as Vault path references.
Rotation delegates entirely to UPD-024's
`secret_rotation_schedules` + `RotatableSecretProvider` pattern; this
feature adds the workspace/provider scoping layer on top.

## REST endpoints

| Method + path | Purpose | Role |
|---|---|---|
| `POST /api/v1/model-catalog/credentials` | Register provider credential for a workspace | `platform_admin`, `superadmin` |
| `GET /api/v1/model-catalog/credentials?workspace_id=` | List credentials | `auditor`, `platform_admin`, `superadmin` |
| `PATCH /api/v1/model-catalog/credentials/{id}/vault-ref` | Update vault_ref (re-point) | `platform_admin`, `superadmin` |
| `DELETE /api/v1/model-catalog/credentials/{id}` | De-register | `platform_admin`, `superadmin` |
| `POST /api/v1/model-catalog/credentials/{id}/rotate` | Trigger rotation via UPD-024 | `platform_admin`, `superadmin` |

## Request / response shapes

### `POST /credentials`

```json
{
  "workspace_id": "<UUID>",
  "provider": "openai" | "anthropic" | "google" | "mistral",
  "vault_ref": "secret/data/musematic/prod/providers/{ws_id}/openai"
}
```

The `vault_ref` MUST already point at a populated Vault path; the
endpoint verifies accessibility by attempting a read and returning
`400 Bad Request` if the path is empty or inaccessible. **The API key
itself is never submitted in the request body** — it must be placed
in Vault out-of-band (via `ops-cli vault put`, Terraform, etc.).

### `POST /credentials/{id}/rotate`

```json
{
  "overlap_window_hours": 24,
  "emergency": false,
  "justification": "..."
}
```

Response (rule 44 — never echoes secret):

```json
{
  "rotation_schedule_id": "<UUID>",
  "rotation_state": "rotating",
  "overlap_ends_at": "<ISO8601>"
}
```

Emergency rotation (`emergency: true`) with `overlap_window_hours: 0`
requires 2PA per constitution rule 33 — the endpoint rejects with
`400` if the requester has not also submitted a second approval via
UPD-024's rotation workflow.

## Router integration

The router resolves credentials at dispatch time:

```python
# common/clients/model_router.py
async def _resolve_credential(self, workspace_id: UUID, provider: str) -> str:
    cred_row = await credential_service.get_by_workspace_provider(
        workspace_id, provider
    )
    if cred_row is None:
        raise CredentialNotConfiguredError(
            f"workspace {workspace_id} has no credential for {provider}"
        )
    # Delegate to UPD-024's provider — handles rotation overlap
    return await rotatable_secret_provider.get_current(cred_row.vault_ref)
```

During an active rotation overlap, `RotatableSecretProvider.validate_either(...)`
accepts BOTH current and previous credentials for incoming auth checks
(UPD-024 contract); for outgoing calls, the router always injects
`current`.

## Vault path scheme

`secret/data/musematic/{env}/providers/{workspace_id}/{provider}`

Values: see `data-model.md` §4.

## Unit-test contract

- **CR1** — register credential: row created referencing Vault path;
  raw key never in DB.
- **CR2** — register with empty Vault path: 400 rejected.
- **CR3** — router credential resolution: correct credential injected
  as `Authorization: Bearer <key>` header; Bearer value never logged.
- **CR4** — workspace isolation: credentials scoped per workspace;
  cross-workspace resolution rejected.
- **CR5** — rotation delegation: `POST /rotate` creates an entry in
  `secret_rotation_schedules` (UPD-024) and returns the rotation ID.
- **CR6** — zero-downtime: during rotation overlap, 100 concurrent
  router calls succeed (shared test with SR6 from UPD-024 contracts).
- **CR7** — emergency rotation 2PA: single-approver emergency rejected;
  second approval succeeds.
