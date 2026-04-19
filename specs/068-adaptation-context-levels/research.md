# Research: Agent Adaptation Pipeline and Context Engineering Levels

**Feature**: 068-adaptation-context-levels  
**Date**: 2026-04-19  
**Phase**: 0 — Research & Discovery

## Codebase Survey Findings

### Existing Implementation (Critical Discovery)

The `agentops/adaptation/` module **already exists** with a partial pipeline, and `agentops_adaptation_proposals` **already exists** as a DB table. This feature formalizes, hardens, and extends those capabilities — it does not create them from scratch.

```
apps/control-plane/src/platform/agentops/
├── adaptation/
│   ├── analyzer.py              # ✅ BehavioralAnalyzer: 4 signal rules (quality_trend, cost_quality, failure_pattern, tool_utilization)
│   ├── pipeline.py              # ✅ AdaptationPipeline: propose → review → ATE-test → promote
│   └── __init__.py
├── health/                       # 5-dimension health scoring
├── regression/                   # Statistical regression detection
├── canary/                       # Canary deployment lifecycle
├── cicd/                         # 5-gate CI/CD gate evaluation
├── retirement/                   # Decommissioning workflow
├── governance/                   # Retirement/recertification triggers + grace period
├── models.py                    # 10 tables (incl. agentops_adaptation_proposals)
├── schemas.py
├── service.py                   # AgentOpsService (facade; methods for propose/review/list already exist)
├── repository.py
├── router.py                    # POST /{agent_fqn}/adapt + POST /adaptations/{id}/review already live
├── events.py                    # agentops.adaptation.proposed/reviewed/completed already emitted
├── exceptions.py
└── dependencies.py

apps/control-plane/src/platform/context_engineering/
├── quality_scorer.py            # QualityScorer: 6 quality dimensions (relevance, freshness, authority, contradiction_density, token_efficiency, task_brief_coverage)
├── drift_monitor.py             # DriftMonitor: quality degradation detection
├── compactor.py                 # 4 compaction strategies
├── privacy_filter.py
├── models.py                    # 5 tables
├── service.py                   # ContextEngineeringService
└── ...
```

### Existing `agentops_adaptation_proposals` Schema

```
id UUID PK, agent_fqn, workspace_id, revision_id,
status ENUM (proposed, no_opportunities, approved, rejected, testing, passed, failed, promoted),
proposal_details JSONB, signals JSONB[],
review_reason, reviewed_by, reviewed_at,
candidate_revision_id, evaluation_run_id,
completed_at, completion_note
```

### Existing Pipeline Flow

```
1. BehavioralAnalyzer.analyze(agent_fqn, workspace_id) → list[AdaptationSignal]
   - 4 rules: quality_trend, cost_quality, failure_pattern, tool_utilization
2. propose_adaptation() → creates proposal (status=proposed) or no_opportunities
3. review_adaptation(decision=approved|rejected)
   - If approved: creates candidate_revision + submits ATE evaluation → status=testing
4. ATE completion → status=passed | failed
5. If passed: candidate promoted to production → status=promoted
```

### Gaps vs Feature 068 Spec

| Spec Requirement | Existing | Gap |
|---|---|---|
| Proposal includes **expected_improvement** field (FR-002) | `proposal_details` JSONB has adjustments but no explicit target metric | Add dedicated column |
| Approval → **apply** is explicit operator action with pre-apply snapshot (FR-013) | Approval auto-triggers ATE+promote; no human-gated apply step; no pre-apply snapshot | Insert apply step + snapshot |
| **Byte-identical rollback** of applied adaptation (FR-017) | No rollback path (only ATE failure → status=failed) | New rollback operation |
| **Post-apply outcome** measurement in production (FR-015) | ATE result is pre-apply validation; no post-production outcome record | New outcome table |
| **TTL expiration** of pending proposals (FR-010) | No TTL scanner | Scheduler + status=expired |
| **Orphan** state when agent deleted (FR-011) | No orphan detection | Scanner + status=orphaned |
| **Stale** state when target fields no longer exist (FR-014) | Not validated at apply | Validation at apply time |
| **Revoke approval** before apply (FR-009) | No revoke path | New transition |
| **One proposal per agent** concurrent enforcement (FR-012) | Not enforced — multiple proposals can coexist | Add uniqueness check |
| **Proficiency level per agent** (FR-019–024) | Not computed | New entity + scanner |
| **Context-performance correlation** (FR-025–028) | Not computed | New entity + scanner |
| **Convergence signal ingestion** from evaluation (FR-029) | BehavioralAnalyzer reads ClickHouse usage events; convergence not explicitly ingested | Add 5th signal rule |

### Migration Numbering

