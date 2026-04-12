# Quickstart: Policy and Governance Engine

**Branch**: `028-policy-governance-engine` | **Date**: 2026-04-12 | **Phase**: 1

Test scenarios for verification. Uses pytest + pytest-asyncio with a live PostgreSQL test database (no mocks for DB, MSW not applicable for backend).

---

## Prerequisites

- PostgreSQL test database with migration 028 applied
- Redis available for bundle cache tests
- Test agent profile in `registry_agent_profiles` at maturity level 1
- Auth token with `platform_admin` role

---

## Scenario 1 — Policy Create and Version History

**Goal**: Verify policy creation produces version 1 and updates produce immutable new versions.

**Steps**:
```python
# Create policy
POST /api/v1/policies
body = {"name": "Test Policy", "scope_type": "workspace", "workspace_id": "...", "rules": {...}}
# → 201, id=policy_id, current_version.version_number=1

# Update rules
PATCH /api/v1/policies/{policy_id}
body = {"rules": {"enforcement_rules": [{"id": "r1", "action": "deny", "tool_patterns": ["*"]}]}}
# → 200, current_version.version_number=2

# Retrieve version history
GET /api/v1/policies/{policy_id}/versions
# → 200, items has 2 entries, version 1 has original rules, version 2 has new rules
# → version 1 is immutable: still retrievable at /versions/1
```

**Expected**: Version 1 still accessible after version 2 created. Rules of version 1 unchanged.

---

## Scenario 2 — Policy Composition Deterministic Precedence

**Goal**: Verify agent → workspace → global precedence with deny-wins at same level.

**Setup**:
- Global policy: allows all tools (`*`)
- Workspace policy: denies `external-api`
- Agent-specific policy: allows `external-api` (agent override)

**Steps**:
```python
# Attach global policy
POST /api/v1/policies/{global_policy_id}/attach
body = {"target_type": "global"}

# Attach workspace policy
POST /api/v1/policies/{ws_policy_id}/attach
body = {"target_type": "workspace", "target_id": "workspace-uuid"}

# Attach agent policy
POST /api/v1/policies/{agent_policy_id}/attach
body = {"target_type": "agent_revision", "target_id": "agent-revision-uuid"}

# Resolve effective policy
GET /api/v1/policies/effective/{agent_id}?workspace_id=workspace-uuid
```

**Expected**:
- `external-api` is in the allowed list (agent-level allow overrides workspace-level deny)
- Each resolved rule has provenance showing its policy_id and scope_level
- `conflicts` list contains the workspace deny vs. agent allow conflict with `resolution: "more_specific_scope_wins"`

---

## Scenario 3 — Tool Gateway: Allow Path

**Goal**: Verify permitted tool invocation emits gate.allowed and does NOT create BlockedActionRecord.

**Steps**:
```python
# Configure agent with policy allowing "calculator"
# Call gateway service directly in integration test:
result = await tool_gateway_service.validate_tool_invocation(
    agent_id=agent_id,
    agent_fqn="test-ns:test-agent",
    tool_fqn="calculator",
    declared_purpose="data-analysis",
    execution_id=uuid4(),
    workspace_id=workspace_id,
    session=session,
)
assert result.allowed is True
assert result.block_reason is None
```

**Kafka check**: `policy.gate.allowed` NOT emitted (opt-in not set on rule by default).

**DB check**: `SELECT count(*) FROM policy_blocked_action_records WHERE agent_id = :id` returns 0.

---

## Scenario 4 — Tool Gateway: Block Path + BlockedActionRecord

**Goal**: Verify blocked tool creates record with full context.

**Steps**:
```python
result = await tool_gateway_service.validate_tool_invocation(
    agent_id=agent_id,
    agent_fqn="test-ns:test-agent",
    tool_fqn="external-api:payment-gateway",
    declared_purpose="data-analysis",
    execution_id=uuid4(),
    workspace_id=workspace_id,
    session=session,
)
assert result.allowed is False
assert result.block_reason == "permission_denied"
assert result.policy_rule_ref is not None
```

