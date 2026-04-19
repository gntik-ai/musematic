# Quickstart & Test Scenarios: Agent Contracts and Certification Enhancements

**Feature**: 062-agent-contracts-certification  
**Scope**: End-to-end test scenarios covering all 5 user stories + edge cases

---

## Setup Assumptions

- Platform is running with trust bounded context enabled
- Workspace `ws-test` exists
- Agent `finance-ops:kyc-verifier` exists in the registry
- APScheduler `trust-surveillance-cycle` and `trust-grace-period-check` jobs are enabled
- Kafka topics: `workflow.runtime`, `runtime.lifecycle`, `policy.events`, `trust.events`

---

## US1 — Contract Definition and Runtime Enforcement

### S1: Create and attach a terminate-on-time-breach contract

```http
# 1. Create contract with time constraint
POST /api/v1/trust/contracts
Authorization: Bearer <agent_owner_token>
X-Workspace-Id: ws-test

{
  "agent_id": "finance-ops:kyc-verifier",
  "task_scope": "KYC document verification",
  "time_constraint_seconds": 10,
  "enforcement_policy": "terminate"
}
# → 201 { id: "contract-A", enforcement_policy: "terminate" }

# 2. Attach to an execution
POST /api/v1/trust/contracts/contract-A/attach-execution
{ "execution_id": "exec-001" }
# → 204

# 3. Runtime: execution runs for 15 seconds
# ContractMonitorConsumer receives runtime.lifecycle event with elapsed=15s
# Expected: ContractBreachEvent created (breached_term=time_constraint)
# Expected: enforcement_action=terminate, enforcement_outcome=success
# Expected: execution transitions to contract-terminated state (distinct from user-cancel)

# 4. Verify breach event
GET /api/v1/trust/contracts/contract-A/breaches
# → breaches[0].breached_term == "time_constraint"
# → breaches[0].enforcement_action == "terminate"
# → breaches[0].target_id == "exec-001"
```

### S2: Warn-only quality breach allows continuation

```http
# 1. Create contract with quality threshold and warn policy
POST /api/v1/trust/contracts
{
  "agent_id": "finance-ops:kyc-verifier",
  "task_scope": "KYC",
  "quality_thresholds": {"accuracy_min": 0.95},
  "enforcement_policy": "warn"
}
# → 201 { id: "contract-B" }

# 2. Attach to interaction
POST /api/v1/trust/contracts/contract-B/attach-interaction
{ "interaction_id": "int-001" }
# → 204

# 3. Runtime: interaction completes with accuracy=0.90
# ContractMonitorConsumer receives evaluation event (accuracy=0.90 < 0.95)
# Expected: ContractBreachEvent created (enforcement_action=warn)
# Expected: interaction NOT terminated — continues to completion

# 4. Verify breach recorded but interaction completed
GET /api/v1/trust/contracts/contract-B/breaches
# → breaches[0].enforcement_action == "warn"

GET /api/v1/interactions/int-001
# → interaction.status == "completed" (NOT terminated)
```

### S3: Default enforcement policy is `warn`

```http
# Create contract with no enforcement_policy field
POST /api/v1/trust/contracts
{
  "agent_id": "finance-ops:kyc-verifier",
  "task_scope": "KYC",
  "cost_limit_tokens": 500
}
# → 201 { enforcement_policy: "warn" }
# Verify default is stored explicitly as "warn"
```

### S4: Contract snapshot immutability (FR-004)

```http
# 1. Create and attach contract
POST /api/v1/trust/contracts → contract-C (cost_limit_tokens=1000)
POST /api/v1/trust/contracts/contract-C/attach-execution { "execution_id": "exec-002" }
# → 204 (snapshot captured: cost_limit_tokens=1000)

# 2. Update the contract
PUT /api/v1/trust/contracts/contract-C { "cost_limit_tokens": 500 }
# → 200 (contract updated)

# 3. Simulate execution using 800 tokens (exceeds new limit of 500 but within old 1000)
# ContractMonitorConsumer uses snapshot on exec-002: cost_limit=1000
# Expected: NO breach triggered (800 < 1000 per snapshot)
GET /api/v1/trust/contracts/contract-C/breaches?target_id=exec-002
# → items: [] (no breach)
```

### S5: One-contract-per-interaction enforcement (FR-003)

```http
# 1. Attach contract-A to interaction int-002
POST /api/v1/trust/contracts/contract-A/attach-interaction { "interaction_id": "int-002" }
# → 204

# 2. Attempt to attach contract-B to the same interaction
POST /api/v1/trust/contracts/contract-B/attach-interaction { "interaction_id": "int-002" }
# → 409 Conflict: "Interaction int-002 already has a contract attached."

# 3. Re-attach same contract (idempotent)
POST /api/v1/trust/contracts/contract-A/attach-interaction { "interaction_id": "int-002" }
# → 204 (no-op, no duplicate)
```

### S6: Conflicting terms rejected at save time (FR-025)

