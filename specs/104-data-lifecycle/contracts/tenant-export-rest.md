# Contract — Tenant Export REST

**Phase 1 output.** Routes under `/api/v1/admin/tenants/{tenant_id}/data-export/*`. Gated by `require_superadmin`.

The tenant admin's read-only counterpart is `/api/v1/me/tenant/data-export` (not implemented in v1; deferred — admin-only for v1).

---

## `POST /api/v1/admin/tenants/{tenant_id}/data-export`

Request a full tenant export.

**Request body**:

```json
{
  "include_workspaces": true,
  "include_users": true,
  "include_audit_chain": true,
  "include_cost_history": true,
  "delivery": {
    "method": "email_with_otp",  // or "email_and_sms" when feature flag enabled
    "encrypt_with_password": true
  }
}
```

**Response 202**:

```json
{
  "id": "uuid",
  "scope_type": "tenant",
  "scope_id": "uuid",
  "status": "pending",
  "estimated_completion": "2026-05-03T11:00:00Z",
  "estimated_size_bytes_lower_bound": 50000000000
}
```

**Behaviour**:
- Audits `data_lifecycle.export_requested` with `scope=tenant` and the actor (super admin id; double-audit if impersonating per rule 34).
- Generates a 32-char URL-safe password; password delivered out-of-band per R9.
- Emits `data_lifecycle.export.requested` Kafka event.

**Errors**:

| Status | Code |
|---|---|
| 403 | `not_superadmin` |
| 404 | `tenant_not_found` |
| 409 | `tenant_pending_deletion` (use phase-1 final-export instead) |
| 422 | `tenant_subscription_active` (when `delivery.method='email_and_sms'` requires UPD-077 SMS readiness) |

---

## `GET /api/v1/admin/tenants/{tenant_id}/data-export/jobs`

List recent tenant export jobs (admin queue view).

Same shape as workspace list endpoint but with `tenant_id` path scoping.

---

## `GET /api/v1/admin/tenants/{tenant_id}/data-export/jobs/{job_id}`

Same shape as workspace job-detail endpoint. The `output_url` returned to a super admin is signed for 30 days (vs 7 days for workspace exports). Each fetch issues a fresh URL and audits `data_lifecycle.export_url_issued`.

---

## ZIP layout (tenant scope)

```
metadata.json                         # tenant_id, slug, exported_at, format_version, schema URLs
tenant/
  tenant.json                         # registration, plan, settings (no secrets)
  dpa/
    dpa-v{n}.json                     # DPA history (metadata; raw PDF NOT included unless requested)
  subscription/
    subscription_history.json         # billing summary (UPD-052)
workspaces/
  {workspace_id}/
    [same as workspace-scope ZIP layout]
users/
  users.json                          # tenant-scoped users (members of tenant workspaces only)
audit/
  audit_chain.jsonl                   # tenant-scoped chronological audit entries
costs/
  cost_history.json                   # tenant cost rollups by month
README.md                             # how to read the export, decryption instructions
```

Encryption: ZIP is AES-256 password-protected (the password is the out-of-band-delivered string from R9). `output_url` requires the password in HTTP Basic-style auth header to download (S3 SSE-C).
