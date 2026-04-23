# REST API Contracts: Agent Contracts and Certification Enhancements

**Feature**: 062-agent-contracts-certification  
**Base path**: `/api/v1/trust/` (all trust endpoints share the existing trust router)  
**Auth**: JWT Bearer, workspace-scoped via `get_workspace` dependency  
**File to modify**: `apps/control-plane/src/platform/trust/router.py`

---

## New Endpoints — Certifiers

### POST /certifiers
Register a new external certifier organization.

**Auth**: PLATFORM_ADMIN or COMPLIANCE_OFFICER role

**Request body**:
```json
{
  "name": "ACME Labs",
  "organization": "ACME Certification Authority",
  "credentials": {"accreditation_body": "ISO/IEC 17065", "license_number": "ACME-2024-001"},
  "permitted_scopes": ["financial_calculations", "hipaa_compliance"]
}
```

**Response 201**:
```json
{
  "id": "uuid",
  "created_at": "2026-04-19T12:00:00Z",
  "name": "ACME Labs",
  "organization": "ACME Certification Authority",
  "credentials": {"accreditation_body": "ISO/IEC 17065", "license_number": "ACME-2024-001"},
  "permitted_scopes": ["financial_calculations", "hipaa_compliance"],
  "is_active": true
}
```

**Errors**: 409 if certifier with same name already exists.

---

### GET /certifiers
List all active certifiers.

**Auth**: Any authenticated user

**Query params**: `include_inactive=false` (default)

**Response 200**:
```json
{
  "items": [CertifierResponse, ...],
  "total": 1
}
```

---

### GET /certifiers/{certifier_id}
Get a specific certifier.

**Auth**: Any authenticated user

**Response 200**: `CertifierResponse`  
**Errors**: 404

---

### DELETE /certifiers/{certifier_id}
De-list a certifier (sets `is_active=false`). Existing certifications remain valid.

**Auth**: PLATFORM_ADMIN role

**Response 204**: No content  
**Errors**: 404

---

## New Endpoints — Agent Contracts

### POST /contracts
Create a new agent contract.

**Auth**: AGENT_OWNER or PLATFORM_ADMIN role

**Request body**:
```json
{
  "agent_id": "finance-ops:kyc-verifier",
  "task_scope": "KYC document verification only. No credit decisioning.",
  "quality_thresholds": {"accuracy_min": 0.95, "latency_max_ms": 5000},
  "time_constraint_seconds": 120,
  "cost_limit_tokens": 10000,
  "escalation_conditions": {"human_required_on": ["pii_detected", "sanction_list_match"]},
  "success_criteria": {"required_fields": ["decision", "confidence"]},
  "enforcement_policy": "terminate"
}
```

**Validation** (FR-002, FR-025):
- `enforcement_policy` must be one of `warn`, `throttle`, `escalate`, `terminate`
- Numeric limits must be ≥ 1 if present
- `cost_limit_tokens=0` paired with non-null `expected_outputs` → 422 with conflict message

**Response 201**: `AgentContractResponse`

---

### GET /contracts
List contracts for the workspace.

**Auth**: Any workspace member

**Query params**: `agent_id=<fqn>` (optional), `include_archived=false`

**Response 200**:
```json
{
  "items": [AgentContractResponse, ...],
  "total": N
}
```

---

### GET /contracts/{contract_id}
Get a specific contract.

**Auth**: Any workspace member

**Response 200**: `AgentContractResponse`  
**Errors**: 404

---

### PUT /contracts/{contract_id}
Update a contract definition. Does not affect existing attachments (snapshots are immutable).

**Auth**: AGENT_OWNER or PLATFORM_ADMIN

**Request body**: Subset of `AgentContractCreate` fields (all optional)

**Response 200**: `AgentContractResponse`  
**Errors**: 404, 422

---

### DELETE /contracts/{contract_id}
Archive a contract (soft delete). Contract cannot be archived if attached to in-flight executions.

**Auth**: AGENT_OWNER or PLATFORM_ADMIN

**Response 204**: No content  
**Errors**: 404, 409 if in-flight attachments exist

---

### POST /contracts/{contract_id}/attach-interaction
Attach a contract to an interaction (idempotent, FR-003, FR-004, FR-026).

**Auth**: AGENT_OWNER or PLATFORM_ADMIN

**Request body**:
```json
{
  "interaction_id": "uuid"
}
```

**Behavior**:
- If the interaction already has this contract attached: 204 (idempotent no-op)
- If the interaction has a different contract already: 409 Conflict

**Response 204**: No content  
**Errors**: 404 (contract or interaction not found), 409 (already has different contract), 422 (contract archived)

---

### POST /contracts/{contract_id}/attach-execution
Attach a contract to an execution (idempotent, FR-003, FR-004, FR-026).

**Auth**: AGENT_OWNER or PLATFORM_ADMIN

**Request body**:
```json
{
  "execution_id": "uuid"
}
```

**Behavior**: Same idempotency as attach-interaction.

**Response 204**: No content  
**Errors**: 404, 409, 422

---

### GET /contracts/{contract_id}/breaches
List breach events for a contract.

**Auth**: AGENT_OWNER, PLATFORM_ADMIN, or COMPLIANCE_OFFICER

**Query params**: `target_type=interaction|execution`, `start`, `end`, `limit=50`, `cursor`

**Response 200**:
```json
{
  "items": [ContractBreachEventResponse, ...],
  "next_cursor": "token|null"
}
```

---

## New Endpoints — Compliance KPI

### GET /compliance/rates
Query contract compliance rates. (FR-020, FR-021)

**Auth**: COMPLIANCE_OFFICER or PLATFORM_ADMIN (enforces FR-021)