Latest migration: `054_trajectory_evaluation_schema.py` (feature 067) → next is **055**.  
Down revision: `"054_trajectory_evaluation_schema"`.

### Existing Settings

`AgentOpsSettings` already exists in `config.py` with health scoring, canary, retirement settings. Need additions for adaptation lifecycle (TTL, observation window, rollback retention) and proficiency (min observations, dwell time).

### APScheduler Pattern

The codebase uses **FastAPI lifespan-attached schedulers** (not APScheduler directly) — `SchedulerService.tick()` pattern with periodic scans started in app startup. Existing schedulers: `analytics_budget_scheduler`, `context_engineering_drift_scheduler`, `memory_scheduler`, `goal_auto_completion_scheduler`, `notifications_webhook_retry_scheduler`, etc. Same pattern will be used for the new scanners (adaptation_ttl, adaptation_orphan, adaptation_outcome, proficiency_recomputer, correlation_recomputer).

### Self-Correction Convergence Data

Already available in ClickHouse `analytics_usage_events.self_correction_loops` (UInt32) field, aggregated to hourly/daily/monthly rollups. BehavioralAnalyzer reads ClickHouse via `clickhouse_client.execute()` pattern — same pattern will be used for the convergence signal rule.

### Agent Configuration Mutability

`registry_agent_profiles` mutable fields: `display_name`, `purpose`, `approach`, `role_types`, `tags`, `visibility_agents`, `visibility_tools`, `mcp_server_refs`. **Immutable**: `fqn`, `local_name`, `namespace_id`, `sha256_digest`, `manifest_snapshot`. Adaptations modify the mutable fields OR create a new `AgentRevision` (which is the existing pattern for behavior changes).

### Existing Endpoints (Agentops Adaptation)

```
POST /api/v1/agentops/{agent_fqn}/adapt                    → propose
GET  /api/v1/agentops/{agent_fqn}/adaptation-history       → list
POST /api/v1/agentops/adaptations/{proposal_id}/review     → approve/reject
```

No apply, rollback, revoke, outcome, or TTL endpoints exist yet.

---

## Decisions

### D-001: Extend existing adaptation pipeline — do not rewrite

- **Decision**: Extend `agentops/adaptation/pipeline.py` and `agentops/adaptation/analyzer.py` additively. Reshape the `AdaptationPipeline` class to add `apply()`, `rollback()`, `revoke_approval()`, `compute_outcome()` methods alongside the existing `propose()` and `review()` methods. Keep existing `testing/passed/failed/promoted` statuses working while adding new ones for the full spec state machine.
- **Rationale**: Brownfield Rule 1. Existing production behavior (propose + review + ATE + promote) must continue to work; rewriting would break feature 062+ certification flows that depend on agentops/adaptation.
- **Alternatives**: New `adaptation_v2/` module — rejected; diverges from existing patterns and creates a parallel system.

### D-002: Extend `agentops_adaptation_proposals` table (migration 055) — no new proposal table

- **Decision**: Migration 055 adds columns to existing table: `expected_improvement JSONB NULL`, `pre_apply_snapshot_key TEXT NULL`, `applied_at TIMESTAMPTZ NULL`, `applied_by UUID NULL`, `rolled_back_at TIMESTAMPTZ NULL`, `rolled_back_by UUID NULL`, `rollback_reason TEXT NULL`, `expires_at TIMESTAMPTZ NULL`, `revoked_at TIMESTAMPTZ NULL`, `revoked_by UUID NULL`, `revoke_reason TEXT NULL`, `signal_source VARCHAR(32) NULL` (manual/automatic/scheduled). Extend `adaptation_proposal_status` enum with new values: `applied`, `rolled_back`, `expired`, `orphaned`, `stale`, `revoked`.
- **Rationale**: Brownfield Rule 6 (additive enum values) + Rule 7 (backward-compatible APIs). Existing proposals continue to load with NULL in new columns.
- **Alternatives**: New table linked by FK — rejected; splits the state machine across two tables and complicates transitions.

### D-003: New `agentops_adaptation_outcomes` table

- **Decision**: New table stores post-apply outcome measurements: `id`, `proposal_id FK → agentops_adaptation_proposals`, `observation_window_start`, `observation_window_end`, `expected_delta JSONB`, `observed_delta JSONB`, `classification VARCHAR(32)` (`improved`, `no_change`, `regressed`, `inconclusive`), `variance_annotation JSONB`, `measured_at`. Immutable once `measured_at` is set.
- **Rationale**: Outcome is a distinct entity from the proposal — one proposal produces zero or one outcome record; decoupling simplifies querying and preserves proposal immutability.
- **Alternatives**: Inline outcome fields in proposals table — rejected; would mix lifecycle concerns.

