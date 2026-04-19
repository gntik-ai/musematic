# Implementation Plan: Agent Adaptation Pipeline and Context Engineering Levels

**Branch**: `068-adaptation-context-levels` | **Date**: 2026-04-19 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/068-adaptation-context-levels/spec.md`

## Summary

Formalize and extend the **already-existing** `agentops/adaptation/` pipeline (propose → review → test → promote) into the full spec state machine (proposed → approved → applied → rolled_back, plus expired/orphaned/stale/revoked terminal states). Add two new cross-cutting observability capabilities: per-agent **proficiency level** (novice/competent/advanced/expert + undetermined) derived from context-quality signals, and per-agent **context-performance correlation** computed over a rolling window. **What exists**: `agentops_adaptation_proposals` table, `BehavioralAnalyzer` with 4 signal rules, `AdaptationPipeline` class with propose/review/ATE-test, existing Kafka events `agentops.adaptation.*`. **What this feature adds**: (1) explicit operator-triggered apply step with pre-apply snapshot, (2) byte-identical rollback, (3) post-apply outcome measurement, (4) TTL expiration + orphan + stale detection scanners, (5) revoke-approval transition, (6) 5th signal rule (convergence_regression) feeding the pipeline automatically, (7) `agentops_proficiency_assessments` table + scheduler + API, (8) `context_engineering_correlation_results` table + scheduler + API. Migration 055 extends `agentops_adaptation_proposals` with 12 columns and adds 6 enum values + 4 new tables + 3 new enums.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+, redis-py 5.x async, clickhouse-connect 0.8+, scipy ≥ 1.13 (for `pearsonr`), numpy ≥ 1.26 — all already in requirements.txt (scipy added via feature 034)  
**Storage**: PostgreSQL 16 (4 new tables + 12 new columns + 6 new enum values + 3 new enums via Alembic 055); ClickHouse (read-only — analytics_usage_events); Redis (no new keys)  
**Testing**: pytest + pytest-asyncio 8.x, ruff 0.7+, mypy 1.11+ strict  
**Target Platform**: Linux, Kubernetes  
**Project Type**: Web service — additive extension in existing FastAPI monolith  
**Performance Goals**: Detection-to-proposal latency ≤ signal-poll-interval (default 60 min) per SC-012; ingestion-degraded recovery ≤ 1 poll cycle per SC-013; correlation recomputation ≤ 24h per D-008; outcome measurement ≤ observation window + grace period per SC-003  
**Constraints**: Approval gate is load-bearing (SC-002, FR-007); pre-existing agentops & context_engineering endpoints byte-identical (SC-014, FR-034); no direct mutation outside approved-proposal path (FR-036); rollback byte-identical (SC-004, FR-017)  
**Scale/Scope**: Extensions to 8 existing files in `agentops/` + 4 existing files in `context_engineering/` + 5 new scheduler tasks + 1 migration; ~15 new or modified files total

## Constitution Check

*All principles checked against this feature design.*

| Gate | Status | Notes |
|------|--------|-------|
| **Principle I** — Modular monolith | ✅ PASS | All changes inside existing `agentops/` and `context_engineering/` bounded contexts; no new contexts |
| **Principle III** — Dedicated data stores | ✅ PASS | PostgreSQL for lifecycle records; ClickHouse read-only for performance metrics; no in-memory shared state |
| **Principle IV** — No cross-boundary DB access | ✅ PASS | `AgentOpsService` calls `registry_service` and `evaluation_service` via injected interfaces, not direct DB access; `CorrelationService` in `context_engineering/` uses ClickHouse client |
| **Principle VI** — Policy is machine-enforced | ✅ PASS | Approval gate (FR-007) enforced at service layer before any mutation call; partial unique index enforces one-open-per-agent |
| **Principle VIII** — FQN addressing | ✅ PASS | All agent references use `agent_fqn` string identifier (existing pattern) |
| **Principle IX** — Zero-trust default visibility | ✅ PASS | All proposal/proficiency/correlation queries workspace-scoped; existing RBAC reused |
| **Principle XI** — Secrets never in LLM context | ✅ PASS | No LLM calls introduced by this feature |
| **Reminder 26** — Evaluate trajectories, not just outputs | ✅ PASS | Adaptation pipeline consumes trajectory-derived signals via `BehavioralAnalyzer` reading ClickHouse; post-apply outcome measurement operates on trajectory metrics |
| **Brownfield Rule 1** — Never rewrite | ✅ PASS | `agentops/adaptation/pipeline.py` and `analyzer.py` extended additively; no file replaced wholesale |
| **Brownfield Rule 2** — Alembic migrations | ✅ PASS | All DDL in migration 055 |
| **Brownfield Rule 3** — Preserve existing tests | ✅ PASS | Existing `agentops/adaptation/` unit tests continue to pass (behavior on `propose` + `review` preserved; `apply` is new path) |
| **Brownfield Rule 4** — Use existing patterns | ✅ PASS | Repository/service/scheduler-in-lifespan/Kafka envelope/dependency-injection patterns all reused |
| **Brownfield Rule 5** — Reference existing files | ✅ PASS | All modified files cited below with exact paths |
| **Brownfield Rule 6** — Additive enum values | ✅ PASS | 6 new values added to existing `adaptation_proposal_status` enum — the enum itself is preserved |
| **Brownfield Rule 7** — Backward-compatible APIs | ✅ PASS | Existing 3 adaptation endpoints preserve their request/response shape; new fields are optional (default null); existing `testing/passed/failed/promoted` statuses remain valid for historical proposals |
| **Reminder 29** — No MinIO in app code | ✅ PASS | Snapshots stored in PostgreSQL JSONB (within 30-day retention easily handled); no object storage needed |

## Project Structure

### Documentation (this feature)

```text
specs/068-adaptation-context-levels/
├── plan.md              ✅ This file
├── spec.md              ✅ Feature specification
├── research.md          ✅ Phase 0 output
├── data-model.md        ✅ Phase 1 output
├── quickstart.md        ✅ Phase 1 output
├── contracts/
│   └── rest-api.md      ✅ Phase 1 output
└── checklists/
    └── requirements.md  ✅ Spec validation (all pass)