```http
POST /api/v1/trust/contracts
{
  "agent_id": "finance-ops:kyc-verifier",
  "task_scope": "KYC",
  "cost_limit_tokens": 0,
  "expected_outputs": {"required_fields": ["decision"]}
}
# → 422 Unprocessable Entity
# { "detail": "cost_limit_tokens=0 conflicts with non-empty expected_outputs" }
```

---

## US2 — Third-Party Certifier Registration and Issuance

### S7: Register certifier and issue scoped certification

```http
# 1. Register ACME Labs
POST /api/v1/trust/certifiers
Authorization: Bearer <admin_token>
{
  "name": "ACME Labs",
  "organization": "ACME Certification Authority",
  "credentials": {"accreditation_body": "ISO/IEC 17065"},
  "permitted_scopes": ["financial_calculations", "hipaa_compliance"]
}
# → 201 { id: "certifier-acme", is_active: true }

# 2. Create certification for the agent
POST /api/v1/trust/certifications
{
  "agent_id": "agent-B-uuid",
  "agent_fqn": "finance-ops:kyc-verifier",
  "agent_revision_id": "rev-R1"
}
# → 201 { id: "cert-001", status: "pending" }

# 3. Issue with external certifier
POST /api/v1/trust/certifications/cert-001/issue-with-certifier
{
  "certifier_id": "certifier-acme",
  "scope": "financial_calculations"
}
# → 200 { external_certifier_id: "certifier-acme", certifier_name: "ACME Labs", ... }

# 4. Verify trust profile shows certifier
GET /api/v1/trust/agents/agent-B-uuid/certifications
# → cert with certifier_name="ACME Labs", scope appears
```

### S8: Out-of-scope issuance rejected (FR-010, SC-003)

```http
POST /api/v1/trust/certifications/cert-001/issue-with-certifier
{
  "certifier_id": "certifier-acme",
  "scope": "medical_diagnosis"
}
# → 422 Unprocessable Entity
# { "detail": "Scope 'medical_diagnosis' is not in ACME Labs permitted scopes." }
```

### S9: Internal and external certifications coexist (FR-018)

```http
# Activate the externally-certifier cert-001
POST /api/v1/trust/certifications/cert-001/activate
# → 200 { status: "active", external_certifier_id: "certifier-acme" }

# Create and activate a separate internal certification for the same agent
POST /api/v1/trust/certifications → cert-002 (internal, no external_certifier_id)
POST /api/v1/trust/certifications/cert-002/activate

# Both appear in trust profile
GET /api/v1/trust/agents/agent-B-uuid/certifications
# → [cert-001 (external, ACME Labs), cert-002 (internal)]
# Neither supersedes the other
```

### S10: De-listed certifier — no new certs, existing valid (FR-019)

```http
# De-list ACME Labs
DELETE /api/v1/trust/certifiers/certifier-acme
# → 204

# Existing cert-001 remains active
GET /api/v1/trust/certifications/cert-001
# → status: "active" (unchanged)

# Attempt new certification from ACME
POST /api/v1/trust/certifications/cert-NEW/issue-with-certifier
{ "certifier_id": "certifier-acme", "scope": "financial_calculations" }
# → 409 Conflict: "Certifier ACME Labs is no longer active."
```

---

## US3 — Certification Expiry and Surveillance

### S11: Active cert stays active before warning window

```http
# Create certification with expiry 30 days out
POST /api/v1/trust/certifications → cert-003 (expires_at=now+30d, status=pending)
POST /api/v1/trust/certifications/cert-003/activate → status=active

# Trigger surveillance cycle (simulate)
# SurveillanceService.run_surveillance_cycle()
# Warning window default = 7 days; 30 days out is outside window

GET /api/v1/trust/certifications/cert-003
# → status: "active" (no transition)
```

### S12: Expiry approach triggers `expiring` transition (FR-013, SC-005)

```http
# Create certification with expiry 2 days out
POST → cert-004 (expires_at=now+2d, status=pending) → activate

# Trigger surveillance cycle
# SurveillanceService: expires_at within 7-day window → transition to expiring
# Also emits trust.certification.expiring event
# Also fires operator alert via monitor.alerts

GET /api/v1/trust/certifications/cert-004
# → status: "expiring"
```

### S13: Past expiry transitions to `expired` (FR-013, SC-004)

```http
# Certification with expires_at in the past
# cert-004 from S12 with expires_at=now-1d (fast-forwarded)

# Trigger surveillance cycle
# SurveillanceService: expiring → expired

GET /api/v1/trust/certifications/cert-004
# → status: "expired"

# Verify not in active-cert lookups
GET /api/v1/trust/agents/agent-C-uuid/certifications?status=active
# → cert-004 NOT in response (SC-004)
```

### S14: Reassessment schedule triggers verdict and status transitions (FR-014, FR-015)