### D-004: New `agentops_adaptation_snapshots` table

- **Decision**: New table `agentops_adaptation_snapshots` (`id`, `proposal_id FK`, `snapshot_type` (pre_apply | post_apply), `configuration_hash`, `configuration JSONB`, `created_at`, `retention_expires_at`). Retention expiration scanner drops rows after `adaptation_rollback_retention_days` (default 30). The snapshot includes the exact pre-apply configuration state for byte-identical rollback.
- **Rationale**: FR-013 (byte-identical snapshot) + FR-017 (rollback within retention window) + SC-004 (100% byte-identity).
- **Alternatives**: Store in MinIO — rejected; 30-day retention fits PostgreSQL easily and simplifies transactional rollback.

### D-005: New `agentops_proficiency_assessments` table

- **Decision**: New table `(id, agent_fqn, workspace_id, level VARCHAR(32), dimension_values JSONB, observation_count INT, trigger VARCHAR(32), assessed_at TIMESTAMPTZ)`. Levels: `undetermined`, `novice`, `competent`, `advanced`, `expert`. Each new assessment appends a row — historical trajectory is the full row set filtered by `(agent_fqn, workspace_id)`.
- **Rationale**: FR-019 (ordered scale), FR-023 (trajectory over time). Append-only design avoids update-in-place complexity and provides full history for SC-010 (dwell-time hysteresis verification).
- **Alternatives**: Single-row-per-agent with updates — rejected; loses trajectory.

### D-006: New `context_engineering_correlation_results` table

- **Decision**: New table `(id, workspace_id, agent_fqn, dimension VARCHAR(64), performance_metric VARCHAR(64), window_start, window_end, coefficient FLOAT, classification VARCHAR(32), data_point_count INT, computed_at)`. Cached per (agent, dimension, performance_metric, window) tuple. Recomputed daily by a scheduler.
- **Rationale**: FR-025 (correlation per dimension × metric × window), FR-027 (data-point count in result). Caching avoids recomputing on every read; SC-011 (reproducibility) is satisfied because computation is deterministic from stored inputs.
- **Alternatives**: Compute on demand — rejected; expensive for fleet-wide queries.

### D-007: Extend `AgentOpsSettings` — no new settings class

- **Decision**: Add fields to existing `AgentOpsSettings`:
  - `adaptation_proposal_ttl_hours: int = 168` (7 days)
  - `adaptation_observation_window_hours: int = 72` (3 days)
  - `adaptation_rollback_retention_days: int = 30`
  - `adaptation_signal_poll_interval_minutes: int = 60`
  - `proficiency_min_observations_per_dimension: int = 10`
  - `proficiency_dwell_time_hours: int = 24`
- **Rationale**: Brownfield Rule 4 (use existing patterns). `AgentOpsSettings` already exists; extending keeps operator-configurable knobs in one place.

### D-008: Extend `ContextEngineeringSettings` for correlation

- **Decision**: Add to existing `ContextEngineeringSettings`:
  - `correlation_window_days: int = 30`
  - `correlation_min_data_points: int = 30`
  - `correlation_recompute_interval_hours: int = 24`
- **Rationale**: Correlation logic lives in `context_engineering/` (it reads both context quality from context_assembly_records and performance from ClickHouse), so its settings belong there.

### D-009: Migration 055, `down_revision = "054_trajectory_evaluation_schema"`

- **Decision**: Single migration `055_adaptation_pipeline_and_proficiency.py`. Adds: (a) 12 columns to `agentops_adaptation_proposals`, (b) 6 enum values to `adaptation_proposal_status`, (c) new table `agentops_adaptation_outcomes`, (d) new table `agentops_adaptation_snapshots`, (e) new table `agentops_proficiency_assessments`, (f) new table `context_engineering_correlation_results`, (g) 2 new enums (`proficiency_level`, `outcome_classification`, `correlation_classification`, `snapshot_type`).
- **Rationale**: Single migration keeps the feature atomic; rolling back one rolls back all.

### D-010: Extend `BehavioralAnalyzer` with 5th signal rule (convergence)

- **Decision**: Add `_analyze_convergence_regression(agent_fqn, workspace_id)` to `BehavioralAnalyzer`. Reads `analytics_usage_events.self_correction_loops` over the configured window; compares against a baseline; emits `AdaptationSignal(rule_type="convergence_regression")` when loops-per-execution exceeds baseline by a threshold.
- **Rationale**: FR-029 (convergence data must feed pipeline) + SC-012 (detection-to-proposal latency). The existing analyzer pattern (4 rules) extends naturally to 5.
- **Alternatives**: Separate signal ingestion service — rejected; overkill for one signal type.

