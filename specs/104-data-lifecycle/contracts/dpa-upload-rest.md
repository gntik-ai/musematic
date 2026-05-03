# Contract — DPA Upload REST

**Phase 1 output.** Routes under `/api/v1/admin/dpa/*`. Gated by `require_superadmin`.

DPA columns on `tenants` already exist (`dpa_signed_at`, `dpa_version`, `dpa_artifact_uri`, `dpa_artifact_sha256`); this BC is the writer of those columns and the steward of the Vault path.

---

## `POST /api/v1/admin/tenants/{tenant_id}/dpa`

Upload a DPA PDF for an Enterprise tenant.

**Request**: `multipart/form-data`
- `file`: PDF (≤ 50 MB; `Content-Type: application/pdf`)
- `version`: string (e.g., `v3.0`); MUST be unique per tenant
- `effective_date`: ISO date

**Behaviour**:
1. Validate file size, MIME type, and that the leading bytes are `%PDF-` (cheap header check).
2. Submit to ClamAV for scanning (R3). 25 s timeout.
   - Infected: return 422 `dpa_virus_detected` with the signature name. Audit `data_lifecycle.dpa_rejected_virus`. Vault is not written.
   - Scanner unreachable: return 503 `dpa_scan_unavailable`. Audit `data_lifecycle.dpa_scan_unavailable`. Vault is not written.
3. Compute SHA-256 of the cleartext bytes.
4. Write the PDF (base64) to Vault path `secret/data/musematic/{env}/tenants/{slug}/dpa/dpa-{version}.pdf` with metadata.
5. Update `tenants` row: `dpa_signed_at = effective_date`, `dpa_version = version`, `dpa_artifact_uri = <vault path>`, `dpa_artifact_sha256 = <hash>`.
6. Emit `data_lifecycle.dpa.uploaded` event + audit `data_lifecycle.dpa_uploaded`.

**Response 201**:

```json
{
  "tenant_id": "uuid",
  "version": "v3.0",
  "effective_date": "2026-05-03",
  "sha256": "abcdef...",
  "vault_path": "secret/data/musematic/prod/tenants/acme/dpa/dpa-v3.0.pdf"
}
```

**Errors**:

| Status | Code |
|---|---|
| 400 | `dpa_pdf_invalid` (bad MIME or magic bytes) |
| 403 | `not_superadmin` |
| 409 | `dpa_version_already_exists` |
| 413 | `dpa_too_large` (>50 MB) |
| 422 | `dpa_virus_detected` |
| 503 | `dpa_scan_unavailable` |

---

## `GET /api/v1/admin/tenants/{tenant_id}/dpa`

List historical DPA versions.

**Response 200**:

```json
{
  "active": {
    "version": "v3.0",
    "signed_at": "2026-05-03T00:00:00Z",
    "sha256": "abcdef..."
  },
  "history": [
    { "version": "v2.0", "signed_at": "2025-09-15T00:00:00Z", "sha256": "..." },
    { "version": "v1.0", "signed_at": "2024-12-01T00:00:00Z", "sha256": "..." }
  ]
}
```

History is reconstructed from audit chain entries (`event_type='data_lifecycle.dpa_uploaded'`) — historical Vault paths are NOT enumerated through this API to limit historical-DPA discoverability.

---

## `GET /api/v1/admin/tenants/{tenant_id}/dpa/{version}/download`

Download a specific DPA version (active or historical).

**Response 200**:
- `Content-Type: application/pdf`
- `Content-Disposition: attachment; filename=dpa-{tenant_slug}-{version}.pdf`
- Body: cleartext PDF bytes

**Behaviour**:
- Reads the Vault path; verifies SHA-256 matches `tenants.dpa_artifact_sha256` (active) or audit-recorded hash (historical).
- Audits `data_lifecycle.dpa_downloaded` with actor + version.

**Errors**:

| Status | Code |
|---|---|
| 403 | `not_superadmin` |
| 404 | `dpa_version_not_found` |
| 502 | `vault_unreachable` |

---

## `GET /api/v1/me/tenant/dpa`

Tenant-admin self-service: view their own tenant's active DPA metadata + download.

Same response shape as the admin endpoint, but:
- Does NOT include `vault_path` field.
- Only returns the **active** version (no history listing).
- Audits `data_lifecycle.dpa_downloaded` with `actor_role='tenant_admin'`.

Errors: 403 if caller is not a tenant admin of the bound tenant. (Rule 46 — operates on `current_user.tenant_id` only.)
