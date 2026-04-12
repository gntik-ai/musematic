# API Contracts: Trust, Certification, and Guardrails

**Feature**: 032-trust-certification-guardrails  
**Date**: 2026-04-12

All endpoints use JWT Bearer auth. Base prefix: `/api/v1`. All responses use `application/json`.

---

## Certification Endpoints

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `POST` | `/trust/certifications` | Create a new certification (pending state) | platform_admin, trust_certifier |
| `GET` | `/trust/certifications/{id}` | Get certification by ID | any authenticated |
| `GET` | `/trust/agents/{agent_id}/certifications` | List all certifications for an agent | any authenticated |
| `POST` | `/trust/certifications/{id}/activate` | Transition pending → active | trust_certifier |
| `POST` | `/trust/certifications/{id}/revoke` | Transition active → revoked | trust_certifier |
| `POST` | `/trust/certifications/{id}/evidence` | Add evidence reference to certification | trust_certifier |

**Create certification request**:
```json
{
  "agent_id": "uuid",
  "agent_fqn": "finance-ops:kyc-verifier",
  "agent_revision_id": "uuid",
  "expires_at": "2027-04-12T00:00:00Z"
}
```

**Revoke request**:
```json
{
  "reason": "Behavioral regression detected in production"
}
```

**Add evidence request**:
```json
{
  "evidence_type": "test_results",
  "source_ref_type": "test_suite_run",
  "source_ref_id": "uuid",
  "summary": "All 47 test cases passed"
}
```

---

## Trust Tier and Signals

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/trust/agents/{agent_id}/tier` | Get trust tier and score for an agent | any authenticated |
| `GET` | `/trust/agents/{agent_id}/signals` | List trust signals for an agent (paginated) | trust_certifier, platform_admin |

**Trust tier response**:
```json
{
  "agent_id": "uuid",
  "agent_fqn": "finance-ops:kyc-verifier",
  "tier": "certified",
  "trust_score": 0.8740,
  "certification_component": 0.9200,
  "guardrail_component": 0.8500,
  "behavioral_component": 0.7800,
  "last_computed_at": "2026-04-12T10:00:00Z"
}
```

---

## Guardrail Pipeline

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `POST` | `/trust/guardrails/evaluate` | Evaluate a single payload through a specific guardrail layer | service account |
| `GET` | `/trust/guardrails/blocked-actions` | List blocked action records (paginated, filterable by agent/layer) | trust_certifier, platform_admin |
| `GET` | `/trust/guardrails/blocked-actions/{id}` | Get a specific blocked action record | trust_certifier, platform_admin |
| `GET` | `/trust/guardrails/config` | Get guardrail pipeline config for workspace/fleet | workspace member |
| `PUT` | `/trust/guardrails/config` | Create or update guardrail pipeline config | workspace_admin, platform_admin |

**Guardrail evaluate request**:
```json
{
  "agent_id": "uuid",
  "agent_fqn": "finance-ops:kyc-verifier",
  "execution_id": "uuid",
  "interaction_id": "uuid",
  "workspace_id": "uuid",
  "layer": "prompt_injection",
  "payload": {
    "prompt": "Ignore all previous instructions and..."
  }
}
```

**Guardrail evaluate response**:
```json
{
  "allowed": false,
  "layer": "prompt_injection",
  "policy_basis": "policy-uuid",
  "blocked_action_id": "uuid"
}
```

---

## Safety Pre-Screener

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `POST` | `/trust/prescreener/screen` | Screen content before full guardrail pipeline | service account |
| `GET` | `/trust/prescreener/rule-sets` | List pre-screener rule set versions | platform_admin |
| `POST` | `/trust/prescreener/rule-sets` | Upload a new rule set version | platform_admin |
| `POST` | `/trust/prescreener/rule-sets/{id}/activate` | Activate a rule set version | platform_admin |

**Screen request**:
```json
{
  "content": "User input or tool output text here",
  "context_type": "input"
}
```

**Screen response**:
```json
{
  "blocked": true,
  "matched_rule": "jailbreak-pattern-007",
  "passed_to_full_pipeline": false
}
```

---

## Observer-Judge-Enforcer Pipeline

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/trust/oje-configs` | List OJE pipeline configs for workspace/fleet | workspace_admin |
| `POST` | `/trust/oje-configs` | Create OJE pipeline configuration | workspace_admin, platform_admin |
| `GET` | `/trust/oje-configs/{id}` | Get OJE pipeline config by ID | workspace_admin |
| `DELETE` | `/trust/oje-configs/{id}` | Deactivate OJE pipeline config | workspace_admin, platform_admin |

