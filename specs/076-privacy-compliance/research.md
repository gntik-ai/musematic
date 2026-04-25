# Phase 0 Research: Privacy Compliance (GDPR / CCPA)

**Feature**: 076-privacy-compliance
**Date**: 2026-04-25

## Scope

Create `privacy_compliance/` as a new bounded context. One Alembic
migration (060) adds 7 tables. The cascade-deletion orchestrator
must handle **38 PII-bearing tables across 14 BCs** + 5 other data
stores (Qdrant, OpenSearch, S3, ClickHouse, Neo4j). Constitution gates:
rule 15 (cascade deletion), rule 16 (tombstones), rule 18 (residency at
query time), AD-17 (tombstone-based RTBF proof), rule 9 (audit chain),
rule 33 (2PA on PIA approvals).

## Decisions

### D-001 — No existing `privacy/` BC to absorb

**Decision**: Start a fresh `privacy_compliance/` bounded context. The
constitution note about "absorbing `privacy/` baseline
differential-privacy into privacy_compliance" does not describe reality
— the codebase has no `privacy/` BC today; it has two narrow helpers:

- `context_engineering/privacy_filter.py` (~161 lines, access-control
  filtering by classification tag).
- `trust/privacy_assessment.py` (~31 lines, policy-engine wrapper).

Both are **access-control utilities**, NOT deletion / RTBF services.
Treat them as unchanged dependencies. The new `privacy_compliance/`
BC builds cascade deletion, DSR handling, DLP, residency, PIA, and
consent from scratch.

**Rationale**: Preserves brownfield rule 1 (never rewrite) — neither
helper is a functional fit for what UPD-023 needs. They remain where
they are.

### D-002 — Pluggable `CascadeAdapter` registry with explicit enumeration

**Decision**: Implement cascade deletion via a registry of
`CascadeAdapter` instances. Each adapter handles ONE data store
(PostgreSQL, Qdrant, OpenSearch, S3, ClickHouse, Neo4j-on-Postgres-
fallback). The registry is statically populated at module import time;
a CI static-analysis check enforces that every new data store added
to the platform also registers an adapter (constitution rule 25
analogue: every new BC gets an E2E suite; every new store gets a
cascade adapter).

Signature:

```python
class CascadeAdapter(ABC):
    store_name: str  # "postgresql", "qdrant", "opensearch", ...

    async def dry_run(self, subject_user_id: UUID) -> CascadePlan: ...
    async def execute(self, subject_user_id: UUID) -> CascadeResult:
        """Returns per-table/collection/index/bucket counts."""

class CascadeOrchestrator:
    def __init__(self, adapters: list[CascadeAdapter]): ...
    async def run(
        self, dsr_id: UUID, subject_user_id: UUID, *, dry_run: bool = False
    ) -> Tombstone: ...
```

**Rationale**: Open-closed — adding a new data store means adding one
adapter file, not editing the orchestrator. Idempotent: each adapter's
`execute()` is a no-op on already-deleted records.

### D-003 — PostgreSQL adapter: application-layer orchestrated, NOT FK cascade

**Decision**: The PostgreSQL adapter enumerates all **38 PII-bearing
tables across 14 BCs** (per Phase 0 discovery) and issues per-table
`DELETE WHERE user_id = ? OR subject_user_id = ? OR created_by = ? …`
statements inside a single transaction, ordered by FK dependency
(child tables before parent). The per-table column-name map is
declared statically as a Python dict; a CI check diffs this map
against the codebase's actual `ForeignKey("users.id")` uses and fails
the build on drift.

**Rationale**: FK `ON DELETE CASCADE` coverage is incomplete today
(116 cascades mostly on workspace scope, not user scope per Phase 0).
Migrating all 38 tables to add `ON DELETE CASCADE` would be a large
surgery on existing code with cross-BC coordination risk. The
explicit orchestrator is the safer brownfield choice.

**Alternatives considered**:
- Retrofit `ON DELETE CASCADE` onto every `users.id` FK — rejected:
  too many migrations, too much risk of accidental data loss if a
  cascade misbehaves.
- Query-time soft deletes (users → tombstone, other tables read-through
  filter) — rejected: does not satisfy GDPR "erase the data" — the
  bytes must go.

### D-004 — Data-store adapters: per-store techniques

**Decision**:

| Adapter | Mechanism | Source |
|---|---|---|
| **PostgreSQL** | 38-table enumerated `DELETE WHERE` in a single tx | D-003 |
| **Qdrant** | `delete_points(filter={"must":[{"key":"user_id","match":{"value":...}}]})` | Existing client helper from `common/clients/qdrant.py:171` |
| **OpenSearch** | `delete_by_query(index="*", body={"query":{"term":{"user_id":...}}})` | Existing helper from `common/clients/opensearch.py:179` |
| **S3** | New `delete_objects_matching_prefix(bucket, prefix=f"users/{user_id}/")` helper — list + batch-delete 1,000 objects per `delete_objects` call | Extend `common/clients/object_storage.py:104` |
| **ClickHouse** | Tombstone-column pattern (add `is_deleted BOOLEAN` to PII-bearing rollup tables); queries filter; archival compactor permanently drops rows monthly | Phase 0 found no existing compliance-delete pattern; this is net-new |
| **Neo4j** | The platform's Neo4j "client" is a PostgreSQL fallback on `graph_nodes` + `graph_edges` tables — graph traversal runs in SQL today. Adapter performs `DELETE FROM graph_nodes WHERE owner_user_id = ?` + cascades to edges. When a real Neo4j driver later lands, the adapter signature stays the same; implementation swaps. | `common/clients/neo4j.py` (local-mode-only today) |

**Rationale**: Each store's adapter uses the existing idiomatic
deletion API. S3 needs a small new helper (one helper, one file).
ClickHouse's lack of hard deletes is bridged with a tombstone column +
monthly compactor — standard OLAP pattern.

### D-005 — Tombstone canonical-payload + proof-hash computation

**Decision**: The tombstone's `proof_hash` = SHA-256 of the canonical
JSON of `{subject_user_id_hash, entities_deleted, cascade_log,
created_at_iso}` where:

- `subject_user_id_hash = SHA-256(subject_user_id + platform_salt)` —
  we deliberately record a hash, not the raw subject ID, so the
  tombstone never contains the subject's PII (AD-17 + FR-008).
- `entities_deleted` is a dict `{store_name: count}` with stores sorted
  alphabetically.
- `cascade_log` is a list of per-stage objects
  `{store_name, status, started_at_iso, completed_at_iso, affected_count, error?}`
  ordered by `started_at_iso`.
- Canonical JSON: `json.dumps(..., sort_keys=True, separators=(",",":"))`.
- `platform_salt` is an operator-provisioned secret in Vault (per
  UPD-040); an env-var fallback during rollout. Rotating the salt
  produces a new hashing chain from that point forward; prior
  tombstones remain verifiable with the prior salt (operators keep a
  salt history).

**Rationale**: Matches UPD-024's canonical-JSON convention for the
audit chain. Hashing the subject ID (rather than storing it) satisfies
AD-17 — the tombstone never contains PII.

### D-006 — Tombstone signing via UPD-024's Ed25519 key

**Decision**: Export tombstones via `POST /api/v1/privacy/dsr/{id}/
tombstone/signed` — the platform signs the tombstone JSON with the
same Ed25519 signing key used by UPD-024's audit chain attestations.
External assessors fetch the public key from
`/api/v1/security/audit-chain/public-key` (UPD-024) and verify.

**Rationale**: Single trust anchor per install (UPD-024's signing
key). Avoids introducing a second signing authority. External
verification follows the same protocol as audit-chain attestations.

### D-007 — Residency enforcement at visibility resolution

**Decision**: Residency check lives in
`policies/gateway.py`'s `EffectiveVisibility` resolution path (Phase
0 found this at lines 45–68) — BEFORE FQN pattern matching, add:

```python
if (residency := await _residency_service.get_config(workspace_id)) is not None:
    origin_region = request_context.get("origin_region", "unknown")
    if origin_region != residency.region_code and origin_region not in residency.allowed_transfer_regions:
        raise ResidencyViolation(workspace_id, origin_region, residency.region_code)
```

`origin_region` is derived from an authenticated platform header
`X-Origin-Region` set by ingress (or by the caller's deployment
region for service-to-service calls). Unauthenticated/missing header
→ `origin_region = "unknown"` → treated as disallowed when residency
is configured (fail-closed).

**Rationale**: Query-time enforcement (FR-013), centralised at the
visibility layer so every query-and-read path inherits it for free.

### D-008 — DLP pipeline insertion points

**Decision**: Two insertion points, one per data direction:

1. **Outbound** (tool output → agent): intercept in
   `policies/gateway.py:187` `ToolGatewayService.sanitize_tool_output()`
   — after existing sanitisation, call `dlp_scanner.scan(output,
   workspace_id, direction="outbound")` and apply the rule's action
   (redact / block / flag).
2. **Inside the guardrail pipeline**: add a new
   `GuardrailLayer.dlp_scan` between `output_moderation` and
   `tool_control` in `trust/guardrail_pipeline.py:58`. This covers
   agent outputs that never go through a tool gateway (e.g. direct
   conversation responses).

Both insertion points log to `privacy.dlp.event` Kafka topic.

**Rationale**: Defense-in-depth — tool outputs are sanitised at two
stages (gateway + pipeline). Avoids gaps where a response bypasses
one but not the other.

### D-009 — DLP seeded pattern set (platform floor)

**Decision**: Migration 060 seeds ≥ 10 platform-wide DLP rules with
`seeded=true` (cannot be deleted; can be disabled per-workspace):