```http
# Create cert with weekly reassessment schedule
POST → cert-005 (reassessment_schedule="0 0 * * 0") → activate

# One week passes; SurveillanceService triggers reassessment job

# Record fail verdict
POST /api/v1/trust/certifications/cert-005/reassessments
Authorization: Bearer <compliance_officer_token>
{ "verdict": "fail", "notes": "Model output diverged from certified profile." }
# → 201 { verdict: "fail" }

# Verify certification suspended
GET /api/v1/trust/certifications/cert-005
# → status: "suspended"

# Record pass verdict to restore
POST /api/v1/trust/certifications/cert-005/reassessments
{ "verdict": "pass", "notes": "Remediation applied; criteria met." }
# → 201

GET /api/v1/trust/certifications/cert-005
# → status: "active"
```

---

## US4 — Material Change Triggers Recertification

### S15: Agent revision suspends active certification (FR-016, SC-006)

```http
# Setup: cert-006 active for agent revision R1
# Agent deploys revision R2 → emits trust.events signal (trigger_type=revision)
# SurveillanceConsumer handles material change

# Expected within 1 hour (SC-006):
GET /api/v1/trust/certifications/cert-006
# → status: "suspended"

# TrustRecertificationRequest created
GET /api/v1/trust/recertification-requests?certification_id=cert-006
# → [{ trigger_type: "revision", trigger_reference: "rev-R2", resolution_status: "pending", deadline: now+14d }]
```

### S16: Successful reassessment restores certification (FR-016, SC-007)

```http
# Post reassessment pass
POST /api/v1/trust/certifications/cert-006/reassessments
{ "verdict": "pass", "notes": "R2 validated against original criteria." }
# → 201

# Verify restored
GET /api/v1/trust/certifications/cert-006
# → status: "active"

# Recertification request resolved
GET /api/v1/trust/recertification-requests?certification_id=cert-006
# → [{ resolution_status: "resolved" }]
```

### S17: Grace period expiry causes revocation (FR-017)

```http
# cert-007 suspended, deadline passed (fast-forward past 14 days)
# SurveillanceService.check_grace_period_expiry() runs

GET /api/v1/trust/certifications/cert-007
# → status: "revoked"
# → revocation_reason: "recertification timeout"
```

### S18: Operator dismisses suspension (FR-024)

```http
POST /api/v1/trust/certifications/cert-006/dismiss-suspension
Authorization: Bearer <platform_admin_token>
{ "justification": "Tooling config change only; model weights and behavior unchanged per security review REF-20260419." }
# → 200 { status: "active" }

# Dismissal recorded
GET /api/v1/trust/recertification-requests?certification_id=cert-006
# → [{ resolution_status: "dismissed", dismissal_justification: "Tooling config change..." }]
```

---

## US5 — Contract Compliance KPI

### S19: Compliance rate query — agent scope

```http
# Background: 100 executions for finance-ops:kyc-verifier, over 30 days
#   85 compliant, 10 warned, 3 throttled, 2 terminated

GET /api/v1/trust/compliance/rates
  ?scope=agent
  &scope_id=finance-ops:kyc-verifier
  &start=2026-03-20T00:00:00Z
  &end=2026-04-19T00:00:00Z
Authorization: Bearer <compliance_officer_token>

# → 200 {
#   total_contract_attached: 100,
#   compliant: 85,
#   warned: 10,
#   throttled: 3,
#   terminated: 2,
#   compliance_rate: 0.85,
#   breach_by_term: { cost_limit: 5, time_constraint: 8, quality_threshold: 0, escalation: 2 },
#   trend: [{ date: "2026-04-18", compliant: 9, total: 10 }, ...]
# }
# Response time < 3 seconds (SC-009)
```

### S20: Compliance rate — unauthorized user denied (FR-021, SC-010)

```http
GET /api/v1/trust/compliance/rates?scope=agent&scope_id=...&start=...&end=...
Authorization: Bearer <viewer_token>   # VIEWER role, no COMPLIANCE_OFFICER

# → 403 Forbidden
```

### S21: Zero-attachment query returns "not applicable"

```http
# Agent with no contract-attached executions in window
GET /api/v1/trust/compliance/rates
  ?scope=agent&scope_id=finance-ops:other-agent&start=...&end=...
Authorization: Bearer <compliance_officer_token>

# → 200 {
#   total_contract_attached: 0,
#   compliant: 0,
#   compliance_rate: null,   # NOT 0% or 100%
#   trend: []
# }
```

---

## Edge Case Scenarios

### S22: Execution completes before monitoring can evaluate

```http
# Execution completes in < 100ms, ContractMonitor receives lifecycle event after completion
# Expected: ContractBreachEvent NOT created (no terms observed)
# Expected: Compliance record created with "not_evaluated" status (no breach)
# compliance_rate query counts this as a contract-attached run without a breach
```

### S23: Backward compatibility — interaction without contract (FR-027, SC-013)

```http
# Create interaction without attaching any contract
POST /api/v1/interactions → int-003 (no contract)

# Interaction proceeds normally through its lifecycle
# ContractMonitorConsumer receives events for int-003, finds no contract_id → skips evaluation

# No breach events created for int-003
GET /api/v1/trust/contracts  # (filter would show nothing for int-003)
# → int-003 behavior is IDENTICAL to pre-feature behavior
```
