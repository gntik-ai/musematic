# Quickstart / Test Scenarios: Judge/Enforcer Governance Pipeline

**Feature**: 061-judge-enforcer-governance  
**Date**: 2026-04-18

---

## US1 — Observer Signal Triggers Judge Evaluation

### S1: VIOLATION verdict from matching policy signal

**Setup**: Fleet F1 has governance chain `[observer: platform:anomaly-detector, judge: platform:policy-judge, enforcer: platform:enforcer-1]`, bound to policy P1 (active), `verdict_to_action_mapping: {VIOLATION: block}`.

**Steps**:
1. Emit observer signal to `monitor.alerts`: `{fleet_id: F1, metric: "error_rate", value: 0.97}` where P1 threshold is 0.8.
2. Wait ≤5s (p95 SLA, SC-001).

**Expected**:
- `governance_verdicts` has a new row with `verdict_type=VIOLATION`, `policy_id=P1`, non-empty `evidence`, non-empty `rationale`.
- `governance.verdict.issued` event published with `verdict_type=VIOLATION`.
- No enforcement action yet (enforcer is downstream consumer).

---

### S2: COMPLIANT verdict when signal is below threshold

**Setup**: Same fleet F1, but signal value is 0.3 (below P1 threshold 0.8).

**Steps**:
1. Emit observer signal with `value: 0.3`.

**Expected**:
- Verdict persisted with `verdict_type=COMPLIANT`.
- Event published. No enforcement action for COMPLIANT if not mapped.

---

### S3: ESCALATE_TO_HUMAN when judge agent unavailable

**Setup**: Fleet F2, governance chain where judge FQN points to an unavailable agent.

**Steps**:
1. Emit valid observer signal.
2. Judge is unavailable; wait past `settings.governance.judge_timeout_seconds`.

**Expected**:
- Verdict persisted with `verdict_type=ESCALATE_TO_HUMAN`, rationale mentions "judge unavailable".
- `governance.verdict.issued` published.

---

### S4: No verdict when fleet has no governance chain

**Setup**: Fleet F3 has no governance chain configured.

**Steps**:
1. Emit observer signal with `fleet_id: F3`.

**Expected**:
- No verdict row created.
- Signal silently skipped by governance pipeline (no chain = no enforcement).

---

### S5: ESCALATE_TO_HUMAN when bound policy is deleted

**Setup**: Fleet F4, chain bound to policy P2 which is then deleted.

**Steps**:
1. Delete policy P2.
2. Emit observer signal for fleet F4.

**Expected**:
- Verdict persisted with `verdict_type=ESCALATE_TO_HUMAN`, rationale mentions "policy not found".

---

## US2 — Enforcer Executes Action on Verdict

### S6: block action on VIOLATION verdict

**Setup**: Fleet F1, `verdict_to_action_mapping: {VIOLATION: block}`.

**Steps**:
1. A VIOLATION verdict is issued for target agent A in fleet F1.
2. Enforcer consumes the verdict within ≤10s (p95 SLA, SC-002).

**Expected**:
- `enforcement_actions` has a row with `action_type=block`, `verdict_id` pointing to the VIOLATION verdict, `target_agent_fqn=A`, `outcome` containing block result.
- `governance.enforcement.executed` event published.

---

### S7: notify action on WARNING verdict

**Setup**: Fleet F1, `verdict_to_action_mapping: {WARNING: notify}`.

**Steps**:
1. WARNING verdict issued.
2. Enforcer processes.

**Expected**:
- `enforcement_actions` row with `action_type=notify`, outcome includes delivery receipt.

---

### S8: revoke_cert action on VIOLATION

**Setup**: Fleet F1, `verdict_to_action_mapping: {VIOLATION: revoke_cert}`. Agent A has an active certification C1.

**Steps**:
1. VIOLATION verdict for target A.
2. Enforcer processes.

**Expected**:
- `enforcement_actions` row with `action_type=revoke_cert`.
- `outcome` includes `revoked_cert_id=C1`.
- Certification C1 status is `revoked` (via `CertificationService.revoke()`).

---

### S9: log_and_continue when no mapping matches

**Setup**: Fleet F1, `verdict_to_action_mapping: {VIOLATION: block}`. Judge emits WARNING verdict.

**Steps**:
1. WARNING verdict issued (no WARNING mapping in config).
2. Enforcer processes.

**Expected**:
- `enforcement_actions` row with `action_type=log_and_continue`.
- Outcome includes `unmapped_verdict_type: WARNING` (FR-010).

---

### S10: Idempotency — retry enforcement does not duplicate side effects (SC-006)

**Setup**: Fleet F1, VIOLATION verdict V1, `verdict_to_action_mapping: {VIOLATION: block}`. Enforcement executed once.

**Steps**:
1. First enforcement: block action succeeds.
2. Enforcer retries (simulated partial failure recovery).

**Expected**:
- Only one `enforcement_actions` row for verdict V1.
- Second execution is a no-op; outcome notes "already executed".

---

## US3 — Admin Configures Governance Chain