**DB check**: `policy_blocked_action_records` has 1 row with:
- `enforcement_component = "tool_gateway"`
- `action_type = "tool_invocation"`
- `target = "external-api:payment-gateway"`
- `block_reason = "permission_denied"`
- `policy_rule_ref.rule_id` matches the deny rule

**Kafka check**: `policy.gate.blocked` event emitted with `agent_id` as key.

---

## Scenario 5 — Tool Gateway: Policy Resolution Failure → Deny All

**Goal**: Verify that when bundle cannot be resolved (e.g., DB down during test), gateway defaults to deny.

**Steps**:
```python
# Force bundle cache miss AND DB error (mock session to raise SQLAlchemyError)
result = await tool_gateway_service.validate_tool_invocation(
    agent_id=agent_id, ...
    session=broken_session,  # raises on any query
)
assert result.allowed is False
assert result.block_reason == "policy_resolution_failure"
```

---

## Scenario 6 — Governance Compiler: Bundle and Shard

**Goal**: Verify compiler produces correct bundle and task-scoped shards.

**Steps**:
```python
compiler = GovernanceCompiler()
bundle = compiler.compile_bundle(
    policy_versions=[global_version, workspace_version, agent_version],
    agent_id=agent_id,
    workspace_id=workspace_id,
)
assert "calculator" in bundle.allowed_tool_patterns
assert "external-api" not in bundle.allowed_tool_patterns
assert len(bundle.manifest.conflicts) == 1  # workspace deny vs agent allow

# Task-scoped shard
shard = bundle.get_shard("tool_invocation")
assert all(
    "tool_invocation" in r.get("applicable_step_types", [])
    for r in shard.allowed_tool_patterns  # shard contains only tool-relevant rules
)
```

---

## Scenario 7 — Governance Compiler: Validation Rejects Invalid Input

**Goal**: Verify compiler raises error for invalid policies before producing any bundle.

**Steps**:
```python
invalid_version = build_policy_version(rules={
    "budget_limits": {"max_tool_invocations_per_execution": -1}
})
with pytest.raises(PolicyCompilationError) as exc_info:
    compiler.compile_bundle([invalid_version], agent_id, workspace_id)
assert "Budget limits cannot be negative" in str(exc_info.value)
# No partial bundle produced
```

---

## Scenario 8 — Memory Write Gate: Namespace Authorization

**Goal**: Verify allowed and blocked writes based on namespace policy.

**Steps**:
```python
# Policy allows namespace "finance", denies all others
result_allowed = await memory_write_gate.validate_memory_write(
    agent_id=agent_id, agent_fqn="...", target_namespace="finance",
    content_hash="...", workspace_id=workspace_id, session=session,
)
assert result_allowed.allowed is True

result_blocked = await memory_write_gate.validate_memory_write(
    agent_id=agent_id, agent_fqn="...", target_namespace="hr",
    content_hash="...", workspace_id=workspace_id, session=session,
)
assert result_blocked.allowed is False
assert result_blocked.block_reason == "namespace_unauthorized"
```

---

## Scenario 9 — Memory Write Gate: Rate Limiting

**Goal**: Verify rate limit enforcement via Redis sliding window.

**Steps**:
```python
# Policy: max_memory_writes_per_minute = 3
for i in range(3):
    result = await memory_write_gate.validate_memory_write(...)
    assert result.allowed is True

# 4th write in same minute window
result = await memory_write_gate.validate_memory_write(...)
assert result.allowed is False
assert result.block_reason == "rate_limit_exceeded"

# BlockedActionRecord created with enforcement_component = "memory_write_gate"
```

---

## Scenario 10 — Maturity Gate: Level Insufficient

**Goal**: Verify level-0 agent cannot access level-1 capabilities.

**Setup**: Agent at maturity level 0. Policy includes `maturity_gate_rules: [{min_maturity_level: 1, capability_patterns: ["external_api_calls"]}]`.

