# Service Interfaces: AI-Assisted Agent Composition

Documents in-process service calls between bounded contexts. All methods are async.

---

## Interfaces Composition CONSUMES

### RegistryServiceInterface (from feature 021)

```python
# Existing methods used for validation:
async def get_agent_revision(
    agent_fqn: str, revision_id: UUID
) -> AgentRevisionSummary | None: ...

# NEW methods required (to be added in feature 021 or a coordination task):
async def get_available_tools(workspace_id: UUID) -> list[ToolSummary]: ...
    # Returns: [{tool_id, name, capability_description, tool_type, is_accessible}]
    # Used by: blueprint validation — tools check

async def get_available_models(workspace_id: UUID) -> list[ModelSummary]: ...
    # Returns: [{model_id, identifier, provider, tier, is_accessible}]
    # Used by: blueprint validation — model check
    # Also used for: including available models as context in LLM prompt
```

**Fallback behaviour**: If `get_available_tools` or `get_available_models` is not yet implemented, `BlueprintValidator` returns `"validation_unavailable"` status for those checks rather than blocking blueprint creation.

---

### PolicyServiceInterface (from feature 028)

```python
# Used by: blueprint validation — policy compatibility check
async def evaluate_conformance(
    agent_fqn: str, revision_id: UUID, workspace_id: UUID
) -> ConformanceResult: ...
    # For blueprint validation, agent_fqn is a draft FQN and revision_id is None;
    # the service interface must accept None revision_id for pre-creation checks.
    # Returns: {passed: bool, violations: [{policy_id, rule_id, description}]}
```

---

### ConnectorServiceInterface (from feature 025)

```python
# Used by: blueprint validation — connector status check
async def check_connector_status(
    connector_name: str, workspace_id: UUID
) -> ConnectorStatusResult: ...
    # Returns: {configured: bool, operational: bool, connector_type: str}

async def list_workspace_connectors(workspace_id: UUID) -> list[ConnectorSummary]: ...
    # Returns: [{connector_id, connector_name, connector_type, status}]
    # Used by: LLM prompt context (available connectors for suggestions)
```

---

## Interfaces Composition EXPOSES

### CompositionServiceInterface (consumed by other bounded contexts)

```python
class CompositionServiceInterface(Protocol):

    async def get_latest_agent_blueprint(
        self, request_id: UUID, workspace_id: UUID
    ) -> AgentBlueprintSummary | None: ...
        # Returns the latest version of the agent blueprint for a request.
        # Used by: registry (021) when operator chooses to instantiate blueprint as agent.

    async def get_latest_fleet_blueprint(
        self, request_id: UUID, workspace_id: UUID
    ) -> FleetBlueprintSummary | None: ...
        # Returns the latest version of the fleet blueprint for a request.
        # Used by: fleet management (033) when operator chooses to instantiate as fleet.
```

---

## LLM Prompt Context (Platform Knowledge Sent to LLM)

The `LLMCompositionClient` constructs a structured system prompt that includes:

```json
{
  "platform_context": {
    "available_tools": [{"name": "...", "capability": "...", "type": "..."}],
    "available_models": [{"identifier": "...", "provider": "...", "tier": "..."}],
    "available_connectors": [{"name": "...", "type": "...", "status": "configured"}],
    "active_policies": [{"name": "...", "description": "...", "scope": "..."}],
    "context_engineering_strategies": ["standard", "compressed", "hierarchical"]
  }
}
```

**Security note**: This context MUST NEVER include API keys, credentials, connection strings, secrets, or any sensitive configuration. Only human-readable names and capability descriptions. Constitution Principle XI.

---

## Kafka Events

### Topic: `composition.events`
Key: `composition_request_id`
Producers: `composition/events.py`
Consumers: analytics (020, lifecycle KPIs), notification service (operator alerts)

Event types:
- `blueprint_generated` — agent or fleet blueprint successfully created
- `blueprint_validated` — validation completed (includes `overall_valid`)
- `blueprint_overridden` — human override applied to a blueprint version
- `blueprint_finalized` — operator marked blueprint as finalized (pre-instantiation)
- `generation_failed` — LLM call failed or timed out