### S11: Valid fleet chain configuration accepted

**Setup**: Agents `platform:policy-judge` (role: judge) and `platform:enforcer-1` (role: enforcer) exist.

**Steps**:
1. `PUT /api/v1/fleets/{fleet_id}/governance-chain` with valid `observer_fqns`, `judge_fqns`, `enforcer_fqns`, `verdict_to_action_mapping: {VIOLATION: block}`.

**Expected**:
- 200 response with new chain version.
- `fleet_governance_chains` has a new row with `is_current=true`.
- Previous row (if any) has `is_current=false`.

---

### S12: Chain rejected for role mismatch (FR-011, SC-005)

**Steps**:
1. `PUT` chain referencing `platform:my-agent` (role: executor) as `judge_fqns[0]`.

**Expected**:
- 422 response: `"Agent platform:my-agent does not have the judge role"`.
- No chain row created.

---

### S13: Chain rejected for non-existent agent (FR-012, SC-005)

**Steps**:
1. `PUT` chain referencing `platform:ghost-agent` which does not exist in registry.

**Expected**:
- 422 response: `"Agent platform:ghost-agent not found"`.

---

### S14: Workspace chain overrides fleet chain (FR-013)

**Setup**: Fleet F1 has chain with judge J1. Workspace W1 has chain with judge J2.

**Steps**:
1. Emit observer signal with `fleet_id: F1, workspace_id: W1`.

**Expected**:
- Signal routed to judge J2 (workspace chain wins).
- Verdict's `judge_agent_fqn` = J2's FQN.

---

## US4 — Audit Query

### S15: Compliance user lists verdicts by fleet and time range

**Steps**:
1. AUDITOR user calls `GET /api/v1/governance/verdicts?fleet_id=F1&from_time=2026-04-17T00:00:00Z&to_time=2026-04-18T23:59:59Z`.

**Expected**:
- Response includes all verdicts for F1 in the time range.
- Each item has `judge_agent_fqn`, `verdict_type`, `policy_id`, `rationale`, `source_event_id`.

---

### S16: Full verdict detail with enforcement action

**Steps**:
1. AUDITOR calls `GET /api/v1/governance/verdicts/{verdict_id}`.

**Expected**:
- Response includes `evidence` payload, `rationale`, and nested `enforcement_action` (if one exists) with `action_type` and `outcome`.

---

### S17: Non-AUDITOR user denied (FR-018, SC-009)

**Steps**:
1. VIEWER role user calls `GET /api/v1/governance/verdicts`.

**Expected**:
- 403 response: `"Insufficient role: auditor required"`.

---

### S18: Retention GC removes expired verdicts with cascade (FR-019, SC-010)

**Setup**: Verdict V1 and its enforcement action A1 are older than `settings.governance.retention_days`.

**Steps**:
1. Retention GC job runs.

**Expected**:
- `governance_verdicts` row for V1 deleted.
- `enforcement_actions` row for A1 deleted via ON DELETE CASCADE.
- Neither row appears in audit queries.

---

## US5 — Layered Judge Chain

### S19: First judge COMPLIANT → second judge runs

**Setup**: Fleet F5, chain with two judges: J1 (rule-based) and J2 (LLM-based).

**Steps**:
1. Emit observer signal.
2. J1 evaluates → COMPLIANT verdict.
3. J2 evaluates → WARNING verdict.

**Expected**:
- Two `governance_verdicts` rows: one COMPLIANT (J1), one WARNING (J2).
- Enforcer receives J2's WARNING verdict (last terminal context) for enforcement.

---

### S20: First judge VIOLATION → second judge does NOT run

**Steps**:
1. Same fleet F5.
2. J1 evaluates → VIOLATION verdict (terminal).

**Expected**:
- One `governance_verdicts` row: VIOLATION (J1).
- J2 does NOT evaluate (chain stops at terminal verdict).
- Enforcer receives J1's VIOLATION verdict.

---

## Rate Limiting

### S21: Observer flood rejected (FR-024, SC-007)

**Setup**: `settings.governance.rate_limit_per_observer_per_minute = 100`.

**Steps**:
1. Observer `platform:anomaly-detector` emits 150 signals in 60s for fleet F1.

**Expected**:
- First 100 signals processed normally.
- Signals 101–150 dropped with incident log entry.
- No duplicate verdicts.

---

## Self-Referential Chain Rejection

### S22: Circular chain rejected at save time (FR-025)

**Steps**:
1. `PUT` chain where agent J1 appears in both `judge_fqns` and `enforcer_fqns`.

**Expected**:
- 422: `"Self-referential governance chain detected: agent J1 cannot judge and enforce in the same chain"`.

---

## Enforcement Idempotency — Target Deleted

### S23: Target deleted before enforcement action

**Steps**:
1. VIOLATION verdict issued for target agent A.
2. Agent A is deleted from registry before enforcer processes.
3. Enforcer processes.

**Expected**:
- `enforcement_actions` row persisted with `outcome: {"error": "target_not_found", "target_agent_fqn": "..."}`.
- No exception or silent drop; record exists for audit.
