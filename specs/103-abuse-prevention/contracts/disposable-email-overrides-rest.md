# Contract — Disposable-Email Overrides REST

**Phase 1 output.** Defines the per-domain override list at `/api/v1/admin/security/email-overrides/*`. All routes gated by `require_superadmin`.

---

## `GET /api/v1/admin/security/email-overrides`

List overrides.

**Query params** (optional): `mode` (`block` | `allow`), `q` (substring match on domain).

**Response 200**:

```json
{
  "items": [
    { "domain": "legitimate-but-flagged.example", "mode": "allow", "reason": "...", "created_at": "...", "created_by_user_id": "..." },
    ...
  ]
}
```

The override list is **never** exposed via any non-superadmin route per the platform-private constraint in spec Assumptions and R2.

---

## `POST /api/v1/admin/security/email-overrides`

Add an override.

**Request body**:

```json
{
  "domain": "example.com",
  "mode": "allow",          // or "block"
  "reason": "Confirmed by support ticket #12345"
}
```

**Validation**:
- `domain` is lowercased, must match a basic FQDN regex (`^[a-z0-9.-]+$`, no protocol prefix, no path).
- `mode` ∈ `{block, allow}`.

**Behaviour**:
- Upserts on (`domain`) — re-adding a domain updates `mode` + `reason`.
- Audits the change with prior + new `mode` (NULL prior on first add).
- Invalidates the in-memory cache (the next disposable-email lookup re-reads).

**Errors**:

| Status | Code |
|---|---|
| 422 | `domain_invalid` |
| 422 | `mode_invalid` |

---

## `DELETE /api/v1/admin/security/email-overrides/{domain}`

Remove an override. The domain reverts to whatever the upstream blocklist says.

204 on success, 404 if absent (not idempotent — the 404 is informative, not a hard failure).

---

## `POST /api/v1/admin/security/email-overrides/refresh-blocklist`

Manually trigger the disposable-email upstream sync (which also runs weekly via cron). Returns 202 with a job id; the actual upstream fetch + DB upsert happens asynchronously.

**Response 202**:

```json
{ "job_id": "...", "started_at": "..." }
```

The job emits `abuse.threshold.changed` audit-chain entries when domains are added or removed (one entry per delta, batched in chunks of 100).

---

## Out-of-scope

- The signup-side disposable-email check itself is documented in `signup-guards-rest.md`.
- The `disposable_email_domains` upstream-managed table is not exposed via API — operators only manipulate the override list. Inspecting the upstream list happens via direct DB query or via the audit log of the cron's deltas.
