# Compliance Evidence Contract

**Feature**: 074-security-compliance
**Module**: `apps/control-plane/src/platform/security_compliance/services/compliance_service.py`

## Evidence auto-association

A Kafka consumer on the seven security topics (plus
`security.audit.chain.verified`) inserts one `compliance_evidence`
row per matching mapping.

```python
# compliance_service.py
async def on_security_event(event: SecurityEvent) -> None:
    mappings = await repo.find_mappings_by_evidence_type(event.evidence_type)
    for mapping in mappings:
        if mapping.filter_expression:
            if not jsonpath_matches(event.payload, mapping.filter_expression):
                continue
        await repo.insert_compliance_evidence(
            control_id=mapping.control_id,
            evidence_type=event.evidence_type,
            evidence_ref=f"{event.source}:{event.entity_id}",
            evidence_hash=event.payload_hash,
        )
```

## Manual evidence upload

For controls with no auto-source (e.g. "written security policy"),
compliance officers upload PDFs/documents:

```
POST /api/v1/security/compliance/evidence/manual
Content-Type: multipart/form-data
  - control_id: UUID
  - description: string
  - file: binary
```

File stored in S3 bucket `compliance-evidence/{framework}/
{control_id}/{timestamp}-{filename}`; `evidence_ref = s3://...`.

## Framework view

```
GET /api/v1/security/compliance/frameworks/{framework}
```

Returns:

```json
{
  "framework": "soc2",
  "controls": [
    {
      "control_id": "CC7.1",
      "description": "...",
      "evidence_count": 12,
      "latest_evidence_at": "...",
      "gap": false
    },
    {
      "control_id": "CC9.1",
      "description": "...",
      "evidence_count": 0,
      "gap": true,
      "suggested_source": "manual attestation required"
    }
  ]
}
```

## Evidence bundle export

```
POST /api/v1/security/compliance/bundles
Body: {
  "framework": "soc2",
  "window_start": "2026-01-01",
  "window_end": "2026-03-31"
}
```

Response: signed archive URL (pre-signed S3 URL). Bundle contents:
JSON manifest + pointers to every evidence artefact + content
hashes + Ed25519 signature by the audit chain's signing key.

## REST endpoints

| Method + path | Purpose | Role |
|---|---|---|
| `GET /api/v1/security/compliance/frameworks` | List frameworks | `auditor`, `compliance_officer`, `superadmin` |
| `GET /api/v1/security/compliance/frameworks/{framework}` | Controls + evidence summary | same |
| `POST /api/v1/security/compliance/evidence/manual` | Upload manual evidence | `compliance_officer`, `superadmin` |
| `GET /api/v1/security/compliance/evidence?control_id=` | List evidence per control | same |
| `POST /api/v1/security/compliance/bundles` | Generate export bundle | `compliance_officer`, `superadmin` |
| `GET /api/v1/security/compliance/bundles/{id}` | Fetch bundle (pre-signed URL) | same |

## Invariants

- Manual uploads produce both an S3 object AND a compliance_evidence
  row with `evidence_hash` of the file.
- Bundle export is signed with the Ed25519 audit signing key (same
  key that signs audit attestations — single trust anchor per
  install).
- Bundle hash verification is stateless — external assessors re-hash
  the referenced artefacts and compare to bundle manifest hashes.

## Test IDs

- **CE1** — auto-association: emit `security.sbom.published` → one
  new `compliance_evidence` row per matched control.
- **CE2** — manual upload: PDF uploaded → S3 object + evidence row
  with file hash.
- **CE3** — framework view: gaps flagged for controls with no
  evidence.
- **CE4** — bundle export: signed archive; external verifier verifies
  signature with public key.
- **CE5** — unmapped evidence type metric: emit event with no
  mapping → metric increments.
