# Quickstart & Acceptance Scenarios: Agent Adaptation Pipeline and Context Engineering Levels

**Feature**: 068-adaptation-context-levels  
**Date**: 2026-04-19

## Setup Prerequisites

1. An active workspace with at least one deployed agent
2. The agent has at least 50 recent executions with quality/cost/latency metrics in ClickHouse
3. Operator and reviewer principals with appropriate roles (`agentops:adapt`, `agentops:review`, `agentops:apply`)
4. Migration 055 applied

---

## Scenario S1 — Manual pipeline invocation produces a proposal with expected improvement

```bash
POST /api/v1/agentops/billing-agent/adapt
{
  "workspace_id": "workspace-uuid",
  "revision_id": "revision-uuid"
}
```

Expected response `201 Created`:
```json
{
  "id": "proposal-uuid",
  "status": "proposed",
  "signal_source": "manual",
  "proposal_details": { "adjustments": [...] },
  "signals": [{"rule_type": "quality_trend", "metrics": {...}}],
  "expected_improvement": {
    "metric": "quality_score",
    "baseline_value": 0.62,
    "target_value": 0.75,
    "target_delta": 0.13,
    "observation_window_hours": 72
  },
  "expires_at": "2026-04-26T10:00:00Z"
}
```

Verify: agent configuration unchanged (`GET /api/v1/registry/agents/billing-agent` returns pre-pipeline state).

---

## Scenario S2 — Pipeline returns `no_opportunities` when agent healthy

```bash
# Agent has no quality trend, no cost regression, no failure pattern
POST /api/v1/agentops/healthy-agent/adapt
```

Expected: proposal created with `status=no_opportunities`, no `expected_improvement`, rationale explains which signals were checked and found clean.

---

## Scenario S3 — Concurrent invocations return the existing open proposal

```bash
POST /api/v1/agentops/billing-agent/adapt   # → returns proposal-A
POST /api/v1/agentops/billing-agent/adapt   # → returns the SAME proposal-A (not a duplicate)
```

Expected: second call returns existing proposal with same `id`. DB uniqueness index `ux_agentops_adaptation_one_open_per_agent` enforces this.

---

## Scenario S4 — Apply refused before approval

```bash
POST /api/v1/agentops/adaptations/{proposal_id}/apply
# proposal still in status=proposed
```

Expected `409 Conflict`: `{"error": "proposal_not_approved", "current_status": "proposed"}`. Agent unchanged.

---

## Scenario S5 — Approve then apply, outcome measured, rollback available

```bash
# 1. Approve
POST /api/v1/agentops/adaptations/{proposal_id}/review
{ "decision": "approved", "reason": "signal looks real; approving" }
# → status=approved, agent still unchanged

# 2. Apply
POST /api/v1/agentops/adaptations/{proposal_id}/apply
{ "reason": "applying during low-traffic window" }
# → status=applied, agent config updated
# Response contains pre_apply_snapshot_id and configuration hashes

# 3. Wait 72h (observation window). Scheduler measures outcome:
GET /api/v1/agentops/adaptations/{proposal_id}/outcome
# → classification="improved", observed_delta.observed_delta=0.09, expected_delta.target_delta=0.13

# 4. (Optional) Rollback within retention window
POST /api/v1/agentops/adaptations/{proposal_id}/rollback
{ "reason": "change worked but operator decided to revert" }
# → status=rolled_back
# Response: byte_identical_to_pre_apply=true (SC-004)
```

---

## Scenario S6 — Reject with reason

```bash
POST /api/v1/agentops/adaptations/{proposal_id}/review
{ "decision": "rejected", "reason": "signal appears to be one-off; no action needed" }
# → status=rejected, proposal cannot be applied

POST /api/v1/agentops/adaptations/{proposal_id}/apply
# → 409 Conflict
```

---

## Scenario S7 — Revoke approval before apply

```bash
POST /api/v1/agentops/adaptations/{proposal_id}/review { "decision": "approved" }
# → status=approved

POST /api/v1/agentops/adaptations/{proposal_id}/revoke-approval
{ "reason": "issue self-resolved; no need to apply" }
# → status=proposed (returned to proposed; requires fresh approval)

POST /api/v1/agentops/adaptations/{proposal_id}/apply
# → 409 Conflict (not approved)
```

---

## Scenario S8 — TTL expiration

