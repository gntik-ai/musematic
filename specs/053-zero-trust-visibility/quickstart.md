# Quickstart / Test Scenarios: Zero-Trust Default Visibility

**Feature**: 053-zero-trust-visibility | **Date**: 2026-04-18

---

## US1 — Default-deny for a newly registered agent

**Test file**: `tests/unit/policies/test_tool_gateway_visibility.py`, `tests/unit/registry/test_visibility_flag.py`

**Precondition**: `VISIBILITY_ZERO_TRUST_ENABLED=true`; agent `new-agent:alpha` has `visibility_agents=[]`, `visibility_tools=[]`; workspace has no visibility grant.

### Scenario 1-A: Agent list returns empty

```
# Arrange
settings.visibility.zero_trust_enabled = True
requesting_agent_id = <new-agent:alpha UUID>

# Act
result = await registry_service.list_agents(
    workspace_id=ws,
    requesting_agent_id=requesting_agent_id,
)

# Assert
assert result.items == []
assert result.total == 0
```

### Scenario 1-B: Tool invocation blocked (existence not disclosed)

```
# Arrange — same preconditions

# Act
gate = await tool_gateway.validate_tool_invocation(
    agent_id=requesting_agent_id,
    tool_fqn="tools:finance:wire-transfer",
    ...
)

# Assert
assert gate.allowed is False
assert gate.block_reason == "visibility_denied"
```

### Scenario 1-C: Flag OFF — no new denial

```
# Arrange
settings.visibility.zero_trust_enabled = False   # flag off

# Act
result = await registry_service.list_agents(workspace_id=ws, requesting_agent_id=requesting_agent_id)

# Assert — existing behavior, all agents returned
assert result.total > 0
```

---

## US2 — Per-agent FQN pattern grants

**Test file**: `tests/unit/registry/test_visibility_flag.py`

**Precondition**: `VISIBILITY_ZERO_TRUST_ENABLED=true`; agents `finance-ops:kyc-verifier`, `finance-ops:aml-checker`, `hr-ops:onboarding-agent` registered in workspace.

### Scenario 2-A: Pattern restricts to namespace

```
# Arrange
set agent A visibility_agents = ["finance-ops:*"]

# Act
result = await registry_service.list_agents(workspace_id=ws, requesting_agent_id=A_id)

# Assert
fqns = {item.fqn for item in result.items}
assert fqns == {"finance-ops:kyc-verifier", "finance-ops:aml-checker"}
assert "hr-ops:onboarding-agent" not in fqns
```

### Scenario 2-B: Workspace grant supplements per-agent (union)

```
# Arrange
set agent A visibility_agents = []
set workspace grant agent_patterns = ["finance-ops:*"]

# Act
result = await registry_service.list_agents(workspace_id=ws, requesting_agent_id=A_id)

# Assert
assert result.total == 2   # both finance-ops agents
```

### Scenario 2-C: Union of per-agent and workspace grant

```
# Arrange
set agent A visibility_agents = ["hr-ops:*"]
set workspace grant agent_patterns = ["finance-ops:*"]

# Act / Assert
# Both namespaces appear; total = 3
assert result.total == 3
```

---

## US3 — Tool visibility enforced at invocation

**Test file**: `tests/unit/policies/test_tool_gateway_visibility.py`

**Precondition**: `VISIBILITY_ZERO_TRUST_ENABLED=true`; agent has `visibility_tools=["tools:search:*"]`.

### Scenario 3-A: Visible tool proceeds

```
gate = await tool_gateway.validate_tool_invocation(
    agent_id=agent_id,
    tool_fqn="tools:search:web",
    ...
)
assert gate.allowed is True
# block_reason absent (existing 5-stage checks still run)
```

### Scenario 3-B: Invisible tool blocked

```
gate = await tool_gateway.validate_tool_invocation(
    agent_id=agent_id,
    tool_fqn="tools:finance:wire-transfer",
    ...
)
assert gate.allowed is False
assert gate.block_reason == "visibility_denied"
# No information about tool existence in response
```

### Scenario 3-C: Flag OFF — both tools proceed (no regression)