**OJE config create request**:
```json
{
  "workspace_id": "uuid",
  "fleet_id": null,
  "observer_fqns": ["trust-mesh:anomaly-observer"],
  "judge_fqns": ["trust-mesh:policy-judge"],
  "enforcer_fqns": ["trust-mesh:auto-enforcer"],
  "policy_refs": ["policy-uuid-1", "policy-uuid-2"]
}
```

---

## Recertification

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/trust/recertification-triggers` | List triggers for an agent (query param: agent_id) | trust_certifier, platform_admin |
| `GET` | `/trust/recertification-triggers/{id}` | Get trigger by ID | trust_certifier, platform_admin |

---

## Circuit Breaker

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/trust/circuit-breaker/{agent_id}/status` | Get circuit breaker status for an agent | workspace_admin, platform_admin |
| `POST` | `/trust/circuit-breaker/{agent_id}/reset` | Manually reset a tripped circuit breaker | platform_admin |
| `GET` | `/trust/circuit-breaker/configs` | List circuit breaker configs | workspace_admin |
| `POST` | `/trust/circuit-breaker/configs` | Create/update circuit breaker config | workspace_admin, platform_admin |

---

## ATE (Accredited Testing Environments)

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/trust/ate/configs` | List ATE configurations for workspace | workspace member |
| `POST` | `/trust/ate/configs` | Create ATE configuration | workspace_admin, platform_admin |
| `GET` | `/trust/ate/configs/{id}` | Get ATE configuration | workspace member |
| `POST` | `/trust/ate/runs` | Initiate an ATE run for a certification | trust_certifier |
| `GET` | `/trust/ate/runs/{simulation_id}` | Get ATE run status and results | trust_certifier |

---

## Privacy Assessment

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `POST` | `/trust/privacy/assess` | Assess context assembly for privacy compliance | service account |

---

## Kafka Events Produced on `trust.events`

| Event type | Key field | Payload summary |
|---|---|---|
| `certification.created` | `agent_id` | cert_id, agent_fqn, revision_id, status |
| `certification.activated` | `agent_id` | cert_id, agent_fqn, activated_by |
| `certification.revoked` | `agent_id` | cert_id, reason, revoked_by |
| `certification.expired` | `agent_id` | cert_id, expired_at |
| `certification.superseded` | `agent_id` | old_cert_id, new_cert_id |
| `trust_tier.updated` | `agent_id` | agent_fqn, tier, trust_score |
| `guardrail.blocked` | `agent_id` | layer, policy_basis, blocked_action_id, execution_id |
| `circuit_breaker.activated` | `agent_id` | failure_count, threshold, workspace_id |
| `recertification.triggered` | `agent_id` | trigger_type, new_certification_id |
| `prescreener.rule_set.activated` | `—` | version, rule_count |

---

## Kafka Topics Consumed

| Topic | Event type | Handler |
|---|---|---|
| `registry.events` | `agent_revision.published` | RecertificationService (trigger revision_changed) |
| `policy.events` | `policy.updated` | RecertificationService (trigger policy_changed) |
| `workflow.runtime` | `execution.guardrail_failed` | CircuitBreakerService (record failure) |
| `simulation.events` | `simulation.completed` | ATEService (process results, link evidence) |

---

## Internal Service Interfaces

Consumed by other bounded contexts via in-process Python function call (§IV):

```python
# Provided by trust/ for consumption by other bounded contexts:

class TrustServiceInterface:
    """Internal interface for cross-context trust queries."""

    async def get_agent_trust_tier(self, agent_id: str) -> TrustTierSummary: ...
    """Returns tier + trust_score for agent deployment gate checks."""

    async def is_agent_certified(self, agent_id: str, revision_id: str) -> bool: ...
    """Returns True if agent has an active certification for the given revision."""

    async def evaluate_guardrail_pipeline(
        self,
        agent_id: str,
        workspace_id: str,
        layer: str,
        payload: dict,
        context: dict
    ) -> GuardrailResult: ...
    """Synchronous guardrail evaluation — returns allowed=True/False + policy_basis."""
```

Consumed by `trust/` from other bounded contexts:

```python
# PolicyGovernanceEngine from policies/ bounded context:
policy_engine.evaluate_tool_access(agent_id, tool_id, workspace_id) -> PolicyDecision
policy_engine.evaluate_memory_write(agent_id, namespace, workspace_id) -> PolicyDecision
policy_engine.check_privacy_compliance(context_assembly_id, workspace_id) -> PrivacyResult

# RuntimeControlService gRPC client for enforcer quarantine:
runtime_controller.stop_runtime(runtime_id, reason) -> StopResult

# SimulationControlService gRPC client for ATE:
simulation_controller.create_simulation(config) -> SimulationHandle
```
