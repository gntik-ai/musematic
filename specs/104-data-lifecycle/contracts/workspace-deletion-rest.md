# Contract — Workspace Deletion REST

**Phase 1 output.** Routes under `/api/v1/workspaces/{workspace_id}/deletion-jobs/*` and the public-but-anti-enumerated `/api/v1/workspaces/cancel-deletion/{token}`. RBAC: only workspace **owner** may schedule deletion (workspace admins cannot).

Two-phase workflow:
1. **Phase 1** — owner submits typed confirmation. Status flips to `pending_deletion`. Cancel link valid for `grace_period_days` (default 7).
2. **Phase 2** — `grace_monitor` cron, after grace expiry, advances the job to `phase_2`, dispatches the cascade via the privacy `CascadeOrchestrator`, writes a tombstone, transitions workspace to `deleted`.

---

## `POST /api/v1/workspaces/{workspace_id}/deletion-jobs`

Request workspace deletion. Owner-only.

**Request body**:

```json
{
  "typed_confirmation": "delete acme-pro-workspace",
  "reason": "...optional free text..."
}
```

The `typed_confirmation` MUST exactly match the workspace's slug (case-sensitive). This is the deliberate-action gate from US2.

**Response 202**:

```json
{
  "id": "uuid",
  "scope_type": "workspace",
  "scope_id": "uuid",
  "phase": "phase_1",
  "grace_period_days": 7,
  "grace_ends_at": "2026-05-10T10:00:00Z",
  "cancel_link_emailed_to": "owner-redacted@example.com"
}
```

**Behaviour**:
- Generates a 32-byte URL-safe cancel token; SHA-256 hash stored in `deletion_jobs.cancel_token_hash`; plaintext sent via UPD-077 email channel.
- Workspace status flips to `pending_deletion`. All write APIs against the workspace return 423 `workspace_pending_deletion`.
- Audits `data_lifecycle.workspace_deletion_phase_1`.
- Emits `data_lifecycle.deletion.requested` Kafka event.

**Errors**:

| Status | Code |
|---|---|
| 400 | `typed_confirmation_mismatch` |
| 403 | `not_workspace_owner` |
| 409 | `deletion_job_already_active` (per partial-unique-index) |
| 423 | `workspace_pending_deletion` (already pending) |

---

## `GET /api/v1/workspaces/{workspace_id}/deletion-jobs/{job_id}`

Returns deletion job state. Owner + workspace admin readable.

**Response 200**:

```json
{
  "id": "uuid",
  "phase": "phase_1",
  "grace_ends_at": "...",
  "cascade_started_at": null,
  "cascade_completed_at": null,
  "tombstone_id": null,
  "abort_reason": null
}
```

`abort_reason` is omitted for non-superadmin readers.

---

## `POST /api/v1/workspaces/cancel-deletion/{token}`

Anti-enumeration cancel endpoint per R10. Always returns 200 with the same body, regardless of token validity.

**Response 200**:

```json
{
  "message": "If the link was valid, deletion has been cancelled. Check your email for confirmation."
}
```

**Behaviour** (server-side branches, never reflected in response):
- Token valid + unused + job in `phase_1` + not expired: flip job to `aborted`, restore workspace to `active`, emit `data_lifecycle.deletion.aborted`, audit `data_lifecycle.workspace_deletion_aborted`, send confirmation email.
- Token valid but already used: audit `data_lifecycle.cancel_token_invalid` (subtype `already_used`), no-op.
- Token invalid: audit `data_lifecycle.cancel_token_invalid` (subtype `unknown`), no-op.
- Token expired: audit `data_lifecycle.cancel_token_invalid` (subtype `expired`), no-op.

---

## Internal: `POST /api/v1/admin/data-lifecycle/deletion-jobs/{id}/abort`

Super-admin abort during phase-1. Returns 409 if cascade has begun. See [tenant-deletion-rest.md](./tenant-deletion-rest.md) for the shared admin-side abort surface.
