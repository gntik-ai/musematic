# Service Interfaces: Scientific Discovery Orchestration

Documents in-process service calls between bounded contexts. All methods are async.

---

## Interfaces Discovery CONSUMES

### PolicyServiceInterface (from feature 028)
```python
# Used by: experiment governance validation
async def evaluate_conformance(
    agent_fqn: str, revision_id: UUID | None, workspace_id: UUID
) -> ConformanceResult: ...
    # Returns: {passed: bool, violations: [{policy_id, rule_id, description}]}
```

### SandboxManagerClient (gRPC — services/sandbox-manager, port 50053)
```python
# Used by: experiment execution
# NEW method needed in apps/control-plane/src/platform/common/clients/sandbox_manager.py:
async def execute_code(
    template: str,      # "python3.12"
    code: str,          # Experiment code from plan
    workspace_id: UUID,
    timeout_seconds: int
) -> SandboxExecutionResult: ...
    # Returns: {execution_id, status, stdout, stderr, exit_code, artifacts}
```

### WorkflowServiceInterface (from feature 029)
```python
# Used by: GDE cycle — triggering agent generation, debate, refinement as workflow executions
async def create_execution(
    workflow_definition_id: UUID,
    input_context: dict,
    workspace_id: UUID,
    triggered_by: UUID
) -> ExecutionSummary: ...
    # Used to dispatch hypothesis generation and critique agent workflows
```

---

## Interfaces Discovery EXPOSES

### DiscoveryServiceInterface (consumed by analytics, frontend, workspace tools)
```python
class DiscoveryServiceInterface(Protocol):

    async def get_session_summary(
        self, session_id: UUID, workspace_id: UUID
    ) -> DiscoverySessionSummary | None: ...
        # Returns: {session_id, status, current_cycle, top_hypothesis, leaderboard_top5}

    async def get_top_hypotheses(
        self, session_id: UUID, workspace_id: UUID, limit: int = 5
    ) -> list[HypothesisSummary]: ...
        # Returns top-ranked hypotheses by Elo score
        # Used by: workspace dashboard, recommendation agents
```

---

## Redis Key Patterns

Written by Discovery, read by real-time gateway and other services:

```
leaderboard:{session_id}
  Type: Sorted set
  Members: hypothesis_id
  Scores: Elo score (float, default 1000.0)
  TTL: none (expires when session ends + 24h cleanup)

lock:discovery:elo:{session_id}
  Type: String (lock token)
  TTL: 10s
  Used: protect Elo batch update after tournament round
```

---

## Kafka Events

### Topic: `discovery.events`
Key: `session_id`
Producers: `discovery/events.py`
Consumers:
- ws_hub (real-time cycle progress to frontend WebSocket)
- analytics (020, discovery session KPIs)
- proximity clustering APScheduler trigger (on `cycle_completed` → schedule proximity computation)

Event types: `session_started`, `hypothesis_generated`, `critique_completed`, `tournament_round_completed`, `cycle_completed`, `session_converged`, `session_halted`, `experiment_designed`, `experiment_completed`, `proximity_computed`

### Consumed: `workflow.runtime` topic
Discovery consumes workflow execution completion events to receive hypothesis generation, debate, and refinement results dispatched via the workflow execution engine.