**Query params**:
- `scope`: `agent` | `fleet` | `workspace` (required)
- `scope_id`: FQN or UUID (required)
- `start`: ISO datetime (required)
- `end`: ISO datetime (required)
- `bucket`: `daily` (default) | `hourly`

**Response 200**:
```json
{
  "scope": "agent",
  "scope_id": "finance-ops:kyc-verifier",
  "start": "2026-03-20T00:00:00Z",
  "end": "2026-04-19T00:00:00Z",
  "total_contract_attached": 100,
  "compliant": 85,
  "warned": 10,
  "throttled": 3,
  "escalated": 0,
  "terminated": 2,
  "compliance_rate": 0.85,
  "breach_by_term": {
    "time_constraint": 2,
    "cost_limit": 3,
    "quality_threshold": 5,
    "escalation": 5
  },
  "trend": [
    {"date": "2026-04-18", "compliant": 9, "total": 10},
    ...
  ]
}
```

**Special case** (edge case): `total_contract_attached=0` → `compliance_rate=null`, `trend=[]`

**Errors**: 403 (insufficient role), 422 (invalid scope or date range)

---

## Extended Existing Endpoints — Certifications

### POST /certifications/{certification_id}/issue-with-certifier
Link an external certifier to an existing certification. (FR-009, FR-010)

**Auth**: COMPLIANCE_OFFICER or PLATFORM_ADMIN

**Request body**:
```json
{
  "certifier_id": "uuid",
  "scope": "financial_calculations"
}
```

**Validation** (FR-010): `scope` must be in `certifier.permitted_scopes`

**Response 200**: Extended `CertificationResponse` with `certifier_name`, `external_certifier_id`, `certifier_credentials`

**Errors**: 404 (cert or certifier not found), 422 (scope outside permitted_scopes), 409 (certifier is inactive)

---

### POST /certifications/{certification_id}/dismiss-suspension
Operator manually dismisses a material-change suspension. (FR-024)

**Auth**: PLATFORM_ADMIN role

**Request body**:
```json
{
  "justification": "Reviewed change; model weights unchanged, only tooling config modified."
}
```

**Behavior**: Transitions `suspended → active`, creates audit record, records dismissal justification on the active `TrustRecertificationRequest`.

**Response 200**: `CertificationResponse`  
**Errors**: 404, 409 (cert is not in `suspended` status)

---

### GET /certifications/{certification_id}/reassessments
List reassessment records for a certification. (FR-014)

**Auth**: Any workspace member

**Response 200**:
```json
{
  "items": [ReassessmentResponse, ...],
  "total": N
}
```

---

### POST /certifications/{certification_id}/reassessments
Record a reassessment verdict. (FR-014, FR-015)

**Auth**: COMPLIANCE_OFFICER or PLATFORM_ADMIN

**Request body**:
```json
{
  "verdict": "pass",
  "notes": "Full re-evaluation on revised model. All criteria met."
}
```

**Behavior**:
- `pass` → transitions `suspended → active` (FR-015)
- `fail` → transitions `active/expiring → suspended` (FR-015)
- `action_required` → no status change, records the verdict

**Response 201**: `ReassessmentResponse`  
**Errors**: 404, 422

---

### GET /recertification-requests
List material-change recertification requests. (distinct from existing `/recertification-triggers`)

**Auth**: COMPLIANCE_OFFICER or PLATFORM_ADMIN

**Query params**: `certification_id=<uuid>` (optional), `status=pending|resolved|dismissed|revoked` (optional)

**Response 200**:
```json
{
  "items": [TrustRecertificationRequestResponse, ...],
  "total": N
}
```

---

### GET /recertification-requests/{request_id}
Get a specific recertification request.

**Auth**: COMPLIANCE_OFFICER or PLATFORM_ADMIN

**Response 200**: `TrustRecertificationRequestResponse`  
**Errors**: 404

---

## Kafka Event Shapes (new event types on `trust.events` topic)

### `trust.contract.breach`
Emitted by `ContractMonitorConsumer` when a contract term is violated.

```json
{
  "event_type": "trust.contract.breach",
  "source": "platform.trust",
  "correlation_context": { "...": "..." },
  "payload": {
    "contract_id": "uuid",
    "target_type": "execution",
    "target_id": "uuid",
    "breached_term": "time_constraint",
    "observed_value": {"elapsed_seconds": 35},
    "threshold_value": {"time_constraint_seconds": 30},
    "enforcement_action": "terminate",
    "enforcement_outcome": "success"
  }
}
```

### `trust.contract.enforcement`
Emitted on enforcement actions; also published to `monitor.alerts` for escalate/terminate actions.

```json
{
  "event_type": "trust.contract.enforcement",
  "source": "platform.trust",
  "payload": {
    "contract_id": "uuid",
    "breach_event_id": "uuid",
    "action": "terminate",
    "target_type": "execution",
    "target_id": "uuid",
    "outcome": "success"
  }
}
```

### `trust.certification.expiring`
Emitted by `SurveillanceService` when a certification transitions to `expiring`.

```json
{
  "event_type": "trust.certification.expiring",
  "source": "platform.trust",
  "payload": {
    "certification_id": "uuid",
    "agent_id": "finance-ops:kyc-verifier",
    "expires_at": "2026-04-26T00:00:00Z",
    "days_until_expiry": 7
  }
}
```

### `trust.certification.suspended`
Emitted when a certification is suspended due to material change.

```json
{
  "event_type": "trust.certification.suspended",
  "source": "platform.trust",
  "payload": {
    "certification_id": "uuid",
    "agent_id": "finance-ops:kyc-verifier",
    "trigger_type": "revision",
    "trigger_reference": "rev_uuid",
    "grace_period_deadline": "2026-05-03T00:00:00Z"
  }
}
```
