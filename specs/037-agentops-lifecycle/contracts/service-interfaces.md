# Service Interfaces: AgentOps Lifecycle Management

Documents in-process service calls between bounded contexts. All methods are async.

---

## Interfaces AgentOps CONSUMES

### TrustServiceInterface (from feature 032)

```python
# Used by: CI/CD gate (certification + trust tier checks), governance triggers
async def is_agent_certified(agent_fqn: str, revision_id: UUID) -> CertificationStatus: ...
    # Returns: {status: 'active'|'expired'|'pending'|'revoked', expires_at, revision_id}

async def get_agent_trust_tier(agent_fqn: str, workspace_id: UUID) -> TrustTierResult: ...
    # Returns: {tier: 0|1|2|3, score: float, components: {}}

async def get_guardrail_pass_rate(
    agent_fqn: str, workspace_id: UUID, window_days: int
) -> float: ...
    # Returns: pass_rate in [0.0, 1.0] over the given window

async def trigger_recertification(
    agent_fqn: str, revision_id: UUID, trigger_reason: str
) -> None: ...
    # Marks agent pending_recertification and starts grace period
```

### EvalSuiteServiceInterface (from feature 034)

```python
# Used by: CI/CD gate (evaluation pass check), behavioral baseline computation
async def get_latest_agent_score(
    agent_fqn: str, workspace_id: UUID
) -> EvalScoreSummary | None: ...
    # Returns: {aggregate_score, threshold, passed, run_id, completed_at}

async def get_run_results(run_id: UUID) -> EvalRunDetail: ...
    # Returns: full run with per-case verdicts, scorer breakdown

async def submit_to_ate(
    revision_id: UUID, eval_set_id: UUID, workspace_id: UUID
) -> ATESubmission: ...
    # Used by adaptation pipeline to test candidate revisions
```

### PolicyServiceInterface (from feature 028)

```python
# Used by: CI/CD gate (policy conformance check)
async def evaluate_conformance(
    agent_fqn: str, revision_id: UUID, workspace_id: UUID
) -> ConformanceResult: ...
    # Returns: {passed: bool, violations: [{policy_id, rule_id, description}]}
```

### WorkflowServiceInterface (from feature 029)

```python
# Used by: retirement workflow dependency detection
async def find_workflows_using_agent(
    agent_fqn: str, workspace_id: UUID
) -> list[WorkflowDependency]: ...
    # Returns: [{workflow_id, workflow_name, owner_user_id, status}]
```

### RegistryServiceInterface (from feature 021)

```python
# Used by: canary deployment (revision validation), retirement (hide from discovery)
async def get_agent_revision(
    agent_fqn: str, revision_id: UUID
) -> AgentRevisionSummary | None: ...

async def set_marketplace_visibility(
    agent_fqn: str, visible: bool, workspace_id: UUID
) -> None: ...
    # Used by retirement to remove agent from marketplace discovery
```

---

## Interfaces AgentOps EXPOSES

### AgentOpsServiceInterface (consumed by runtime-controller, execution engine)

```python
async def get_active_regression_alerts(
    agent_fqn: str, revision_id: UUID
) -> list[RegressionAlertSummary]: ...
    # Returns alerts with status='active' for this revision

async def get_current_health_score(
    agent_fqn: str, workspace_id: UUID
) -> AgentHealthScoreSummary | None: ...
    # Returns latest health score row, or None if no score yet

async def run_gate_check(
    agent_fqn: str, revision_id: UUID, workspace_id: UUID,
    requested_by: UUID
) -> CiCdGateSummary: ...
    # Runs all 5 gates concurrently, persists CiCdGateResult, returns summary

async def is_agent_retiring(
    agent_fqn: str, workspace_id: UUID
) -> bool: ...
    # Returns True if an active RetirementWorkflow exists for this agent
```

---

## Redis Key Patterns

Canary routing configuration (written by AgentOps, read by runtime controller):

```
canary:{workspace_id}:{agent_fqn}
  Value: JSON {
    "canary_revision_id": "...",
    "production_revision_id": "...",
    "traffic_percentage": 10,
    "observation_window_end": "2026-04-15T12:00:00Z",
    "deployment_id": "..."
  }
  TTL: observation_window_end + 3600s (1 hour buffer for cleanup)
```

Health score scheduling lock (APScheduler distributed lock):
```
lock:agentops:health_scorer:{workspace_id}
  TTL: scoring_interval_minutes * 60s
```

---

## Kafka Events

### Topic: `agentops.events`
Key: `agent_fqn`
Producers: `agentops/events.py`
Consumers: notification service, trust module (recertification triggers), marketplace search (retirement → hide), analytics (lifecycle KPIs)

Event types: same as `GovernanceEvent.event_type` enum in data-model.md
