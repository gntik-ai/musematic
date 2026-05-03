# Contract — Suspension REST

**Phase 1 output.** Defines the suspension queue + lift admin endpoints, and the login-side refusal contract that fires when a user with an active suspension authenticates.

---

## `GET /api/v1/admin/security/suspensions`

List suspensions. Default returns active (`lifted_at IS NULL`); `include_lifted=true` returns the full history.

**Query params**:

| Param | Type | Notes |
|---|---|---|
| `tenant_id` | UUID | Filter by tenant. |
| `reason` | string | Filter by reason code. |
| `suspended_by` | string | `system` / `super_admin` / `tenant_admin`. |
| `include_lifted` | bool | Default `false`. |
| `limit` | int | 1–200, default 50. |
| `cursor` | string | Opaque suspended_at timestamp. |

**Response 200**:

```json
{
  "items": [
    {
      "id": "...",
      "user_id": "...", "user_email": "...",
      "tenant_id": "...", "tenant_slug": "...",
      "reason": "repeated_velocity",
      "evidence_summary": { "rule": "...", "events": 7, "window_hours": 24 },
      "suspended_at": "...",
      "suspended_by": "system",
      "suspended_by_user_id": null,
      "lifted_at": null,
      "lifted_by_user_id": null,
      "lift_reason": null
    },
    ...
  ],
  "next_cursor": "..."
}
```

---

## `POST /api/v1/admin/security/suspensions`

Manually suspend a user.

**Request body**:

```json
{
  "user_id": "...",
  "reason": "manual_super_admin",
  "evidence": { "free_form": "..." }
}
```

**Behaviour**:
- Verifies the target is NOT in a privileged role (FR-744.3) — refuses with 403 `cannot_suspend_privileged_user` if so.
- Creates the suspension row, emits `abuse.suspension.applied`, audits, notifies the user via UPD-042.
- Returns 201 with the suspension row.

**Errors**:

| Status | Code |
|---|---|
| 403 | `cannot_suspend_privileged_user` |
| 404 | `user_not_found` |
| 409 | `user_already_suspended` (active row exists) |

---

## `POST /api/v1/admin/security/suspensions/{id}/lift`

Lift an active suspension.

**Request body**:

```json
{ "lift_reason": "False positive — Acme office NAT confirmed" }
```

**Behaviour**:
- Sets `lifted_at`, `lifted_by_user_id`, `lift_reason`.
- Notifies the user (`UPD-042`).
- Emits `abuse.suspension.lifted` + audit-chain entry.

**Errors**:

| Status | Code |
|---|---|
| 404 | `suspension_not_found` |
| 409 | `suspension_already_lifted` |

---

## Login-side refusal

The login endpoint at `apps/control-plane/src/platform/auth/router.py` (existing — UPD-014) gains a suspension-state check. The check happens AFTER credential validation passes — i.e., we confirm the credentials are valid, then refuse with a clear reason. Refusing before credential validation would create a credential-enumeration oracle.

**Response on suspended login**:

| Status | Code | Body |
|---|---|---|
| 403 | `account_suspended` | `{ "appeal_contact": "support@musematic.ai" }` |

The body **deliberately does NOT** include the suspension reason or evidence — leaking that to the suspended user would help them game the rules. The user is told only that the account is suspended and where to appeal. The detailed reason lives in the audit chain and the admin queue.

**Mid-session invalidation**: when a user with an active session is suspended, their next authenticated request is refused with the same `account_suspended` code via the auth-middleware. Existing sessions in Redis (`session:{user_id}:{session_id}`) are cleared on the suspension UPDATE (in the same transaction, with a Redis-side broadcast — fail-closed on Redis error).

**Privileged-role exemption — defense in depth**: the suspension service refuses to write a suspension row whose target user has any of `platform_admin`, `tenant_admin` roles. The auth middleware additionally checks the role on every request — if a future bug allows a privileged-user suspension row to land, the middleware ignores it for those roles. (The fix would be to clear the orphaned row, not to lock out the operator.)
