# SBOM Generation + Ingest Contract

**Feature**: 074-security-compliance
**Files**:
- `.github/workflows/deploy.yml` (extend existing `anchore/sbom-action`)
- `apps/control-plane/src/platform/security_compliance/services/sbom_service.py`

## CI extension (deploy.yml)

Extend the existing step at `deploy.yml:97-108` to run **twice** per
image, once with `format: cyclonedx-json`, once with `format:
spdx-json`. Both outputs are:

1. Attached to the GitHub release (existing behaviour).
2. POSTed to `/api/v1/security/sbom` via the `release-artefacts.yml`
   workflow's platform-JWT-exchange step.

```yaml
- name: Generate CycloneDX SBOM
  uses: anchore/sbom-action@v0
  with:
    image: ${{ steps.push.outputs.digest }}
    format: cyclonedx-json
    output-file: sbom-cyclonedx.json

- name: Generate SPDX SBOM
  uses: anchore/sbom-action@v0
  with:
    image: ${{ steps.push.outputs.digest }}
    format: spdx-json
    output-file: sbom-spdx.json
```

## REST endpoints (admin)

| Method + path | Purpose | Role |
|---|---|---|
| `POST /api/v1/security/sbom` | Ingest one SBOM | `service_account` with `release_publisher` role |
| `GET /api/v1/security/sbom/{release_version}?format=` | Retrieve by release + format | `auditor`, `superadmin` |
| `GET /api/v1/security/sbom/{release_version}/hash` | Retrieve content SHA-256 | `auditor`, `superadmin` |

### POST /sbom body

```json
{
  "release_version": "1.4.0",
  "format": "spdx" | "cyclonedx",
  "content": "<full SBOM JSON as string>"
}
```

Service computes `content_sha256`, inserts row, emits
`security.sbom.published` Kafka event.

## Invariants

- One row per (release_version, format) — unique constraint.
- Content hash verifies on retrieval (integrity guarantee).
- Chain entry created for every ingest event (rule 9).

## Test IDs

- **SB1** — ingest CycloneDX → row + event + hash.
- **SB2** — ingest duplicate → 409 Conflict.
- **SB3** — retrieve by (version, format) → original content + hash.
- **SB4** — hash mismatch on external modification → detected by audit.