```
settings.visibility.zero_trust_enabled = False
gate_visible = await tool_gateway.validate_tool_invocation(agent_id=agent_id, tool_fqn="tools:search:web", ...)
gate_invisible = await tool_gateway.validate_tool_invocation(agent_id=agent_id, tool_fqn="tools:finance:wire-transfer", ...)
# Both proceed to existing permission check stage
```

---

## US4 — Delegation to invisible peers is blocked

**Test file**: `tests/unit/interactions/test_delegation_visibility.py`

**Precondition**: `VISIBILITY_ZERO_TRUST_ENABLED=true`; agent A has `visibility_agents=[]`; agent B is registered in same workspace.

### Scenario 4-A: Delegation to invisible agent fails (existence not disclosed)

```
from platform.interactions.exceptions import InteractionNotFoundError

with pytest.raises(InteractionNotFoundError):
    await interaction_service.add_participant(
        interaction_id=interaction_id,
        participant=ParticipantAdd(identity="finance-ops:secret-agent", role=ParticipantRole.assignee),
        workspace_id=ws,
        requesting_agent_id=A_id,
    )
```

### Scenario 4-B: Delegation to visible agent succeeds

```
# Arrange: set agent A visibility_agents = ["finance-ops:*"]
result = await interaction_service.add_participant(
    interaction_id=interaction_id,
    participant=ParticipantAdd(identity="finance-ops:aml-checker", role=ParticipantRole.assignee),
    workspace_id=ws,
    requesting_agent_id=A_id,
)
assert result.identity == "finance-ops:aml-checker"
```

### Scenario 4-C: Legacy caller (no requesting_agent_id) unaffected

```
# No requesting_agent_id — backward-compatible
result = await interaction_service.add_participant(
    interaction_id=interaction_id,
    participant=ParticipantAdd(identity="any:agent", role=ParticipantRole.assignee),
    workspace_id=ws,
)
assert result is not None
```

---

## US5 — Backward-compatible rollout

**Test file**: `tests/unit/test_visibility_flag_off.py`

### Scenario 5-A: Existing test suite passes with flag OFF

```
# Run with VISIBILITY_ZERO_TRUST_ENABLED=false (default)
# All existing registry, gateway, interaction, marketplace tests pass
# No new denials; behavior identical to pre-feature codebase
```

### Scenario 5-B: Flag toggle takes effect on next request

```
# Arrange
settings.visibility.zero_trust_enabled = True
# Assert: subsequent list returns empty for agent with no grants

settings.visibility.zero_trust_enabled = False
# Assert: subsequent list returns all agents again
# No redeployment needed; SC-008 verified
```

### Scenario 5-C: Audit distinguishability

```
# Arrange: flag ON, agent A has empty visibility
# Act: attempt tool invocation on invisible tool
gate = await tool_gateway.validate_tool_invocation(...)

# Assert: Kafka publish captured
published_event = captured_kafka_messages[-1]
assert published_event["block_reason"] == "visibility_denied"
# Distinguishable from "permission_denied" for operator rollout audit (SC-005)
```

---

## Marketplace filtering

**Test file**: `tests/unit/marketplace/test_marketplace_visibility.py`

### Scenario M-A: Search returns only visible agents

```
# Arrange: flag ON, agent A visibility_agents = ["finance-ops:*"]
# Act
results = await search_service.search(
    request=SearchRequest(query="compliance"),
    workspace_id=ws,
    requesting_agent_id=A_id,
)
# Assert: only finance-ops FQNs in results; total reflects post-filter count
assert all(item.fqn.startswith("finance-ops:") for item in results.items)
```

### Scenario M-B: total never exceeds enumerable set

```
# The count returned is always the filtered count, never the pre-filter count
assert results.total == len(results.items)   # for single-page result
```

---

## Edge case scenarios

| Edge case | Expected behavior |
|---|---|
| Pattern `*` (wildcard all) | Agent sees all; audit event flagged with `wildcard_patterns=True` |
| Pattern `*:*` | Same as `*` |
| Workspace grant removed mid-session | Next request after grant removal returns empty (falls back to per-agent only) |
| Flag toggled ON mid-deployment | In-flight requests complete under old behavior; new requests see filter |
| Invisible agent in `total` count | Never included; SC-007: 100% of paginated responses exclude invisible entities |