```bash
# Proposal created at T, TTL=168h (7 days).
# At T+168h, scheduler runs adaptation_ttl_scanner.
# Proposal auto-transitions to status=expired.

POST /api/v1/agentops/adaptations/{proposal_id}/review
# → 409 Conflict: proposal_expired

POST /api/v1/agentops/adaptations/{proposal_id}/apply
# → 409 Conflict: proposal_expired
```

Verify: event `agentops.adaptation.expired` emitted.

---

## Scenario S9 — Orphan detection when agent archived

```bash
# 1. Create proposal for agent-A. Proposal in status=proposed.
# 2. Archive agent-A via registry:
PATCH /api/v1/registry/agents/agent-A { "status": "archived" }

# 3. Next orphan scanner cycle runs:
# Proposal auto-transitions to status=orphaned.

POST /api/v1/agentops/adaptations/{proposal_id}/review
# → 409 Conflict: agent_orphaned
```

---

## Scenario S10 — Stale detection at apply

```bash
# 1. Proposal A targets agent field "approach".
# 2. Between approval and apply, agent was updated and field was reworded such that the target is no longer meaningful.
# 3. Apply attempts:
POST /api/v1/agentops/adaptations/{proposal_id}/apply
# → 409 Conflict: proposal_stale (FR-014)
# → proposal status auto-transitions to status=stale
```

---

## Scenario S11 — Outcome inconclusive from noise

```bash
# Agent has high natural variance in quality_score.
# Post-apply observation: observed_stddev=0.15, expected_delta=0.13
# Outcome scheduler computes:
classification = "inconclusive"
variance_annotation = {
  "observed_stddev": 0.15,
  "expected_delta_magnitude": 0.13,
  "reason": "variance exceeds expected-improvement magnitude"
}
```

Verify: reviewer sees explicit "inconclusive" (not "no_change") with variance annotation.

---

## Scenario S12 — Rollback after retention window refused

```bash
# Proposal applied at T. Retention = 30 days.
# At T+31 days, operator attempts rollback:
POST /api/v1/agentops/adaptations/{proposal_id}/rollback
# → 410 Gone: rollback_window_expired
# Message: "Pre-apply snapshot beyond 30-day retention; rollback not available"
```

---

## Scenario S13 — Apply fails mid-operation, auto-recovery

```bash
# During apply, registry_service partially updates profile then connection fails.
# Apply service catches exception, detects partial state:
#   - Compares current config hash against pre-apply and expected post-apply hashes
#   - If current matches neither: auto-rolls back via pre-apply snapshot
#   - Records recovery_path="auto_rollback" on proposal
#   - Proposal transitions to status=approved (retry) or status=rejected with failure annotation
```

Verify: agent never remains in partial state; every apply-attempt either succeeds cleanly or rolls back cleanly (FR-018).

---

## Scenario S14 — Proficiency level assigned after sufficient observations

```bash
# Agent has 42 retrieval_accuracy, 35 instruction_adherence, 28 context_coherence observations.
# Min per dimension: 10. All dimensions clear minimum.

GET /api/v1/agentops/billing-agent/proficiency
{
  "level": "competent",
  "dimension_values": {
    "retrieval_accuracy": 0.82,
    "instruction_adherence": 0.78,
    "context_coherence": 0.71,
    "aggregate_score": 0.77
  },
  "observation_count": 105,
  "assessed_at": "2026-04-19T06:00:00Z"
}
```

---

## Scenario S15 — Undetermined proficiency for early-lifecycle agent

```bash
# Agent deployed 2 days ago; only 5 retrieval_accuracy observations.
GET /api/v1/agentops/new-agent/proficiency
{
  "level": "undetermined",
  "missing_dimensions": ["instruction_adherence", "context_coherence"],
  "observation_count": 5,
  "min_observations_required": 10
}
```

Verify: level is `undetermined`, not `novice` (FR-021, SC-009).

---

## Scenario S16 — Proficiency trajectory visible

```bash
GET /api/v1/agentops/billing-agent/proficiency/history?limit=20
{
  "items": [
    {"level": "competent", "assessed_at": "2026-04-19T06:00:00Z", "trigger": "scheduled"},
    {"level": "competent", "assessed_at": "2026-04-18T06:00:00Z", "trigger": "scheduled"},
    {"level": "novice",    "assessed_at": "2026-04-01T06:00:00Z", "trigger": "scheduled"},
    ...
  ]
}
```

---

## Scenario S17 — Fleet query by proficiency level

```bash
GET /api/v1/agentops/proficiency?workspace_id=...&level_at_or_below=competent
# Returns all agents at competent or novice level
```

