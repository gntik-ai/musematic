# Audit and Compliance Administration

## Audit Chain

The control plane maintains an append-only cryptographic audit chain in `audit_chain_entries`. Each chained row stores the previous hash, sequence number, canonical payload hash, and entry hash. The database migration installs a trigger that rejects updates and deletes.

Operational endpoints:

- `GET /api/v1/security/audit-chain/public-key`: public Ed25519 verifying key.
- `GET /api/v1/security/audit-chain/verify?start_seq=&end_seq=`: validates chain continuity for auditors and superadmins.
- `POST /api/v1/security/audit-chain/attestations`: exports a signed attestation for a sequence range.

OAuth, A2A gateway, registry lifecycle, MCP invocation, and security-compliance audit writes append into this chain. Verification emits `security.audit.chain.verified`, which can be collected as compliance evidence.

## Compliance Evidence

Security-compliance events are consumed into `compliance_evidence` through framework mappings seeded from `soc2`, `iso27001`, `hipaa`, and `pci_dss` YAML catalogues.

Operational endpoints:

- `GET /api/v1/security/compliance/frameworks`: list frameworks with seeded controls.
- `GET /api/v1/security/compliance/frameworks/{framework}`: show controls, evidence counts, gaps, and suggested evidence sources.
- `POST /api/v1/security/compliance/evidence/manual`: upload manual evidence for a control.
- `GET /api/v1/security/compliance/evidence`: list stored evidence, optionally filtered by control.
- `POST /api/v1/security/compliance/bundles`: export a signed evidence manifest for an audit window.

Manual evidence is stored in the configured `security_compliance.manual_evidence_bucket`. Bundle manifests include evidence hashes and an audit-chain Ed25519 signature so auditors can verify integrity outside the platform.

## Release Evidence

Release pipelines produce two evidence streams:

- SBOMs in SPDX and CycloneDX format, canonicalized before hashing.
- Scanner results from Trivy, pip-audit, Bandit, govulncheck, gosec, and npm audit.

Findings at or above the scanner gate severity block release unless they are marked dev-only or covered by an active vulnerability exception. Exceptions require two-person approval.

## Privacy Compliance

Privacy compliance records are linked to the platform audit chain by event type. DSR
lifecycle transitions, deletion cascades, PIA transitions, DLP events, residency
changes, residency violations, and consent revocations all emit typed privacy
events.

Primary operator surfaces:

- `POST /api/v1/privacy/dsr` for data-subject requests and tombstone export.
- `GET /api/v1/privacy/dsr/{dsr_id}/tombstone/signed` for signed erasure proofs.
- `POST /api/v1/privacy/pia` for privacy impact assessments and approval workflow.
- `GET /api/v1/privacy/dlp/rules` and `GET /api/v1/privacy/dlp/events` for DLP operations.
- `PUT /api/v1/privacy/residency/{workspace_id}` for regional policy configuration.
- `GET /api/v1/privacy/consents?user_id=` for consent history review.

Signed deletion tombstones can be verified without platform imports using
`tests/e2e/scripts/verify_signed_tombstone.py`.

## Common Admin Workflows

### Export Audit Evidence

Select the framework, control, and date range. Generate a signed evidence bundle and verify the included audit-chain signature before sending it outside the platform.

### Review Vulnerability Exceptions

Open the release evidence page, inspect scanner findings, confirm exception expiry, and require two-person approval for production exceptions.

### Process a Data-Subject Request

Create the DSR, verify identity, run the deletion or export workflow, and attach the signed tombstone or export proof to the request.

### Verify Audit Chain Continuity

Run the audit-chain verify endpoint for the target sequence range. Investigate immediately if continuity or signature verification fails.