**Steps**:
```python
result = await tool_gateway_service.validate_tool_invocation(
    agent_id=level_0_agent_id,
    tool_fqn="external-api:some-service",  # tagged as external_api_calls capability
    ...
)
assert result.allowed is False
assert result.block_reason == "maturity_level_insufficient"
assert "required_level" in result.policy_rule_ref
assert result.policy_rule_ref["required_level"] == 1
```

---

## Scenario 11 — Purpose-Bound Authorization Mismatch

**Goal**: Verify purpose mismatch blocks invocation.

**Setup**: Agent declared purpose "customer-support". Tool "trading-algorithm" has compatible_purposes = ["financial-trading"].

**Steps**:
```python
result = await tool_gateway_service.validate_tool_invocation(
    agent_id=agent_id,
    tool_fqn="trading-algorithm",
    declared_purpose="customer-support",
    ...
)
assert result.allowed is False
assert result.block_reason == "purpose_mismatch"
```

---

## Scenario 12 — Visibility Filter: Zero-Trust Default

**Goal**: Verify agent with no visibility config gets empty registry results.

**Steps**:
```python
# Agent with no visibility configuration
visibility_filter = await policy_service.get_visibility_filter(
    agent_id=no_visibility_agent_id
)
# Registry repository applies filter
agents = await registry_repo.list_agents_with_visibility(
    session=session,
    visibility_filter=visibility_filter
)
assert len(agents) == 0  # Zero-trust default: see nothing
```

---

## Scenario 13 — Visibility Filter: FQN Pattern Matching

**Goal**: Verify wildcard FQN patterns work correctly.

**Setup**: Agent with `visibility_agents = ["finance-ops:*"]`. 3 finance-ops agents, 2 marketing agents registered.

**Steps**:
```python
agents = await registry_repo.list_agents_with_visibility(
    session=session,
    visibility_filter=VisibilityFilter(agent_patterns=["finance-ops:*"], tool_patterns=[])
)
assert len(agents) == 3
assert all(a.fqn.startswith("finance-ops:") for a in agents)
# marketing agents NOT returned
```

---

## Scenario 14 — Tool Output Sanitizer

**Goal**: Verify known secret patterns are redacted, clean output passes through.

**Steps**:
```python
sanitizer = OutputSanitizer()

# Test bearer token
result = sanitizer.sanitize(
    "Response: Bearer eyJhbGciOiJSUzI1NiJ9abc123",
    agent_id=agent_id, tool_fqn="api-caller", ...
)
assert "[REDACTED:bearer_token]" in result.output
assert "eyJhbGciOiJSUzI1NiJ9abc123" not in result.output
assert result.redaction_count == 1

# Test clean output
result_clean = sanitizer.sanitize(
    "{'result': 42, 'status': 'ok'}",
    agent_id=agent_id, tool_fqn="calculator", ...
)
assert result_clean.output == "{'result': 42, 'status': 'ok'}"
assert result_clean.redaction_count == 0
```

**DB check**: `policy_blocked_action_records` has 1 row for the bearer token redaction with `enforcement_component = "sanitizer"`.

---

## Scenario 15 — Bundle Cache (Redis)

**Goal**: Verify compiled bundle is cached and served from cache on second call.

**Steps**:
```python
# First call: compiles bundle + writes to Redis
bundle1 = await policy_service.get_enforcement_bundle(agent_id, workspace_id, session)
fingerprint = bundle1.manifest.fingerprint

# Verify Redis key exists
cached = redis_client.get(f"policy:bundle:{fingerprint}")
assert cached is not None

# Second call: should come from cache (no DB queries for policy_versions)
with count_db_queries() as counter:
    bundle2 = await policy_service.get_enforcement_bundle(agent_id, workspace_id, session)
assert counter.policy_versions_queries == 0  # No DB queries for versions
assert bundle2.manifest.fingerprint == fingerprint
```
