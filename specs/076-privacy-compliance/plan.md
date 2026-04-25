# Implementation Plan: Privacy Compliance (GDPR / CCPA)

**Branch**: `076-privacy-compliance` | **Date**: 2026-04-25 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/076-privacy-compliance/spec.md`

## Summary

Create the `privacy_compliance/` bounded context implementing GDPR /
CCPA data-subject rights with cascade deletion across six data stores
(PostgreSQL, Qdrant, OpenSearch, S3, ClickHouse, Neo4j), tombstone
records with Ed25519-signed proof-of-deletion hashes (signing key
reused from UPD-024's audit chain), query-time residency enforcement
in the visibility resolution path, DLP scanning of tool outputs +
guardrail-pipeline outputs with a seeded pattern floor, PIA workflow
gating certification for agents that process PII/PHI/financial/
confidential data, first-interaction AI disclosure + consent
tracking. One Alembic migration (060) adds 7 tables. The cascade
orchestrator handles 38 PII-bearing tables discovered across 14
existing bounded contexts, plus deletion adapters for the other five
stores.

## Technical Context

**Language/Version**: Python 3.12+ (control plane). No Go changes.
**Primary Dependencies**:
- FastAPI 0.115+, SQLAlchemy 2.x async, Pydantic v2, aiokafka 0.11+,
  APScheduler 3.x (all existing)
- `cryptography` (existing) for SHA-256 and Ed25519 verification of
  tombstones (signing done via UPD-024's key — no new key material
  introduced)
- Existing data-store clients: `qdrant-client`, `opensearch-py`,
  `aioboto3`, `clickhouse-connect`, and the Neo4j PostgreSQL-fallback
- No new third-party libraries
**Storage**:
- **PostgreSQL** — 7 new tables via Alembic migration 060
  (`privacy_dsr_requests`, `privacy_deletion_tombstones`,
  `privacy_residency_configs`, `privacy_dlp_rules`,
  `privacy_dlp_events`, `privacy_impact_assessments`,
  `privacy_consent_records`)
- Also: tombstone-column addition (`is_deleted BOOLEAN`) on ClickHouse
  rollup tables that contain PII (migration 060 adds via ClickHouse
  client calls in `upgrade()` post-PG-work).
- **Kafka** — 5 new topics per constitution §7:
  `privacy.dsr.received`, `privacy.dsr.completed`,
  `privacy.deletion.cascaded`, `privacy.dlp.event`,
  `privacy.pia.approved` (plus a derived `privacy.pia.rejected` and
  `privacy.pia.superseded`)
- **Redis** — `privacy:consent:{user_id}:{workspace_id}` (30 s TTL
  read-through cache on consent state) and
  `privacy:residency:{workspace_id}` (60 s TTL cached residency
  config)
- **Vault** — `secret/data/musematic/{env}/privacy/subject-hash-salt`
  (single salt used in tombstone subject-hashing; via UPD-040's
  `SecretProvider`)
**Testing**: pytest + pytest-asyncio; E2E cascade test requires all
six data stores in docker-compose. CI coverage ≥ 95%. Cascade
chaos-tests inject per-store failures and assert correct partial-
failure handling.
**Target Platform**: Linux (K8s / Docker / local native).
**Project Type**: One new bounded context + extensions to existing
`policies/gateway.py`, `trust/guardrail_pipeline.py`,
`registry/service.py`, `interactions/service.py`,
`trust/services/certification_service.py`.
**Performance Goals** (from SC-002, SC-010):
- Cascade deletion completes within 1 hour of DSR submission for a
  subject with 1M rows across all stores.
- Per-store deletion adapter latency ≤ the data-store's native bulk-
  delete primitive (sub-second for most; up to 10 minutes for S3 with
  100k+ objects).
- Residency check on the hot path ≤ 1 ms overhead (Redis-cached
  config).
- DLP scanner adds ≤ 10 ms p99 to tool output latency (regex matching
  is fast; seeded ~10 patterns compiled once).
**Constraints**:
- Cascade is all-or-tracked: if any store fails, DSR → `failed` with
  full `cascade_log`; partial success is idempotent on retry (FR-009).
- Tombstones NEVER contain PII (FR-008 + AD-17); `subject_user_id` is
  hashed with a Vault-stored salt before persistence.
- Tombstone `proof_hash` is deterministic SHA-256 of canonical JSON.
- Residency violations fail closed (unknown region = disallowed).
- Consent revocation propagates within 5 minutes to training
  exclusions + analytics suppression (SC-006).
**Scale/Scope**:
- 7 new Postgres tables, 1 Alembic migration, 1 new BC, 5 new Kafka
  topics, 2 new Redis key patterns, 1 new Vault path, 1 new Python
  role (`privacy_officer`).
- ~22 new REST endpoints under `/api/v1/privacy/*`.
- 6 new `CascadeAdapter` implementations.
- 38 PostgreSQL tables declared in the PostgreSQL adapter's per-table
  column map.
- 10+ seeded DLP rules.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*
Evaluated against `.specify/memory/constitution.md` at v1.3.0.

| Gate | Status | Notes |
|------|--------|-------|
| **Principle I** — Modular monolith | ✅ PASS | One new BC; integration points are narrow (4 existing files extended). |
| **Principle III** — Dedicated data stores | ✅ PASS | Each store kept to its charter. |
| **Principle IV** — No cross-boundary DB access | ⚠️ PASS WITH NOTE | The cascade orchestrator's PostgreSQL adapter deletes rows in 14 other BCs' tables. This is the ONE legitimate cross-BC DB-access exception in the platform (erasure is a cross-cutting concern per GDPR). The adapter is owned by `privacy_compliance/` and treats each target BC's tables as input via a declared column map; the BCs themselves do not query across to `privacy_compliance/`. This matches the constitution's spirit (cascades as an exception for compliance). |
| **Principle VI** — Policy machine-enforced | ✅ PASS | Erasure, residency, DLP, PIA, consent all policy-enforced via code. |
| **Brownfield Rule 1** — Never rewrite | ✅ PASS | 4 existing files gain short additions (hooks); no rewrites. |
| **Brownfield Rule 2** — Alembic migration | ✅ PASS | Migration 060. |
| **Brownfield Rule 3** — Preserve existing tests | ✅ PASS | Net-additive. |
| **Brownfield Rule 4** — Use existing patterns | ✅ PASS | Service layer + router + FastAPI + SQLAlchemy + Kafka events + APScheduler workers. |
| **Brownfield Rule 7** — Backward-compatible APIs | ✅ PASS | Net-new endpoints; existing endpoints unaffected. |
| **Brownfield Rule 8** — Feature flags | ✅ PASS | `FEATURE_PRIVACY_DSR_ENABLED`, `FEATURE_DLP_ENABLED`, `FEATURE_RESIDENCY_ENFORCEMENT` (per constitution's feature-flag inventory) gate each capability independently. |
| **Rule 9** — PII audit chain entries | ✅ PASS — **load-bearing** | Every DSR / tombstone / PIA / DLP event / residency violation emits an audit-chain entry via UPD-024's `AuditChainService.append()`. |
| **Rule 10** — Every credential through Vault | ✅ PASS | Subject-hash-salt in Vault (via UPD-040 `SecretProvider`). |
| **Rule 15** — Every data deletion cascades | ✅ PASS — **load-bearing** | This feature implements the rule; cascade orchestrator handles all 6 data stores. |
| **Rule 16** — Every DSR request produces a tombstone | ✅ PASS — **load-bearing** | FR-006 / FR-007: every completed erasure DSR produces a tombstone with proof hash. |
| **Rule 18** — Regional queries enforce data residency | ✅ PASS — **load-bearing** | FR-012 / FR-013: query-time enforcement, not install-time. |
| **Rule 29** — Admin endpoints segregated | ✅ PASS | All `/api/v1/privacy/*` endpoints tagged `admin` except the self-service consent endpoints under `/api/v1/me/consents/*`. |
| **Rule 30** — Admin endpoints declare role gate | ✅ PASS | Every mutating method depends on `privacy_officer` / `platform_admin` / `superadmin` (new role introduced per research.md D-015). |
| **Rule 33** — 2PA enforced server-side | ✅ PASS — **load-bearing** | PIA approver ≠ submitter (FR-024). Cancellation of a scheduled erasure during the hold window uses 2PA. |
| **Rule 37** — Env vars auto-documented | ✅ PASS | `Field(description=...)` on every new setting. |
| **Rule 39** — Every secret via SecretProvider | ✅ PASS | Subject-hash-salt resolved via `SecretProvider`. |
| **Rule 45** — Every user-facing backend has a UI | ⚠️ PARTIAL | Self-service endpoints (`/api/v1/me/consents`, `/api/v1/me/dsr`) are introduced here as backend; the UI surface comes in UPD-042 (User-Facing Notification Center + Self-Service Security). Spec's US2 AI disclosure UI is scoped out to UPD-042's consent UX; this feature delivers only the backend enforcement. |
| **Rule 46** — Self-service endpoints scoped to `current_user` | ✅ PASS | `/api/v1/me/consents` + `/api/v1/me/dsr` endpoints accept no `user_id` parameter; resolved from JWT. |
| **AD-17** — Tombstone-based RTBF proof | ✅ PASS — **load-bearing** | FR-008 + FR-011 — tombstone never contains PII; signed and externally verifiable. |

**No hard violations.** Principle IV is the one notable case — the
cascade orchestrator spans BCs by design, reflecting GDPR's
cross-cutting nature. The constitution's spirit is upheld: the
orchestrator is owned by `privacy_compliance/` (single responsibility
for the cross-cut); target BCs do not query `privacy_compliance/`.

## Project Structure

### Documentation (this feature)

```text
specs/076-privacy-compliance/
├── plan.md                          ✅ This file
├── spec.md                          ✅ 6 user stories, 31 FRs, 11 SC
├── research.md                      ✅ 15 decisions
├── data-model.md                    ✅ 7 tables + Redis + Kafka + Vault
├── quickstart.md                    ✅ 6 walkthroughs
├── contracts/
│   ├── dsr-handling.md              ✅ Request lifecycle + admin API
│   ├── cascade-orchestrator.md      ✅ Adapter registry + tombstone
│   ├── dlp-pipeline.md              ✅ Rule engine + insertion points
│   ├── residency-enforcer.md        ✅ Query-time check + integration
│   ├── pia-workflow.md              ✅ Draft → review → approve cycle
│   └── consent-service.md           ✅ First-interaction disclosure + revocation
└── checklists/
    └── requirements.md              ✅ Spec validation (all pass)
```

### Source Code (extending `apps/control-plane/`)

```text
apps/control-plane/src/platform/
├── privacy_compliance/                              # NEW BC
│   ├── __init__.py
│   ├── models.py                                    # 7 tables
│   ├── schemas.py
│   ├── repository.py
│   ├── events.py                                    # 5+ Kafka topics
│   ├── router.py                                    # /api/v1/privacy/* (admin)
│   ├── router_self_service.py                       # /api/v1/me/consents, /api/v1/me/dsr
│   ├── exceptions.py
│   ├── services/
│   │   ├── dsr_service.py                           # 6 request-type handlers
│   │   ├── cascade_orchestrator.py                  # registers adapters, runs deletion
│   │   ├── dlp_service.py                           # rule CRUD + scan
│   │   ├── residency_service.py                    # config CRUD + enforcement
│   │   ├── pia_service.py                           # lifecycle + approval
│   │   └── consent_service.py                       # grants + revocations
│   ├── cascade_adapters/
│   │   ├── __init__.py
│   │   ├── base.py                                  # CascadeAdapter ABC
│   │   ├── postgresql_adapter.py                    # 38-table column map + DELETEs
│   │   ├── qdrant_adapter.py
│   │   ├── opensearch_adapter.py
│   │   ├── s3_adapter.py                            # new delete_objects_matching_prefix
│   │   ├── clickhouse_adapter.py                    # tombstone column pattern
│   │   └── neo4j_adapter.py                         # graph_nodes/edges fallback today
│   ├── dlp/
│   │   ├── __init__.py
│   │   ├── scanner.py                               # regex engine + action dispatcher
│   │   └── seeded_patterns.yaml                     # 10+ platform floor patterns
│   └── workers/
│       ├── hold_window_releaser.py                  # APScheduler — release scheduled erasures after hold
│       ├── dlp_event_aggregator.py                  # daily counts into ClickHouse
│       └── consent_propagator.py                    # propagate revocations to agent composition + analytics
├── auth/
│   └── schemas.py                                   # EXTEND — add privacy_officer to RoleType enum
├── policies/
│   └── gateway.py                                   # EXTEND — residency check + DLP output scan
├── trust/
│   ├── guardrail_pipeline.py                        # EXTEND — add GuardrailLayer.dlp_scan
│   └── services/certification_service.py            # EXTEND — block cert when PIA required but not approved
├── registry/
│   └── service.py                                   # EXTEND — residency check during profile lookup
├── interactions/
│   └── service.py                                   # EXTEND — ConsentRequired on first conversation
├── common/
│   ├── clients/object_storage.py                    # EXTEND — delete_objects_matching_prefix helper
│   └── config.py                                    # EXTEND — PrivacyComplianceSettings
└── migrations/versions/
    └── 060_privacy_compliance.py                    # 7 tables + ClickHouse tombstone columns + role seed + DLP pattern seed

.github/workflows/
└── ci.yml                                           # MODIFY — cascade-adapter coverage static check
```

### Key Architectural Boundaries

- **Cascade orchestrator is the cross-cutting seam**, owned by
  `privacy_compliance/`. It reads other BCs' schemas through a declared
  column map — never through cross-BC imports. When a new BC is added,
  its tables must register in the map, enforced by a CI static check.
- **DLP scanner is invoked at two pipeline points** — policies gateway
  (outbound) + guardrail pipeline (stage). Both emit the same
  `privacy.dlp.event` Kafka event shape.
- **Residency is a read-side concern**; enforcement at visibility
  resolution. Writes are trusted to come from an authorised region
  (the write-path is protected by auth already).
- **Consent is gated server-side at `interactions.create_conversation`**;
  UI is a UPD-042 concern.
- **Tombstone signing reuses UPD-024's Ed25519 key** — single trust
  anchor.

## Complexity Tracking

No hard violations. Highest-risk areas:

1. **Cascade orchestrator correctness across 38 tables**. The column
   map is hand-declared today; drift would cause incomplete erasure.
   Mitigation: CI static check diffs the declared map against
   `grep ForeignKey("users.id")` + column-name heuristics; fails the
   build if a PII-bearing table isn't in the map. Quarterly manual
   audit.
2. **Partial cascade failure and idempotency.** Adapter per-store
   failure modes differ (connection loss, timeout, permission denied).
   Mitigation: every adapter's `execute()` is idempotent on retry
   (already-deleted rows return zero-count); the orchestrator's
   `cascade_log` is append-only across retries (not reset on retry).
3. **ClickHouse tombstone-column pattern is new for the platform.**
   Downstream queries must filter `WHERE NOT is_deleted`. Mitigation:
   a query-rewrite helper in `common/clients/clickhouse.py` adds the
   filter automatically for tables registered as tombstone-aware.
4. **DLP false positives on legitimate tool outputs.** Email-looking
   tokens, bank-routing-number-shaped strings can trigger noise.
   Mitigation: seeded patterns conservative; per-workspace rules can
   disable or change action to `flag` rather than `redact`/`block`;
   DLP events carry classification labels only (never the match text)
   so privacy officers can triage without exposure.
5. **Residency enforcement slowdown on hot read paths.** Every
   visibility resolution now hits the residency check. Mitigation:
   60 s Redis cache for residency configs; in-process LRU for the
   workspace → config lookup.
6. **Subject-hash-salt rotation.** Rotating the salt produces a new
   hashing chain; old tombstones can still be verified against the
   old salt but NEW erasures of SAME subjects would hash differently.
   Mitigation: document salt as a rotation event, not a routine
   change; operators keep a salt-history record; tombstones carry
   `salt_version` for lookup.
7. **Consent propagation latency.** A revocation must propagate to
   agent composition + analytics in ≤ 5 minutes (SC-006). Mitigation:
   `consent_propagator.py` APScheduler worker runs every 60 s; updates
   a denormalised `revoked_user_ids` set in Redis that composition +
   analytics consult.

## Phase 0: Research

**Status**: ✅ Complete — see [research.md](research.md).

15 decisions (D-001 through D-015) cover: no existing `privacy/` BC
to absorb, `CascadeAdapter` registry pattern, PostgreSQL
orchestrator-driven deletion (38-table map), per-store adapter
techniques, tombstone canonical payload + proof hash, Ed25519 signing
via UPD-024's key, residency enforcement in visibility resolution,
DLP dual-insertion points, seeded DLP pattern floor, consent
enforcement at `create_conversation`, PIA gating in certification,
migration 060, 24–72 h erasure hold, consent snapshot semantics, new
`privacy_officer` role.

## Phase 1: Design & Contracts

**Status**: ✅ Complete.

- [data-model.md](data-model.md) — 7 Postgres tables + Redis keys +
  Kafka topics + Vault path.
- [contracts/dsr-handling.md](contracts/dsr-handling.md) — DSR
  lifecycle + admin API + 6 handler types.
- [contracts/cascade-orchestrator.md](contracts/cascade-orchestrator.md)
  — adapter registry + tombstone construction + signing.
- [contracts/dlp-pipeline.md](contracts/dlp-pipeline.md) — rule
  engine + scanner insertion points.
- [contracts/residency-enforcer.md](contracts/residency-enforcer.md)
  — query-time check + integration at visibility resolution.
- [contracts/pia-workflow.md](contracts/pia-workflow.md) — draft →
  review → approve cycle + cert gating.
- [contracts/consent-service.md](contracts/consent-service.md) —
  first-interaction disclosure + revocation propagation.
- [quickstart.md](quickstart.md) — six walkthroughs Q1–Q6.

## Phase 2: Tasks

**Status**: ⏳ Deferred to `/speckit.tasks`.
