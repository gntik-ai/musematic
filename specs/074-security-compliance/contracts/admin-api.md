# Admin API Surface Contract

**Feature**: 074-security-compliance
**Files**:
- `apps/control-plane/src/platform/audit/router.py`
- `apps/control-plane/src/platform/security_compliance/router.py`

## Summary

All endpoints live under `/api/v1/security/*` (constitution rule 29)
and carry the `admin` OpenAPI tag (so feature 073's SDK generator
filters them out of consumer SDKs). Every method gates on one of:
`superadmin`, `platform_admin`, `auditor`, `compliance_officer`, or
`service_account` with a named role.

## Endpoint catalogue

Full inventory across the seven sub-contracts:

### Audit chain (`audit_chain_service.md`)

- `GET /api/v1/security/audit-chain/verify`
- `POST /api/v1/security/audit-chain/attestations`
- `GET /api/v1/security/audit-chain/public-key`

### SBOM (`sbom-generation.md`)

- `POST /api/v1/security/sbom`
- `GET /api/v1/security/sbom/{release_version}`
- `GET /api/v1/security/sbom/{release_version}/hash`

### Vulnerability scans (`vuln-scan-pipeline.md`)

- `POST /api/v1/security/scans/{release_version}/results`
- `GET /api/v1/security/scans/{release_version}`
- `GET /api/v1/security/scans/{release_version}/status`
- `POST /api/v1/security/vulnerability-exceptions`
- `GET /api/v1/security/vulnerability-exceptions`

### Secret rotation (`secret-rotation-service.md`)

- `GET /api/v1/security/rotations`
- `POST /api/v1/security/rotations`
- `PATCH /api/v1/security/rotations/{id}`
- `POST /api/v1/security/rotations/{id}/trigger`
- `GET /api/v1/security/rotations/{id}/history`

### JIT credentials (`jit-service.md`)

- `POST /api/v1/security/jit-grants`
- `GET /api/v1/security/jit-grants`
- `GET /api/v1/security/jit-grants/{id}`
- `POST /api/v1/security/jit-grants/{id}/approve`
- `POST /api/v1/security/jit-grants/{id}/reject`
- `POST /api/v1/security/jit-grants/{id}/revoke`
- `POST /api/v1/security/jit-grants/{id}/usage`
- `GET /api/v1/security/jit-approver-policies`

### Pentest tracking (`pentest-tracking.md`)

- `POST /api/v1/security/pentests`
- `GET /api/v1/security/pentests`
- `GET /api/v1/security/pentests/{id}`
- `POST /api/v1/security/pentests/{id}/execute`
- `POST /api/v1/security/pentests/{id}/findings`
- `PATCH /api/v1/security/pentests/{id}/findings/{fid}`
- `GET /api/v1/security/pentests/findings/overdue`
- `GET /api/v1/security/pentests/export`

### Compliance evidence (`compliance-evidence.md`)

- `GET /api/v1/security/compliance/frameworks`
- `GET /api/v1/security/compliance/frameworks/{framework}`
- `POST /api/v1/security/compliance/evidence/manual`
- `GET /api/v1/security/compliance/evidence`
- `POST /api/v1/security/compliance/bundles`
- `GET /api/v1/security/compliance/bundles/{id}`

## Total: 32 endpoints

Across two BCs (`audit/` contributes 3; `security_compliance/`
contributes 29).

## Common contract requirements

- Every method depends on `require_admin` or `require_superadmin`
  via the `auth/dependencies.py` helpers (rule 30).
- Every mutating endpoint emits a `security.*` Kafka event AND
  produces an audit chain entry (rule 9).
- Every error response follows the platform's existing error shape
  (`{error, code, message, detail?}`) with no secret leakage.
- Rate limiting applied per feature 073's middleware (admin tier).

## OpenAPI requirements

- All 32 endpoints carry the `admin` tag + their sub-context tag
  (e.g. `['admin', 'audit-chain']`).
- Path `/api/v1/security/audit-chain/public-key` is exempt from auth
  (public key lookup; constitution rule 49 — public status page
  pattern).
- Spectral lint passes (feature 073's CI gate).