| Classification | Pattern | Action |
|---|---|---|
| `pii` | US SSN `\b\d{3}-\d{2}-\d{4}\b` | redact |
| `pii` | US phone `\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b` | flag |
| `pii` | Email address | redact |
| `pii` | IBAN `\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b` | flag |
| `pii` | EU passport | flag |
| `financial` | Credit card (Luhn + pattern) | block |
| `financial` | US routing number | flag |
| `confidential` | JWT `eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+` | redact |
| `confidential` | Platform API key `msk_[A-Za-z0-9]{32,}` | redact |
| `confidential` | Bearer token prefix | redact |

Operators can add workspace-scoped rules (`seeded=false`, deletable).
The match_summary stored in `dlp_events` is the classification label
only — NEVER the matched text.

**Rationale**: Covers the most-common categories without waiting for
operator configuration. Patterns shared with UPD-029 (feature 073's
debug-logging redaction) + UPD-026 (feature 075's output validator)
so a single library maintains them.

### D-010 — Consent disclosure at first interaction

**Decision**: In `interactions/service.py:123`
`InteractionsService.create_conversation()`, before the first message
is dispatched, call `consent_service.get_or_prompt(user_id,
workspace_id)`. If the user has no prior consent records, return a
structured `ConsentRequired` error; the UI handles this by showing
the disclosure panel. After the user submits choices, a separate
endpoint `POST /api/v1/me/consents` writes the three rows, and the
original `create_conversation` retries.

**Rationale**: Server-side enforcement (UI cannot dispatch without
the consent rows); consent text + UI are UPD-042 concerns (user
self-service settings). This feature ships only the enforcement +
tracking; the rendering is a follow-up.

### D-011 — PIA gating in `trust/services/certification_service`

**Decision**: Extend
`trust/services/certification_service.py`'s `request_certification`
pre-flight (the same service that feature 075 extends for model
cards):

```python
agent = await agents_repo.get(agent_id)
pia_required = any(c in DATA_CATEGORIES_REQUIRING_PIA
                   for c in agent.declared_data_categories)
if pia_required:
    pia = await pia_service.get_approved_pia(agent_id)
    if pia is None:
        raise CertificationBlocked(reason="pia_required", detail=...)
```

`DATA_CATEGORIES_REQUIRING_PIA = {"pii", "phi", "financial", "confidential"}`.

**Rationale**: Single-line addition to an existing path; reuses the
pattern feature 075 establishes for model-card-gated certification.

### D-012 — Alembic migration number

**Decision**: **060**. Chain is 057 → 058 → 059 → 060.

### D-013 — Cascade staging (24 h optional hold)

**Decision**: Erasure DSRs default to immediate cascade. Operators
can configure a platform-wide `PRIVACY_ERASURE_HOLD_HOURS` setting
(default `0`; max `72`). When > 0, a submitted erasure DSR sits at
`status='scheduled'` until the hold expires, during which a
superadmin can cancel it. A Kafka event
`privacy.dsr.scheduled_with_hold` fires on submission.

**Rationale**: GDPR requires "within one month"; a 24–72h hold is
operationally protective (typo protection, mistaken submission) while
staying well within the legal window.

### D-014 — Consent in-flight training snapshot semantics

**Decision**: Training jobs that have already snapshotted their
corpus (snapshot_at < revocation_at) complete as scheduled.
Training jobs that snapshot corpus AFTER a consent revocation exclude
the revoked user. This is a standard "snapshot isolation" pattern.
The snapshot timestamp is recorded on each training job for audit.

**Rationale**: Complying with revocation retroactively during
mid-flight jobs is impractical; the law allows this with proper
documentation of the snapshot semantics.

### D-015 — Admin-API role model

**Decision**: A new `privacy_officer` role is added to
`RoleType` (auth schemas). Permissions:
- CRUD DSR: platform_admin, privacy_officer, superadmin.
- Approve PIA: privacy_officer, superadmin (cannot self-approve —
  rule 33 2PA).
- Review DLP events: privacy_officer, compliance_officer, superadmin.
- Configure DLP rules: privacy_officer, platform_admin, superadmin.
- Configure residency: platform_admin, superadmin (not privacy_officer
  — residency is platform infrastructure, not privacy-policy).

This is the first new role introduced in the audit pass; UPD-024's
later iteration may extend the role catalogue.

**Rationale**: Separation of duties — privacy compliance operators
can do their job without superadmin scope; platform infra stays with
platform_admin.

## Deferred / future

- **Real Neo4j driver integration** — adapter interface supports it;
  current impl uses the PostgreSQL fallback.
- **ClickHouse monthly compactor** — UPD-024 or ops feature could
  schedule hard deletion of tombstoned rows.
- **PIA templates (domain-specific questionnaires)** — v1 ships
  free-form + structured JSON; domain templates are future.
- **Subject-hash-salt rotation tooling** — v1 expects operator to
  rotate manually; a rotation CLI is follow-up.
- **DLP ML-based detection** (beyond regex) — v1 ships regex-only.
