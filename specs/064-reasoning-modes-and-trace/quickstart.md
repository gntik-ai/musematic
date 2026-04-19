# Quickstart & Test Scenarios: Advanced Reasoning Modes and Trace Export

**Feature**: 064-reasoning-modes-and-trace | **Date**: 2026-04-19  
**Spec**: [spec.md](spec.md)

This document lists the acceptance scenarios that drive implementation and verification.

## Budget semantics note

- Omitted `compute_budget` means the reasoning mode is unconstrained and runs to its natural termination.
- Explicit `compute_budget=0.0` is invalid and must be rejected.
- When both workflow and step budgets exist, the Python control plane resolves the stricter one and records `effective_budget_scope` in the trace.

## S1 — DEBATE session reaches consensus before round_limit

Setup: Debate with 2 participants, round_limit=5.  
Expected:
- Session status `CONSENSUS`
- Transcript has position/critique/rebuttal/synthesis records
- `consensus_reached=true`
- One `reasoning.debate.round_completed` event per completed round

## S2 — DEBATE session hits round_limit without consensus

Expected:
- Session status `ROUND_LIMIT`
- `consensus_reached=false`
- Final event `terminated_by="round_limit"`

## S3 — DEBATE validation rejects fewer than 2 participants

Expected: Validation error before execution.

## S4 — DEBATE participant misses turn

Expected:
- `missed_turn=true` on the affected contribution
- Debate continues and finalizes normally

## S5 — DEBATE terminated by compute_budget

Expected:
- Session status `BUDGET_EXHAUSTED`
- `compute_budget_exhausted=true`
- Last round event has `terminated_by="compute_budget_exhausted"`

## S6 — SELF_CORRECTION stabilizes before max_iterations

Expected:
- Loop terminates early with `stabilized=true`
- Trace contains iteration input, critique, and refined output for each iteration

## S7 — SELF_CORRECTION hits max_iterations without stabilization

Expected:
- Loop stops at cap with final critique and answer preserved

## S8 — SELF_CORRECTION detects degradation

Expected:
- Best-scoring answer is retained
- `degradation_detected=true`

## S9 — SELF_CORRECTION oscillation is not stabilization

Expected:
- Loop runs to max_iterations

## S10 — Explicit compute_budget=0.0 rejected

Expected: Validation error.

## S11 — compute_budget > 1.0 rejected

Expected: Validation error.

## S12 — compute_budget enforced across all modes

Expected:
- All supported modes stay within tolerance of the requested budget
- `compute_budget_exhausted` is only true when termination happened because of budget

## S13 — Step budget stricter than workflow budget

Expected: `effective_budget_scope="step"`.

## S14 — Workflow budget stricter than step budget

Expected: `effective_budget_scope="workflow"`.

## S15 — Completed DEBATE trace export

Expected:
- HTTP 200
- `technique="DEBATE"`
- ordered steps with debate-specific step types

## S16 — Completed SELF_CORRECTION trace export

Expected:
- HTTP 200
- `technique="SELF_CORRECTION"`
- iteration triplets preserved in order

## S17 — Completed REACT trace export

Expected:
- HTTP 200
- thought/action/observation triplets

## S18 — In-progress trace export

Expected:
- HTTP 200
- `status="in_progress"`
- `last_updated_at` populated

## S19 — Unauthorized trace export

Expected: HTTP 403 without metadata leakage.

## S20 — Non-existent execution trace export

Expected: HTTP 404.

## S21 — Retention-expired trace export

Expected: HTTP 410.

## S22 — reasoning.debate.round_completed event emitted per round

Expected: exactly one event per round.

## S23 — reasoning.react.cycle_completed event emitted per cycle

Expected: exactly one event per cycle.

## S24 — Slow event consumer does not block reasoning

Expected: debate throughput remains effectively unchanged.

## S25 — Existing COT/TOT/REACT workloads unaffected when compute_budget is omitted

Expected: regression suite passes unchanged.
