# Phase 0 Research: Security Compliance and Supply Chain

**Feature**: 074-security-compliance
**Date**: 2026-04-23

## Scope

This feature introduces two new bounded contexts (`security_compliance/`
for the domain surface, plus a net-new `audit/` BC to host the central
hash-chain), extends the existing CI pipeline with additional vuln
scanners and SPDX output, and adds one Alembic migration (058). Every
decision below is grounded in the current codebase per the Phase 0
discovery report and the constitution at v1.3.0.

## Decisions

### D-001 — Create a central `audit/` BC alongside `security_compliance/`

**Decision**: Ship **two** new bounded contexts:

1. **`apps/control-plane/src/platform/audit/`** — owns the cryptographic
   audit chain (`audit_chain_entries` table) and exposes an in-process
   `AuditChainService` with `append(audit_event_id, payload_bytes)` and
   `verify(start_seq, end_seq)` methods.
2. **`apps/control-plane/src/platform/security_compliance/`** — owns
   the seven audit-pass workflows (SBOM, vuln scan, pentest, rotation,
   JIT, compliance evidence, plus the admin surface).

Every existing audit-writing site (auth's `OAuthAuditEntry`, a2a_gateway's
`a2a_audit_records`, registry's `registry_lifecycle_audit`, mcp's
`mcp_invocation_audit_records`) adds a second call
`audit_chain_service.append(audit_event_id, canonical_payload(row))`
immediately after its existing write. No existing audit tables are
renamed or moved.

**Rationale**: The Phase 0 research found that no central `audit/` BC
exists today — auditing is distributed per-BC. A central chain service
requires a home; `audit/` is that home. Creating it as a second new BC
(alongside `security_compliance/`) keeps scope boundaries clean and
avoids stuffing unrelated concerns into `security_compliance/`.

**Alternatives considered**:
- SQLAlchemy event listener intercepting writes to `*_audit*` tables —
  rejected: listeners run after flush and do not have the cleartext
  audit event available at hash time; the canonical payload cannot be
  reconstructed deterministically from ORM state alone.
