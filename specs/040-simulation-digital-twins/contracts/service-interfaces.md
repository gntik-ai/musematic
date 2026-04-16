# Service Interfaces: Simulation and Digital Twins

Documents in-process service calls between bounded contexts. All methods are async.

---

## Interfaces Simulation CONSUMES

### RegistryServiceInterface (from feature 021)
```python
# Used by: digital twin snapshot — agent config capture
async def get_agent_profile(
    agent_fqn: str, workspace_id: UUID
) -> AgentProfileSummary | None: ...
    # Returns: {fqn, namespace, name, latest_revision_id, maturity_level, status}

async def get_agent_revision(
    revision_id: UUID
) -> AgentRevisionDetail: ...
    # Returns: full agent config including model_config, tool_selections,
    #          connector_suggestions, context_profile_id, visibility_config
```

### PolicyServiceInterface (from feature 028)
```python
# Used by: isolation enforcement — translate isolation policy → enforcement bundle
async def evaluate_conformance(
    agent_fqn: str, revision_id: UUID | None, workspace_id: UUID
) -> ConformanceResult: ...

async def register_simulation_policy_bundle(
    simulation_run_id: UUID, rules: list[dict], workspace_id: UUID
) -> str: ...
    # NEW method needed — registers a temporary simulation-scoped policy bundle
    # Returns: bundle_fingerprint (used to deregister on simulation completion)

async def deregister_simulation_policy_bundle(
    bundle_fingerprint: str
) -> None: ...
    # NEW method needed — removes the temporary bundle after simulation ends
```

### SimulationControllerClient (gRPC — services/simulation-controller, port 50055)
```python
# Used by: simulation run coordination
async def create_simulation(
    workspace_id: UUID,
    twin_configs: list[dict],
    scenario_config: dict,
    max_duration_seconds: int
) -> SimulationControllerRunResponse: ...
    # Returns: {controller_run_id, status, provisioning_events}

async def get_simulation(
    controller_run_id: str
) -> SimulationControllerRunResponse: ...
    # Returns: {status, progress_pct, current_step, results_ref}

async def cancel_simulation(
    controller_run_id: str
) -> None: ...

async def get_simulation_artifacts(
    controller_run_id: str
) -> SimulationArtifactList: ...
    # Returns: {artifacts: [{name, bucket, key, size}]}
```

---

## Interfaces Simulation EXPOSES

### SimulationServiceInterface (consumed by evaluation, agentops, frontend)
```python
class SimulationServiceInterface(Protocol):

    async def get_simulation_summary(
        self, run_id: UUID, workspace_id: UUID
    ) -> SimulationRunSummary | None: ...
        # Returns: {run_id, status, name, digital_twin_ids, completed_at, results_summary}
        # Used by: evaluation for test run correlation

    async def get_twin_config(
        self, twin_id: UUID, workspace_id: UUID
    ) -> TwinConfigSnapshot | None: ...
        # Returns: {twin_id, source_agent_fqn, version, config_snapshot}
        # Used by: evaluation for ATE scenario configuration
```

---

## Redis Key Patterns

Written by Simulation, read by WebSocket gateway:

```
sim:status:{run_id}
  Type: String (JSON)
  Value: {status, progress_pct, current_step, last_updated}
  TTL: 24h after simulation completion
  Used: Status polling fallback; primary updates via WebSocket
```

---

## Kafka Events

### Topic: `simulation.events`
Key: `simulation_id`  
Producers: `simulation_controller` (Go satellite) + `simulation/events.py` (this feature)  
Consumers:
- ws_hub (real-time simulation progress → WebSocket)
- analytics (020, simulation run KPIs)
- evaluation (034, simulation run correlation)

Control-plane event types produced by this feature:
`simulation_run_created`, `simulation_run_cancelled`, `twin_created`, `twin_modified`, `prediction_completed`, `comparison_completed`, `isolation_breach_detected`

### Consumed: `simulation.events`
Simulation bounded context consumes this topic to receive:
- `simulation_run_started` — update SimulationRun.status → running
- `simulation_run_completed` — update SimulationRun.status → completed + store results
- `simulation_run_failed` — update SimulationRun.status → failed
- `simulation_run_timeout` — update SimulationRun.status → timeout