---

## Scenario S18 — Proficiency dwell-time prevents flapping

```bash
# Agent signals hover at competent/advanced boundary.
# Dwell-time = 24h.
# Hour 0: level=advanced, assessed_at=T0
# Hour 12: computed_level=competent, but dwell-time not elapsed → row NOT appended; kept at advanced
# Hour 25: computed_level=competent, dwell-time elapsed → new row appended with level=competent
```

Verify: between T0 and T25, only one row exists (the advanced one); no flapping (FR-024, SC-010).

---

## Scenario S19 — Correlation coefficient per agent

```bash
GET /api/v1/context-engineering/correlations/billing-agent?window_days=30
{
  "agent_fqn": "billing-agent",
  "window_start": "2026-03-20T00:00:00Z",
  "window_end": "2026-04-19T00:00:00Z",
  "results": [
    {
      "dimension": "retrieval_accuracy",
      "performance_metric": "quality_score",
      "coefficient": 0.72,
      "classification": "strong_positive",
      "data_point_count": 45
    },
    {
      "dimension": "context_coherence",
      "performance_metric": "quality_score",
      "coefficient": null,
      "classification": "inconclusive",
      "data_point_count": 12
    }
  ]
}
```

Verify: inconclusive classification when `data_point_count < 30` (min threshold).

---

## Scenario S20 — Strong-negative correlation flagged

```bash
# Agent has strongly negative correlation between context_coherence and quality_score.
# Correlation scheduler emits `context_engineering.correlation.strong_negative` event.

GET /api/v1/context-engineering/correlations?workspace_id=...&classification=strong_negative
{
  "items": [
    {
      "agent_fqn": "poorly-tuned-agent",
      "dimension": "context_coherence",
      "coefficient": -0.81,
      "classification": "strong_negative",
      "data_point_count": 38
    }
  ]
}
```

Verify: quality engineer can query flagged agents as adaptation-pipeline candidates.

---

## Scenario S21 — Automatic signal ingestion (US6)

```bash
# 1. Agent deployed with baseline self_correction_loops=1.2/execution.
# 2. Over last 7 days, loops=2.8/execution (baseline doubled).
# 3. adaptation_signal_poll_interval=60min scheduler runs BehavioralAnalyzer.
# 4. convergence_regression rule fires.
# 5. Proposal created with signal_source="automatic" and signals[0].rule_type="convergence_regression".
```

Verify: proposal enters review queue identically to manual proposals; no auto-apply (FR-007).

---

## Scenario S22 — Signal source unavailable

```bash
# Evaluation framework down.
# BehavioralAnalyzer retries with exponential backoff.
# After 5 failures:
#   - Emits agentops.adaptation.ingestion_degraded event.
#   - Monitoring dashboard shows "signal_ingestion: degraded".
#   - Manual pipeline invocations still work (they re-attempt fresh fetch).
# Evaluation framework recovers:
#   - Next scheduler cycle succeeds.
#   - Emits agentops.adaptation.ingestion_recovered event.
```

---

## Scenario S23 — End-to-end lineage traceable

```bash
GET /api/v1/agentops/adaptations/{proposal_id}/lineage
{
  "proposal_id": "...",
  "signals": [{"rule_type": "quality_trend", "captured_at": "...", "metrics": {...}}],
  "proposal_created_at": "...",
  "proposal_created_by": "uuid",
  "review": { "decision": "approved", ... },
  "application": { "applied_at": "...", "applied_by": "uuid", "pre_apply_snapshot_id": "..." },
  "outcome": { "classification": "improved", ... },
  "rollback": null,
  "current_status": "applied"
}
```

---

## Scenario S24 — Backward compatibility with pre-feature proposals

```bash
# Proposal created before feature 068 landed.
# Status is "promoted" (legacy status).
GET /api/v1/agentops/adaptations/{legacy_proposal_id}
# → Returns proposal successfully with all pre-feature fields intact
# → new fields (expected_improvement, applied_at, etc.) are null
# → status remains "promoted" (historical; not retrofitted)
```

Verify: no historical proposal's status is rewritten (FR-035).

---

## Scenario S25 — Backward-compatible endpoint responses

```bash
# Test: take a snapshot of the response from any pre-existing endpoint before feature 068 deploys.
# After deploy: re-call the same endpoint with the same inputs.
# Expected: all pre-existing response fields are byte-identical; only new optional fields may have been added (FR-034, SC-014).
```