- Force every existing BC to publish to a single `audit_events` Kafka
  topic and consume into a central table — rejected: major migration
  work for existing audit emitters, violates Brownfield Rule 1 ("never
  rewrite existing code"); the audit tables that exist today must
  remain their BCs' source of truth.

### D-002 — Hash chain construction (SHA-256)

**Decision**: Chain entries are linked by SHA-256 hashes. The hash
input is the concatenation:

```
entry_hash = sha256(
    previous_hash (64 hex chars)
    || sequence_number (8-byte big-endian)
    || canonical_payload_hash (64 hex chars)
)
```

The **genesis entry** (sequence_number=1) uses
`previous_hash = "0" * 64`. Canonical payload is produced by the
producing BC and passed to `append()`; the chain service stores only its
SHA-256 hash and never inspects its shape. `audit_event_id` is excluded
from the chain hash so RTBF can null that mutable reference without
invalidating historical chain entries.

**Rationale**: SHA-256 is the de-facto standard for regulatory
attestation. OpenSSL / JDK / Go stdlib / Python `hashlib` all support
it natively; assessors know how to verify it. BLAKE3 would be faster
(~3×) but no major auditor asks for it.

**Alternatives considered**:
- BLAKE3 — rejected on interop grounds.
- Merkle tree (periodic anchoring) — deferred: more complex, marginal
  benefit for our expected chain size (< 10M entries/year).
- Signed per-entry — rejected: signing every entry is overkill;
  signing is done at attestation-export time (D-004).

### D-003 — Chain signing key via UPD-040 (with env-var fallback)

**Decision**: The chain's attestation-signing key is an **Ed25519
keypair** stored at `secret/data/musematic/{env}/audit/signing-key` in
Vault (per UPD-040's canonical path scheme). Public verifying key is
published at `GET /api/v1/security/audit-chain/public-key` for
external assessor verification.

For the interim while UPD-040 is in flight: env-var fallback
`AUDIT_CHAIN_SIGNING_KEY` (hex-encoded Ed25519 private seed, 32 bytes)
and `AUDIT_CHAIN_VERIFYING_KEY` (hex-encoded public key, 32 bytes).
Rotating the signing key is a deliberate governance event (not
automated) documented in `contracts/audit-chain-service.md`; rotation
produces a new chain of attestations but existing attestations remain
verifiable with the prior public key.

**Rationale**: Ed25519 produces small (64-byte) signatures, fast
verification, no parameter risks. Constitution rule 10 requires every
credential through vault — the env-var fallback is a documented
stopgap until UPD-040 lands.

### D-004 — Integrity-check and attestation-export algorithm

**Decision**: `verify(start_seq, end_seq)`:

1. Load entries [start_seq..end_seq] in sequence order.
2. For each entry, recompute `entry_hash` per D-002 inputs.
3. Compare with stored `entry_hash`. First mismatch → return `{valid:
   false, broken_at: seq}`.
4. All match → return `{valid: true, entries_checked: count}`.

`export_attestation(start_seq, end_seq)`:

1. Run `verify(start_seq, end_seq)`; if invalid, error out.
2. Build attestation JSON: `{platform: "musematic", env, start_seq,
   end_seq, start_entry_hash, end_entry_hash, window_start_time,
   window_end_time, chain_entries_count}`.
3. Sign with Ed25519 private key → base64 signature appended as
   `signature`.
4. Return the signed JSON document.

**Rationale**: Walk-and-recompute is O(N) — fast enough for 10M
entries (< 60 s per SC-005). Ed25519 signatures are compact and
interoperable.

### D-005 — Scanner matrix (extend existing, not replace)

**Decision**: Extend `.github/workflows/ci.yml` with the missing
scanners:

| Scanner | Targets | Gate severity |
|---|---|---|
| **Trivy** (existing, lines 568–610 of ci.yml) | Container images | CRITICAL for runtime deps |
| **Gitleaks** (existing, lines 553–566) | Secrets in repo | any finding |
| **pip-audit** (new) | Python `apps/control-plane/` + `apps/ops-cli/` | CRITICAL |
| **govulncheck** (new) | Go `services/*` | HIGH |
| **Bandit** (new) | Python SAST | HIGH |
| **gosec** (new) | Go SAST | HIGH |
| **npm audit** (new) | Frontend `apps/web/` | HIGH |

Each scanner emits a `.sarif` or equivalent JSON output. A new Python
script `ci/normalize_scan_results.py` reads all outputs, normalises
into the `vulnerability_scan_results` table's JSONB shape, and POSTs
to the platform's ingest endpoint
`/api/v1/security/scans/{release_version}/results` (admin-only).

**Rationale**: Reuses the existing Trivy + Gitleaks jobs rather than
forking; the fill-in scanners cover the ecosystems the platform uses
(Python, Go, JS). Dev-only dependencies marked as such via a
`scan-metadata.json` manifest so they do not block releases (per
constitution integration-constraint 9.2).

### D-006 — SBOM format extension (add SPDX alongside CycloneDX)

**Decision**: Extend `.github/workflows/deploy.yml`'s existing
`anchore/sbom-action` step (lines 97–108) to run **twice** per image:
once with `format: cyclonedx-json` (current) and once with
`format: spdx-json`. Both outputs are attached to the GitHub release
AND ingested into the `software_bills_of_materials` Postgres table via
a new CI step that POSTs to `/api/v1/security/sbom`.

**Rationale**: anchore/sbom-action supports both formats; cost is
minimal (< 30 s extra per release). Two formats satisfy compliance
officers who prefer each one.

### D-007 — Pentest remediation SLA mapping

**Decision**: Ship a seeded SLA mapping in the Alembic migration:

| Severity | Due date |
|---|---|
| `critical` | scheduled_for + 7 days |
| `high` | scheduled_for + 30 days |
| `medium` | scheduled_for + 90 days |
| `low` | scheduled_for + 180 days |

Stored in a small `pentest_sla_policies` table, editable by platform
admins but **may not be widened below these defaults** without a
constitutional amendment (floor values enforced via DB check
constraint).

**Rationale**: Defaults match industry norms for SaaS platforms
(e.g. PCI-DSS's 30-day high-severity window). Floor enforcement
matches constitution discipline of irreducible defaults (like the 4-h
debug session cap).

### D-008 — Secret rotation dual-credential contract

**Decision**: Services that validate credentials expose a thin
`validate_credential(presented_credential) -> bool` interface backed
by a `RotatableSecretProvider` that returns both `current` and
`previous` values during an active overlap window. Overlap state is
stored in Vault (or env-fallback) under:

```
secret/data/musematic/{env}/rotating/{secret_name}
  { "current": "...", "previous": "...", "overlap_ends_at": "<ISO8601>" }
```

When `overlap_ends_at` passes, a background worker in the rotation
service marks the previous credential as expired, Vault purges the
`previous` key, and subsequent validations reject the old credential.

**Rationale**: Keeps the rotation contract thin. Existing credential
validators (e.g. JWT signers, DB password users) need only add
acceptance of the `previous` value during the overlap window — no
broader refactor.

**Alternatives considered**:
- Hot-swap without overlap — rejected: incompatible with SC-007's
  zero-failure requirement for typical services.
- Push-based notification from Vault — rejected: not all validators
  can implement a consumer cleanly; pull is more robust.

### D-009 — JIT credential issuance via short-lived JWT

**Decision**: A JIT grant, once approved, triggers the existing
`auth/services/auth_service.py` to issue a short-lived JWT with:

- `sub`: the requester's user_id.
- `purpose`: JWT claim carrying the requested operation + free-text
  purpose.
- `exp`: min(requested_expiry, policy_max_expiry).
- `jti`: the `jit_credential_grants.id` (UUID) for revocation lookup.

Services validating the JWT check the standard `exp`, then perform a
Redis lookup `jit:revoked:{jti}` (TTL set to remaining lifetime) to
detect revocation. Revoking a grant sets this key to `"1"`.

**Rationale**: Uses existing JWT infrastructure (no parallel credential
system). Redis denylist for revocation is constant-time lookup and
self-cleaning via TTL.

### D-010 — JIT approver policy

**Decision**: Seeded `jit_approver_policies` table with rows keyed by
operation pattern:

| Operation pattern | Approver role | Min approvers |
|---|---|---|
| `db:prod:*` | `platform_admin` | 1 |
| `infra:prod:*` | `platform_admin` | 1 |
| `customer_data:*` | `platform_admin` + `trust_reviewer` | 2 |
| `*` (fallback) | `platform_admin` | 1 |

Server-side enforcement: approver's user_id MUST differ from requester
(constitution rule 33 — 2PA); operations with `min_approvers > 1`
require each approver's `role` to match; policy consulted at approve
time; denials recorded in audit chain.

### D-011 — Compliance evidence auto-association

**Decision**: A declarative YAML seed loaded at migration time:

```yaml
# security_compliance/frameworks/mappings.yaml
- evidence_type: sbom_generated
  controls: [soc2.CC7.1, iso27001.A.8.28, hipaa.§164.308(a)(5)(ii)(A)]
- evidence_type: vulnerability_scan_completed
  controls: [soc2.CC7.1, iso27001.A.8.29, pci_dss.6.3]
- evidence_type: secret_rotation_completed
  controls: [soc2.CC6.1, iso27001.A.5.17, pci_dss.3.7]
- evidence_type: jit_grant_approved
  controls: [soc2.CC6.3, iso27001.A.8.18]
- evidence_type: audit_chain_attested
  controls: [soc2.CC7.2, iso27001.A.8.15]
- evidence_type: pentest_finding_remediated
  controls: [soc2.CC7.1, iso27001.A.8.8]
```

A Kafka consumer on the security topics (`security.sbom.published`,
`security.scan.completed`, `security.secret.rotated`,
`security.jit.issued`, `security.audit.chain.verified`,
`security.pentest.finding.raised`) inserts one
`compliance_evidence` row per matching control.

**Rationale**: Decoupled, declarative, and framework catalogues grow
over time without code changes.

### D-012 — Framework seed catalogues

**Decision**: Ship YAML seed files under
`apps/control-plane/src/platform/security_compliance/frameworks/`:

- `soc2.yaml` — Common Criteria CC1 through CC9 (Trust Services).
- `iso27001.yaml` — ISO/IEC 27001:2022 Annex A controls.
- `hipaa.yaml` — HIPAA Security Rule §164.308–§164.314.
- `pci_dss.yaml` — PCI-DSS v4.0 Requirements 1–12.

Loaded by Alembic migration 058 as seed data into
`compliance_controls`. Other frameworks (FedRAMP, NIST CSF) are
future work.

### D-013 — Alembic migration number

**Decision**: **058**. Confirmed by Phase 0 research: `057_api_governance.py`
(feature 073) was published 2026-04-24; 058 is the next free slot.

### D-014 — Vulnerability exception registry (new table)

**Decision**: Add a ninth table `vulnerability_exceptions`:

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `scanner` | VARCHAR(64) | |
| `vulnerability_id` | VARCHAR(128) | e.g. `CVE-2025-12345` |
| `component_pattern` | VARCHAR(256) | pattern matched against scan output |
| `justification` | TEXT | |
| `approved_by` | UUID FK → `users.id` | |
| `expires_at` | TIMESTAMPTZ | NOT NULL |
| `created_at` | TIMESTAMPTZ | |

The gating rule consults this table before blocking; active
(non-expired) exceptions matching the finding pass through. Creating
an exception requires the same approval as JIT grants (peer approval;
rule 33).

**Rationale**: FR-008 explicitly mentions "documented exceptions";
they need a home. Separate table keeps the audit story clean (each
exception creation and expiry is its own chain entry).

### D-015 — CI-to-platform wiring

**Decision**: New CI step `upload-security-artefacts` runs after
scanners + SBOM generation. It authenticates via a dedicated
GitHub-OIDC → short-lived platform JWT (avoids long-lived CI API
keys, per constitution rule 39). POSTs to:

- `POST /api/v1/security/sbom` (SBOM document, format, release version)
- `POST /api/v1/security/scans/{release_version}/results` (normalised
  scan report)
- `POST /api/v1/security/sbom/{release_version}/attach-artefact` (S3
  ref for the raw SBOM file already uploaded to the GitHub release)

The new platform endpoints are admin-gated (rule 30) and allow
"service_account" principals with the `release_publisher` role.

## Deferred / future

- **FedRAMP and NIST CSF** framework catalogues — deferred to a
  follow-up feature.
- **BLAKE3 chain hashing** — deferred pending regulatory-landscape
  change.
- **Automated signing-key rotation protocol** — deferred; current
  rotation is a manual governance event.
- **External HSM for audit-signing key** — deferred; Vault's transit
  engine (per UPD-040) is sufficient for v1.
- **SOC2 Type I / Type II report generation** — assessors still produce
  their own reports; we provide evidence bundles, not the report itself.
