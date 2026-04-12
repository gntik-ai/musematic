# Quickstart & Test Scenarios: Trust, Certification, and Guardrails

**Feature**: 032-trust-certification-guardrails  
**Date**: 2026-04-12

These scenarios define the minimal test cases to verify each user story independently.

---

## Scenario 1: Create Certification in Pending State

**Story**: US1 — Certification Lifecycle  
**Verifies**: FR-001, FR-002, FR-006

**Setup**: Agent with revision_id exists; authenticated trust_certifier user

**Steps**:
1. `POST /trust/certifications` with agent_id, agent_fqn, agent_revision_id
2. Inspect response

**Expected**:
- Response status 201
- Certification status is `"pending"`
- Certification is bound to the submitted `agent_revision_id`
- Audit trail entry recorded with actor and timestamp

---

## Scenario 2: Activate Certification and Verify Trust Tier Update

**Story**: US1  
**Verifies**: FR-002, FR-003, FR-011

**Setup**: Certification in pending state with at least one evidence ref attached

**Steps**:
1. `POST /trust/certifications/{id}/activate`
2. Wait for `trust_tier.updated` Kafka event (or wait 5s)
3. `GET /trust/agents/{agent_id}/tier`

**Expected**:
- Certification status is `"active"`
- `trust.events` Kafka event `certification.activated` fired
- Trust tier updates: `certification_component` increases
- Previous active certification (if any) transitions to `"superseded"`

---

## Scenario 3: Revoke Certification and Observe Trust Score Drop

**Story**: US1  
**Verifies**: FR-002, FR-006, FR-011

**Setup**: Agent with an active certification

**Steps**:
1. `POST /trust/certifications/{id}/revoke` with reason
2. `GET /trust/agents/{agent_id}/tier`

**Expected**:
- Status transitions to `"revoked"` with reason recorded
- Audit trail records revocation with actor
- Trust tier drops: `certification_component` decreases
- `certification.revoked` event on `trust.events`

---

## Scenario 4: Certification Expiry Auto-Transition

**Story**: US1  
**Verifies**: FR-004

**Setup**: Certification with `expires_at` = 1 second in the future

**Expected**:
- APScheduler job (or forced execution) transitions status to `"expired"` after expiry
- `certification.expired` event on `trust.events`

---

## Scenario 5: Guardrail Blocks Prompt Injection

**Story**: US2 — Layered Guardrail Pipeline  
**Verifies**: FR-014, FR-015, FR-016, FR-018

**Setup**: Guardrail pipeline configured for workspace

**Steps**:
1. `POST /trust/guardrails/evaluate` with layer=`prompt_injection`, prompt containing "Ignore all previous instructions"

**Expected**:
- Response: `allowed: false`, `layer: "prompt_injection"`, `policy_basis` populated
- `BlockedActionRecord` created in database with layer, policy_basis, input_context_hash
- `guardrail.blocked` event published on `trust.events`

---

## Scenario 6: Guardrail Fail-Closed on Layer Unavailable

**Story**: US2  
**Verifies**: FR-018

**Setup**: Mock the output moderation layer to raise an exception

**Expected**:
- Guardrail pipeline returns `allowed: false`
- `BlockedActionRecord` created with `policy_basis: "guardrail_layer_unavailable"`
- No exception propagates to the API caller (500 error)

---

## Scenario 7: Pre-Screener Blocks Known Jailbreak in <10ms

**Story**: US3 — Safety Pre-Screening  
**Verifies**: FR-019, FR-020, SC-004

**Setup**: Active pre-screener rule set loaded with jailbreak patterns

**Steps**:
1. Record timestamp
2. `POST /trust/prescreener/screen` with known jailbreak phrase
3. Record timestamp

**Expected**:
- Response: `blocked: true`, `matched_rule` contains rule name, `passed_to_full_pipeline: false`
- Elapsed time < 10ms
- Full guardrail pipeline was NOT invoked (mock assertion)

