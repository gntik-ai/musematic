# Implementation Plan: Security Compliance and Supply Chain

**Branch**: `074-security-compliance` | **Date**: 2026-04-23 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/074-security-compliance/spec.md`

## Summary

Introduce two new bounded contexts — `audit/` (cryptographic hash chain)
and `security_compliance/` (SBOM, vuln scanning, pentest tracking,
rotation, JIT, compliance evidence) — plus one Alembic migration
(058), extensions to the CI + deploy workflows (add pip-audit,
govulncheck, Bandit, gosec, npm audit, SPDX SBOM), and new
`/api/v1/security/*` admin endpoints. The hash chain wraps every
existing audit write across `auth/`, `a2a_gateway/`, `registry/`,
`mcp/` without renaming their audit tables. Ed25519 attestation
signing via UPD-040's Vault (env-var fallback during transition).

## Technical Context

**Language/Version**: Python 3.12+ (control plane); Go, TypeScript, Rust
generated-only for SDKs (feature 073 owns SDK generation).
**Primary Dependencies**:
- FastAPI 0.115+, SQLAlchemy 2.x async, aiokafka 0.11+, APScheduler 3.x
  (all existing)
- `cryptography` library (existing) for Ed25519 signing + SHA-256
- `pyyaml` (existing) for framework-catalogue seed loading
- `anchore/sbom-action@v0` (existing in `deploy.yml`) configured for
  both cyclonedx-json AND spdx-json output
- CI-only: `pip-audit`, `govulncheck`, `bandit`, `gosec`, `npm audit`
**Storage**:
- **PostgreSQL** — 13 new tables via Alembic migration 058
  (`audit_chain_entries` in `audit/`; `software_bills_of_materials`,
  `vulnerability_scan_results`, `vulnerability_exceptions`,
  `penetration_tests`, `pentest_findings`, `pentest_sla_policies`,
  `secret_rotation_schedules`, `jit_credential_grants`,
  `jit_approver_policies`, `compliance_controls`,
  `compliance_evidence`, `compliance_evidence_mappings` in
  `security_compliance/`).
- **Redis** — `jit:revoked:{grant_id}`, `rotation:state:{secret_name}`,
  `chain:last_seq` key patterns.
- **Kafka** — 7 new topics per constitution §7:
  `security.sbom.published`, `security.scan.completed`,
  `security.pentest.finding.raised`, `security.secret.rotated`,
  `security.jit.issued`, `security.jit.revoked`,
  `security.audit.chain.verified`.
- **S3** — `compliance-evidence` bucket for manual evidence uploads.
**Testing**: pytest + pytest-asyncio; CI coverage gate already ≥ 95%.
**Target Platform**: Linux (Kubernetes / Docker / local native).
**Project Type**: Two new bounded contexts + CI extension; no new
runtime profile.
**Performance Goals** (from SC-005, SC-007):
- Integrity check of 1M entries in ≤ 60 s.
- Zero auth failures during credential rotation under 100 req/s.
- Audit chain append latency ≤ 5 ms p99.
**Constraints**:
- Chain entries are append-only (DB triggers prevent UPDATE/DELETE).
- Chain append failure fails the originating audit write (no
  un-chained entries ever ship).
- Signing key never in logs; access scoped to `AuditChainService`.
- Dual-cred overlap window: 24 h ≤ x ≤ 168 h.
**Scale/Scope**:
- 13 new tables, 1 migration, 2 new BCs, 7 new Kafka topics, 2 new
  Redis key namespaces, 1 new S3 bucket.
- ~30 new REST endpoints under `/api/v1/security/*`.
- 5 new CI scanner jobs + 1 SBOM format extension.
- 4 YAML framework catalogues (SOC2, ISO27001, HIPAA, PCI-DSS).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*
Evaluated against `.specify/memory/constitution.md` at v1.3.0.

| Gate | Status | Notes |
|------|--------|-------|
| **Principle I** — Modular monolith | ✅ PASS | Two new BCs follow the existing `{models,schemas,service,router,events}.py` pattern. |
| **Principle III** — Dedicated data stores | ✅ PASS | Postgres + Redis + Kafka + S3, each per their charter. |
| **Principle IV** — No cross-boundary DB access | ✅ PASS | `audit/` exposes in-process service interface only; receives opaque `(audit_event_id, payload)` pairs. |
| **Principle V** — Append-only execution journal | ✅ PASS (expanded) | Audit chain itself is append-only; DB triggers enforce. |
| **Principle VI** — Policy machine-enforced | ✅ PASS | Gating + SLA + approver policies are DB-backed rules; no markdown drives enforcement. |
| **Brownfield Rule 1** — Never rewrite | ✅ PASS | Existing audit-writing sites gain one extra service call; no file wholesale replaced. |
| **Brownfield Rule 2** — Alembic migration | ✅ PASS | Migration 058. |
| **Brownfield Rule 3** — Preserve existing tests | ✅ PASS | Net-additive. |
| **Brownfield Rule 4** — Use existing patterns | ✅ PASS | `publish_*_event`, FastAPI router, SQLAlchemy mixins, APScheduler workers. |
| **Brownfield Rule 7** — Backward-compatible APIs | ✅ PASS | All endpoints net-new. |
| **Brownfield Rule 8** — Feature flags | ✅ PASS | `FEATURE_VULN_GATE_ENABLED`, `FEATURE_AUDIT_CHAIN_STRICT` gate new behaviours. |
| **Rule 9** — PII audit chain entries | ✅ PASS — **load-bearing** | This feature implements the rule. |
| **Rule 10** — Every credential through vault | ✅ PASS — **load-bearing** | Rotation service is primary Vault consumer; UPD-040 dependency documented with env-var fallback. |
| **Rule 29** — Admin endpoints segregated | ✅ PASS | Every endpoint under `/api/v1/security/*`; `admin` OpenAPI tag applied. |
| **Rule 30** — Admin endpoints declare role gate | ✅ PASS | Every method in new routers gates on `require_admin` / `require_superadmin`. |
| **Rule 33** — 2PA enforced server-side | ✅ PASS — **load-bearing** | JIT approver + vulnerability exception approver cannot be requester. |
| **Rule 37** — Env vars auto-documented | ✅ PASS | `Field(description=...)` on every new setting. |
| **Rule 39** — Every secret via SecretProvider | ✅ PASS | New `RotatableSecretProvider` abstraction; no direct `os.getenv` for secrets in business logic. |
| **Rule 40** — Vault token never in logs | ✅ PASS | CI check enforces via `bandit`-style rule on new modules. |
| **Rule 41** — Vault failure doesn't bypass auth | ✅ PASS | Chain append under Vault outage: rotation uses last-cached credential; JIT issuance fails closed. |
| **Rule 44** — Rotation response never echoes secret | ✅ PASS | Rotation API returns `{status, next_rotation_at, overlap_ends_at}` only. |
| **AD-17** — Tombstone-based RTBF proof | ✅ PASS — **load-bearing** | Chain entries preserved; audit event FK `ON DELETE SET NULL`; tombstone replacement per FR-033. |
| **AD-18** — Hash-chain audit integrity | ✅ PASS — **load-bearing** | The primitive this feature introduces. |

**No violations.**

## Project Structure

### Documentation (this feature)

```text
specs/074-security-compliance/
├── plan.md                          ✅ This file
├── spec.md                          ✅ 6 user stories, 38 FRs, 11 SC
├── research.md                      ✅ 15 decisions
├── data-model.md                    ✅ 13 tables + Redis + Kafka + S3 shape
├── quickstart.md                    ✅ 6 walkthroughs
├── contracts/
│   ├── audit-chain-service.md
│   ├── sbom-generation.md
│   ├── vuln-scan-pipeline.md
│   ├── secret-rotation-service.md
│   ├── jit-service.md
│   ├── pentest-tracking.md
│   ├── compliance-evidence.md
│   └── admin-api.md
└── checklists/
    └── requirements.md              ✅ Spec validation (all pass)
```

### Source Code (extending `apps/control-plane/`)

```text
apps/control-plane/src/platform/
├── audit/                                          # NEW BC — hash chain home
│   ├── __init__.py
│   ├── models.py                                   # AuditChainEntry
│   ├── schemas.py
│   ├── service.py                                  # AuditChainService
│   ├── repository.py
│   ├── signing.py                                  # Ed25519 signing/verification
│   ├── events.py
│   ├── router.py                                   # /api/v1/security/audit-chain/*
│   └── exceptions.py
├── security_compliance/                            # NEW BC — the domain surface
│   ├── __init__.py
│   ├── models.py                                   # SBOM, scan, pentest, rotation, JIT, compliance
│   ├── schemas.py
│   ├── repository.py
│   ├── events.py                                   # 6 Kafka topics
│   ├── router.py                                   # /api/v1/security/* (admin)
│   ├── exceptions.py
│   ├── services/
│   │   ├── sbom_service.py
│   │   ├── vuln_scan_service.py
│   │   ├── pentest_service.py
│   │   ├── secret_rotation_service.py
│   │   ├── jit_service.py
│   │   └── compliance_service.py
│   ├── providers/
│   │   └── rotatable_secret_provider.py            # Vault (UPD-040) + env fallback
│   ├── frameworks/
│   │   ├── soc2.yaml
│   │   ├── iso27001.yaml
│   │   ├── hipaa.yaml
│   │   ├── pci_dss.yaml
│   │   └── mappings.yaml                           # evidence_type → control_ids
│   └── workers/
│       ├── rotation_scheduler.py                   # APScheduler
│       ├── overlap_expirer.py                      # end dual-cred window
│       └── pentest_overdue_scanner.py              # surface overdue findings
├── auth/                                           # EXISTING — extend
│   └── repository_oauth.py                         # + audit_chain_service.append() call
├── a2a_gateway/
│   └── server_service.py                           # + audit_chain_service.append() call
├── registry/
│   └── services/registry_query_service.py          # + audit_chain_service.append() call
├── mcp/
│   └── services/invocation_service.py              # + audit_chain_service.append() call
├── common/
│   └── config.py                                   # EXTEND — SecurityComplianceSettings, AuditSettings
└── migrations/versions/
    └── 058_security_compliance.py                  # 13 new tables + seed data

.github/workflows/
├── ci.yml                                          # MODIFY — add pip-audit, govulncheck, Bandit, gosec, npm audit; upload-security-artefacts
├── deploy.yml                                      # MODIFY — anchore/sbom-action twice (cyclonedx-json + spdx-json); POST SBOM to platform
└── release-artefacts.yml                           # NEW — orchestrates scan + SBOM ingestion via GitHub-OIDC → platform JWT

ci/
├── normalize_scan_results.py                       # NEW
├── normalize_sbom.py                               # NEW
└── tests/
    ├── test_normalize_scan_results.py
    └── test_normalize_sbom.py
```

### Key Architectural Boundaries

- **`audit/` never knows which BC produced an audit event.** It accepts
  an opaque `(audit_event_id, canonical_payload)` pair. Producing BCs
  own their audit tables; the chain only links hashes.
- **`security_compliance/` owns its own tables.** No cross-BC DB reads.
- **Rotation never mutates downstream service state.** Manages secrets
  in Vault; downstream services pull via `RotatableSecretProvider`.
- **CI→platform boundary uses GitHub-OIDC → short-lived platform JWT
  exchange** (no long-lived CI API tokens; rule 39).
- **Framework catalogues are immutable seed data.** Additive only.

## Complexity Tracking

No constitution violations. Highest-risk areas:

1. **Audit chain append latency on the hot path.** Every audit-writing
   BC now makes one extra DB write per audit event. Mitigation: single
   INSERT against a sequence-indexed table; ≤ 5 ms p99 budget;
   load-tested in CI. Escape hatch: batched append with in-memory
   hash computation.
2. **Rotation under partial Vault availability.** Vault downtime
   mid-rotation could leave inconsistent overlap state. Mitigation:
   state transitions are idempotent; `overlap_expirer` worker
   re-checks every 30 s; rotation resumes on Vault recovery.
3. **Chain signing-key compromise.** If the key leaks, attestations
   are forgeable. Mitigation: Vault storage (UPD-040); assessor pins
   public key; key rotation forks attestation chain but audit chain
   itself unaffected.
4. **Framework catalogue drift.** Frameworks publish revised versions
   periodically. Mitigation: additive migrations; annual review gate
   in operations playbook.
5. **Compliance evidence auto-association gaps.** New
   evidence-producing event added without updating `mappings.yaml`
   produces zero rows. Mitigation: `mappings.unmapped_evidence_type`
   metric; dashboard surfaces gaps; PR template reminder.
6. **Dev-dep CVE gating false-positives.** Mitigation: `scan-metadata.json`
   declares dev-only; gating engine honours (integration-constraint 9.2);
   exception registry covers irreducible cases.
7. **Migration 058 size (13 tables + seed).** Mitigation: logical
   groups in migration file (each group its own function);
   `make migrate` + `make migrate-rollback` loops tested on fresh DB.

## Phase 0: Research

**Status**: ✅ Complete — see [research.md](research.md).

15 decisions (D-001 through D-015).

## Phase 1: Design & Contracts

**Status**: ✅ Complete — see data-model.md, contracts/*, quickstart.md.

## Phase 2: Tasks

**Status**: ⏳ Deferred to `/speckit.tasks`.