```

### Source Code

```text
apps/control-plane/
├── migrations/versions/
│   └── 055_adaptation_pipeline_and_proficiency.py        # NEW: 4 tables + 12 columns + 6 enum values + 3 enums
└── src/platform/
    ├── agentops/
    │   ├── adaptation/
    │   │   ├── analyzer.py                                # MODIFY: add 5th rule _analyze_convergence_regression
    │   │   ├── pipeline.py                                # MODIFY: decouple approval from auto-apply; add apply/rollback/revoke/outcome orchestration
    │   │   ├── apply_service.py                           # NEW: AdaptationApplyService (pre-apply snapshot, apply, recovery)
    │   │   ├── rollback_service.py                        # NEW: AdaptationRollbackService (byte-identical restore)
    │   │   └── outcome_service.py                         # NEW: AdaptationOutcomeService (post-apply measurement)
    │   ├── proficiency/                                   # NEW subdirectory
    │   │   ├── __init__.py
    │   │   ├── service.py                                 # NEW: ProficiencyService (compute + query)
    │   │   └── scheduler.py                               # NEW: ProficiencyRecomputerTask (daily)
    │   ├── models.py                                      # MODIFY: add columns/enum values to AdaptationProposal; add AdaptationSnapshot, AdaptationOutcome, ProficiencyAssessment models
    │   ├── schemas.py                                     # MODIFY: extend AdaptationProposalResponse; add AdaptationApplyRequest/Response, AdaptationRollbackRequest/Response, AdaptationRevokeRequest/Response, AdaptationOutcomeResponse, AdaptationLineageResponse, ProficiencyResponse, ProficiencyHistoryResponse, ProficiencyFleetResponse
    │   ├── repository.py                                  # MODIFY: add snapshot/outcome/proficiency CRUD + TTL/orphan/outcome-measurement queries
    │   ├── service.py                                     # MODIFY: extend AgentOpsService with apply/rollback/revoke/outcome/lineage/proficiency methods + 5 new scheduler tasks
    │   ├── router.py                                      # MODIFY: add 8 new routes (apply, rollback, revoke-approval, outcome, lineage, proficiency, proficiency-history, proficiency-fleet)
    │   ├── events.py                                      # MODIFY: add 9 new event types (applied, rolled_back, outcome_recorded, approval_revoked, expired, orphaned, stale, ingestion_degraded, proficiency.assessed)
    │   ├── exceptions.py                                  # MODIFY: add StaleProposalError, RollbackWindowExpiredError, OutcomeImmutableError, ApprovalRevokedError
    │   └── dependencies.py                                # MODIFY: wire new services + schedulers
    ├── context_engineering/
    │   ├── correlation_service.py                         # NEW: CorrelationService (Pearson computation + persistence + event publication)
    │   ├── correlation_scheduler.py                       # NEW: CorrelationRecomputerTask (daily)
    │   ├── models.py                                      # MODIFY: add CorrelationResult SQLAlchemy model
    │   ├── schemas.py                                     # MODIFY: add CorrelationResultResponse, CorrelationFleetResponse, CorrelationRecomputeRequest
    │   ├── repository.py                                  # MODIFY: add correlation CRUD queries
    │   ├── service.py                                     # MODIFY: expose correlation methods on existing ContextEngineeringService
    │   ├── router.py                                      # MODIFY: add 3 new routes (per-agent, fleet-query, recompute-trigger)
    │   ├── events.py                                      # MODIFY: add 2 new event types (correlation.computed, correlation.strong_negative)
    │   └── dependencies.py                                # MODIFY: wire CorrelationService + scheduler
    ├── common/config.py                                   # MODIFY: extend AgentOpsSettings (6 new fields) + ContextEngineeringSettings (3 new fields)
    └── main.py                                            # MODIFY: register 5 new schedulers in lifespan (adaptation_ttl, adaptation_orphan, adaptation_outcome_measurer, proficiency_recomputer, correlation_recomputer, snapshot_retention_gc)