---

## Scenario 8: Pre-Screener Passes Ambiguous Input to Full Pipeline

**Story**: US3  
**Verifies**: FR-021

**Setup**: Active pre-screener rules; ambiguous but not clearly violating input

**Steps**:
1. `POST /trust/prescreener/screen` with ambiguous content

**Expected**:
- Response: `blocked: false`, `passed_to_full_pipeline: true`
- Pre-screener log entry recorded with pass decision

---

## Scenario 9: Pre-Screener Rule Hot-Reload Without Restart

**Story**: US3  
**Verifies**: FR-023, SC-011

**Steps**:
1. `POST /trust/prescreener/rule-sets` with new rules including a new pattern "NEWRULE-XYZ"
2. `POST /trust/prescreener/rule-sets/{id}/activate`
3. Wait for `prescreener.rule_set.activated` Kafka event (or max 60s)
4. `POST /trust/prescreener/screen` with "NEWRULE-XYZ"

**Expected**:
- Before activation: "NEWRULE-XYZ" not blocked
- After activation (within 60s): "NEWRULE-XYZ" blocked with new rule name
- No platform restart occurred

---

## Scenario 10: OJE Pipeline — Violation Verdict Triggers Quarantine

**Story**: US4 — Observer-Judge-Enforcer Pipeline  
**Verifies**: FR-025 through FR-029

**Setup**: OJE pipeline configured with mock observer, judge (returns VIOLATION), enforcer (quarantine)

**Steps**:
1. `POST /trust/oje-configs` with observer/judge/enforcer FQNs
2. Trigger a mock observer signal for an execution anomaly
3. Observe judge verdict
4. Observe enforcer action

**Expected**:
- Judge verdict `VIOLATION` emitted with policy basis
- Enforcer calls `RuntimeControlService.StopRuntime` (mock asserted)
- Verdict stored in audit trail with full context
- `circuit_breaker.activated` NOT fired (quarantine is different from circuit breaker)

---

## Scenario 11: OJE Pipeline — ESCALATE_TO_HUMAN Verdict Notifies User

**Story**: US4  
**Verifies**: FR-028, FR-029

**Setup**: OJE pipeline configured; judge mock returns ESCALATE_TO_HUMAN

**Expected**:
- Human notification sent (via `interaction.attention` Kafka topic per §XIII)
- Verdict stored in audit trail with `enforcer_action_taken: "escalated_to_human"`

---

## Scenario 12: Recertification Trigger on New Agent Revision

**Story**: US5 — Recertification  
**Verifies**: FR-031, FR-032, FR-033

**Setup**: Agent with active certification; simulate `registry.events` Kafka event `agent_revision.published`

**Steps**:
1. Publish mock Kafka event `agent_revision.published` for the agent
2. Wait for worker consumer to process
3. `GET /trust/recertification-triggers?agent_id={agent_id}`

**Expected**:
- RecertificationTrigger created with type `revision_changed`
- New pending Certification created linked to the trigger
- `recertification.triggered` event on `trust.events`

---

## Scenario 13: Recertification Trigger Deduplication

**Story**: US5  
**Verifies**: FR-034

**Setup**: Agent with active certification

**Steps**:
1. Publish same `agent_revision.published` event twice within deduplication window
2. Check trigger count

**Expected**:
- Only one `RecertificationTrigger` created (second is silently deduplicated)
- No duplicate pending certifications

---

## Scenario 14: ATE Run Produces Structured Evidence

**Story**: US6 — Accredited Testing Environments  
**Verifies**: FR-039, FR-040, FR-041

**Setup**: ATE configuration with 3 test scenarios; certification in pending state; SimulationController mock

**Steps**:
1. `POST /trust/ate/configs` to create ATE config
2. `POST /trust/ate/runs` with ate_config_id + certification_id
3. Wait for mock `simulation.completed` Kafka event
4. `GET /trust/certifications/{id}` — check evidence_refs