### D-011: Apply step requires explicit operator action — approval ≠ apply

- **Decision**: Change existing pipeline: `review(approved)` now transitions `proposed → approved` **without** auto-triggering ATE or promote. New explicit endpoint `POST /adaptations/{id}/apply` creates pre-apply snapshot, runs ATE (existing pipeline), and on success sets status to `applied` + `applied_at` + `applied_by`. This makes the approval gate (FR-007) load-bearing and adds the snapshot + rollback surface.
- **Rationale**: FR-007, FR-013. Existing auto-promote on approval violates the spec's hard-gate requirement.
- **Migration concern**: Existing in-flight proposals in `testing`/`passed` status must continue to work. Resolution: migration 055 keeps `testing/passed/failed/promoted` statuses for backward compatibility but new proposals use `approved → applied/rolled_back` path. `promoted` status is treated as equivalent to `applied` for existing historical proposals.

### D-012: Pre-apply snapshot captures mutable `AgentProfile` fields + candidate `AgentRevision` reference

- **Decision**: `pre_apply_snapshot` JSONB in `agentops_adaptation_snapshots` captures: (a) the current mutable profile fields (display_name, purpose, approach, role_types, tags, visibility_agents, visibility_tools, mcp_server_refs), (b) the current active `revision_id` if the adaptation includes a revision change. Rollback restores (a) verbatim via `registry_service.update_agent_profile()` and reverts the active revision via `registry_service.activate_revision(previous_revision_id)`.
- **Rationale**: FR-017 (byte-identical rollback). Immutable fields don't need snapshotting. Revision references are immutable so restoring by ID is sufficient.

### D-013: Scheduler additions via existing lifespan pattern

- **Decision**: Five new schedulers attached to FastAPI lifespan:
  1. `adaptation_ttl_scanner` — scan proposed proposals where `now() > created_at + ttl_hours` → transition to `expired`
  2. `adaptation_orphan_scanner` — scan open proposals where agent is archived/deleted → transition to `orphaned`
  3. `adaptation_outcome_measurer` — scan `applied` proposals where `now() > applied_at + observation_window_hours` → compute and persist outcome
  4. `proficiency_recomputer` — daily recompute of proficiency for all agents with sufficient data
  5. `correlation_recomputer` — daily recompute of context-performance correlations
- **Rationale**: FR-010 (TTL), FR-011 (orphan), FR-015 (outcome), FR-019–024 (proficiency), FR-025–028 (correlation). Existing lifespan scheduler pattern accommodates all.

### D-014: Concurrent-proposal enforcement via unique partial index

- **Decision**: Add partial unique index `ux_agentops_adaptation_one_open_per_agent ON agentops_adaptation_proposals (workspace_id, agent_fqn) WHERE status IN ('proposed', 'approved', 'applied')`. Pipeline `propose()` catches `UniqueViolationError` → returns the existing open proposal instead of creating a duplicate.
- **Rationale**: FR-012 + SC-016 (zero duplicate open proposals). DB-level constraint prevents race conditions.

### D-015: Proficiency level derivation function — weighted average with dwell-time gate

- **Decision**: Proficiency computed as `weighted_avg(retrieval_accuracy * 0.4 + instruction_adherence * 0.3 + context_coherence * 0.3)` over the last `proficiency_min_observations_per_dimension` × 3 observations. Level thresholds: `undetermined` if any dimension < min_obs; `novice` if score < 0.4; `competent` if 0.4–0.7; `advanced` if 0.7–0.9; `expert` if ≥ 0.9. Dwell-time gate: a new assessment's level differs from the previous only if the previous level was assigned ≥ `proficiency_dwell_time_hours` ago.
- **Rationale**: FR-019 (ordered scale), FR-020 (documented derivation), FR-024 (dwell-time hysteresis). Weighted function is reproducible and fleet-comparable.

### D-016: Correlation via Pearson coefficient on paired time-series

- **Decision**: For each (agent, dimension, performance_metric, window) — fetch paired observations from `context_assembly_records` (context quality dimension) and ClickHouse `analytics_usage_events` (performance metric) joined by `execution_id`. Compute Pearson coefficient via `scipy.stats.pearsonr`. Classification: `strong_positive` ≥ 0.7, `moderate_positive` 0.3–0.7, `weak` -0.3–0.3, `moderate_negative` -0.7–-0.3, `strong_negative` ≤ -0.7, `inconclusive` when < min_data_points.
- **Rationale**: FR-025 + FR-026 + FR-027. Pearson is the industry standard; scipy is already in requirements.txt for feature 034. Out-of-scope block explicitly defers alternative methods.