apps/control-plane/tests/
├── unit/agentops/
│   ├── test_adaptation_apply_service.py                  # NEW: pre-apply snapshot, apply, recovery paths
│   ├── test_adaptation_rollback_service.py               # NEW: byte-identical restore, retention window enforcement
│   ├── test_adaptation_outcome_service.py                # NEW: classification logic, immutability
│   ├── test_adaptation_pipeline.py                       # EXTEND: new transitions (revoke, apply, rollback, expired, orphaned, stale)
│   ├── test_adaptation_analyzer.py                       # EXTEND: convergence_regression rule
│   ├── test_proficiency_service.py                       # NEW: derivation function, undetermined, dwell-time gate
│   └── test_adaptation_scanners.py                       # NEW: TTL scanner, orphan scanner, outcome measurer
├── unit/context_engineering/
│   └── test_correlation_service.py                       # NEW: Pearson computation, classification, insufficient-data
└── integration/
    ├── agentops/
    │   ├── test_adaptation_lifecycle_integration.py       # NEW: propose → approve → apply → outcome → rollback
    │   └── test_proficiency_integration.py                # NEW: cross-agent proficiency queries
    └── context_engineering/
        └── test_correlation_integration.py                # NEW: end-to-end correlation compute + strong-negative event
```

## Complexity Tracking

No constitution violations. The highest-risk behavioral change is **D-011**: separating approval from auto-apply. Existing historical proposals in `testing/passed/promoted` states must continue to load and render correctly; new proposals enter the full spec state machine (proposed → approved → applied). Migration 055 preserves legacy statuses in the enum so this works without data migration.

Second-highest risk: **byte-identical rollback** (FR-017, SC-004). The pre-apply snapshot must capture every mutable agent-profile field. `registry_service.update_agent_profile()` must accept a complete field set for restore. The rollback service verifies the post-rollback configuration hash matches the pre-apply hash and raises `RollbackIntegrityError` if they diverge — preventing silent non-byte-identical rollbacks.

## Phase 0: Research

**Status**: ✅ Complete — see [research.md](research.md)

Key decisions:

- **D-001**: Extend existing `agentops/adaptation/` additively — pipeline, analyzer, events, models all preserved
- **D-002**: Extend `agentops_adaptation_proposals` with 12 columns + 6 enum values (no new proposal table)
- **D-003**: New `agentops_adaptation_outcomes` table — immutable post-apply measurements
- **D-004**: New `agentops_adaptation_snapshots` table — pre/post-apply JSONB config with 30-day retention
- **D-005**: New `agentops_proficiency_assessments` table — append-only for full trajectory
- **D-006**: New `context_engineering_correlation_results` table — cached coefficients with unique-per-window index
- **D-007**: Extend existing `AgentOpsSettings` with 6 new fields (no new settings class)
- **D-008**: Extend `ContextEngineeringSettings` with 3 new correlation fields
- **D-009**: Migration 055, `down_revision = "054_trajectory_evaluation_schema"` — single atomic migration
- **D-010**: Add 5th analyzer rule `_analyze_convergence_regression` reading ClickHouse self_correction_loops
- **D-011**: Decouple approval from apply — reviewer approves, operator explicitly applies (load-bearing FR-007)
- **D-012**: Pre-apply snapshot captures mutable profile fields + active revision reference — sufficient for byte-identical rollback
- **D-013**: Five new schedulers attached to FastAPI lifespan (TTL, orphan, outcome, proficiency, correlation)
- **D-014**: Partial unique index enforces one open proposal per agent at DB level (SC-016)
- **D-015**: Weighted-average proficiency derivation with documented thresholds + dwell-time hysteresis
- **D-016**: Pearson correlation via `scipy.stats.pearsonr` on paired `(context_assembly_records × ClickHouse usage_events)` by execution_id

## Phase 1: Design & Contracts

**Status**: ✅ Complete

- [data-model.md](data-model.md) — 4 new tables, 12 new columns on existing, 6 enum values + 3 new enums, 11 new Kafka event types
- [contracts/rest-api.md](contracts/rest-api.md) — 11 new REST endpoints + 4 new internal service classes + 1 extended service
- [quickstart.md](quickstart.md) — 25 acceptance scenarios (S1–S25) covering adaptation lifecycle, proficiency, correlation, edge cases, and backward compatibility