**Expected**:
- ATE run started (SimulationController.CreateSimulation called)
- Upon completion: 3 CertificationEvidenceRef entries added with `evidence_type: "ate_results"`
- Each evidence entry has pass/fail status, quality score, latency
- Evidence linked to the correct certification

---

## Scenario 15: ATE Run Timeout Returns Partial Results

**Story**: US6  
**Verifies**: FR-042

**Setup**: ATE configuration with 10s timeout; mock simulation that runs 15s

**Expected**:
- ATE run status is `"timed_out"` after timeout
- Partial results (completed scenarios) recorded as evidence with `summary: "timed_out after Xs"`

---

## Scenario 16: Circuit Breaker Activates After Threshold Exceeded

**Story**: US7 — Circuit Breaker  
**Verifies**: FR-035, FR-036, FR-037

**Setup**: Circuit breaker configured with threshold=3, window=60s for agent

**Steps**:
1. Simulate 3 guardrail failures via `workflow.runtime` Kafka events
2. `GET /trust/circuit-breaker/{agent_id}/status`

**Expected**:
- After 3rd failure: `tripped: true`
- `circuit_breaker.activated` event on `trust.events`
- Human review notification sent (attention channel)
- Workflow paused (mock RuntimeControlService.PauseWorkflow asserted)

---

## Scenario 17: Circuit Breaker Disabled When Threshold = 0

**Story**: US7  
**Verifies**: FR-038

**Setup**: Circuit breaker config with `failure_threshold: 0` (disabled)

**Steps**:
1. Simulate 100 guardrail failures
2. Check circuit breaker status

**Expected**: Circuit breaker never trips; `tripped: false`

---

## Scenario 18: Trust Score Visible in Marketplace

**Story**: US7 — Trust Signals  
**Verifies**: FR-009, FR-010, FR-012, SC-007

**Setup**: Agent with active certification; simulate `trust.events` consumer

**Steps**:
1. Activate a certification (fires `certification.activated`)
2. Wait up to 30s for trust score recomputation
3. `GET /trust/agents/{agent_id}/tier`

**Expected**:
- `trust_score` > 0, `tier` = `"certified"` (assuming high score threshold met)
- `last_computed_at` updated within 30s of the certification event

---

## Scenario 19: Privacy Assessment Blocks Non-Compliant Context

**Story**: US2 / Guardrail pipeline (action_commit layer)  
**Verifies**: FR-043, FR-044

**Setup**: Mock PolicyGovernanceEngine.check_privacy_compliance to return a violation

**Steps**:
1. `POST /trust/privacy/assess` with context_assembly_id that violates data minimization

**Expected**:
- Response: `compliant: false`, `blocked: true`, violations list populated
- Context not delivered to agent

---

## Scenario 20: Coverage and Quality Gates

**Story**: All  
**Verifies**: SC-012

**Steps**:
1. Run `pytest apps/control-plane/tests/ --cov=platform.trust --cov-report=term-missing`
2. Run `ruff check apps/control-plane/src/platform/trust/`
3. Run `mypy apps/control-plane/src/platform/trust/ --strict`

**Expected**:
- Line coverage ≥ 95%
- ruff: 0 errors
- mypy: 0 errors

---

## Test Configuration Notes

- Redis: Use `REDIS_TEST_MODE=standalone` + `REDIS_URL=redis://localhost:6379`
- Kafka: Use in-process asyncio queue fallback (local mode per constitution)
- SimulationController gRPC: Mock via `unittest.mock.AsyncMock` on `SimulationControllerClient`
- RuntimeControlService gRPC: Mock via `AsyncMock` on `RuntimeControllerClient`
- PolicyGovernanceEngine: Mock via `AsyncMock` — do not test cross-context logic here
- All tests in `apps/control-plane/tests/integration/trust/` and `tests/unit/trust/`
