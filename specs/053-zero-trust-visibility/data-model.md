# Data Model: Zero-Trust Default Visibility

**Feature**: 053-zero-trust-visibility | **Date**: 2026-04-18

## No schema changes

All required database structures are already in place. This feature adds no new tables, columns, or Alembic migrations.

| Existing structure | Location | Role in this feature |
|---|---|---|
| `registry_agent_profiles.visibility_agents` | `registry/models/agent.py` | Per-agent FQN glob patterns for agent visibility |
| `registry_agent_profiles.visibility_tools` | `registry/models/agent.py` | Per-agent FQN glob patterns for tool visibility |
| `workspaces_visibility_grants` table | `workspaces/models.py:173–177` | Workspace-level agent/tool FQN patterns supplementing per-agent config |
| `resolve_effective_visibility(agent_id, workspace_id)` | `registry/service.py:554–568` | Computes union of per-agent + workspace patterns per request |

---

## Changed entities

### VisibilitySettings (NEW — config only, no DB)

**Location**: `apps/control-plane/src/platform/common/config.py`

```python
class VisibilitySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VISIBILITY_", extra="ignore")

    zero_trust_enabled: bool = False
```

Added to `PlatformSettings`:
```python
visibility: VisibilitySettings = Field(default_factory=VisibilitySettings)
```

**Env var**: `VISIBILITY_ZERO_TRUST_ENABLED` (string `"true"` / `"false"`, pydantic-settings coerces)  
**Default**: `False` — flag-off by default for existing deployments (Brownfield Rule 8, FR-001)  
**Validation rule**: None beyond bool coercion.  
**State transitions**: Runtime toggle — process re-reads on startup from env. SC-008 ≤5s propagation is met by process restart or config-map rollout; no in-flight requests are affected mid-stream.

---

### ToolGatewayService (MODIFIED — behavior only)

**Location**: `apps/control-plane/src/platform/policies/gateway.py`

New pre-check stage inserted at position 0 in `validate_tool_invocation()`:

| Stage | Condition | Block reason |
|---|---|---|
| **0. Visibility** *(NEW)* | `settings.visibility.zero_trust_enabled AND tool_fqn NOT IN effective_visibility_tools` | `"visibility_denied"` |
| 1. Permission | `permission_ref is None` | `"permission_denied"` |
| 2. Maturity | maturity check fails | `"maturity_level_insufficient"` |
| 3. Purpose | purpose mismatch | `"purpose_mismatch"` |
| 4. Budget | budget exceeded | `"budget_exceeded"` |
| 5. Safety | safety rule blocked | `"safety_rule_blocked"` |

No constructor change needed. `self.registry_service` is already injected (line 22).  
The `_blocked()` method path remains unchanged; only `block_reason` value is new.

---

### InteractionService.add_participant (MODIFIED — signature only)

**Location**: `apps/control-plane/src/platform/interactions/service.py:371–383`

New optional parameter:
```python
async def add_participant(
    self,
    interaction_id: UUID,
    participant: ParticipantAdd,
    workspace_id: UUID,
    requesting_agent_id: UUID | None = None,   # NEW, optional
) -> ParticipantResponse:
```

**Pre-check logic** (when flag ON and `requesting_agent_id` is provided):
1. Call `self.registry_service.resolve_effective_visibility(requesting_agent_id, workspace_id)` → `EffectiveVisibility`
2. Check if `participant.identity` (agent FQN string) matches any pattern in `visibility_agents`
3. If no match → raise `InteractionNotFoundError(interaction_id)` (same shape as "not found"; target identity not disclosed)

**Validation rule**: FQN glob matching via existing `fqn_matches()`. Wildcard `*` or `*:*` patterns treated as "visible to all" (flagged in audit, per spec Edge Cases).

---

### SearchService._get_visibility_patterns (MODIFIED — logic only)

**Location**: `apps/control-plane/src/platform/marketplace/search_service.py:432–449`

New signature:
```python
async def _get_visibility_patterns(
    self,
    workspace_id: UUID,
    requesting_agent_id: UUID | None = None,
) -> list[str]:
```

**New logic**:
```
if flag ON and requesting_agent_id is not None:
    effective = await registry_service.resolve_effective_visibility(
        requesting_agent_id, workspace_id
    )
    return effective.visibility_agents or []   # [] = deny-all under zero-trust
else:
    # existing behavior: workspace grants or ["*"]
    ...
```

Change in default fallback: `[]` when flag ON + agent provided but no patterns match, vs existing `["*"]` (see-all).

---

### RegistryService.list_agents + _assert_agent_visible (MODIFIED — flag gate)

**Location**: `apps/control-plane/src/platform/registry/service.py:344–393, 662–677`

`list_agents()` change:
```python
# Before
if requesting_agent_id is not None:
    visibility_filter = await self.resolve_effective_visibility(...)

# After
if requesting_agent_id is not None and self.settings.visibility.zero_trust_enabled:
    visibility_filter = await self.resolve_effective_visibility(...)
```

`_assert_agent_visible()` change:
```python
# Before: always raises AgentNotFoundError if not visible
# After: only raises when zero_trust_enabled; also emits audit event
```

---

## Audit event (NEW value only)

**Block reason value**: `"visibility_denied"`  
**Emitted by**: tool gateway `_blocked()` and registry service `_assert_agent_visible()`  
**Topic**: existing `policy.gate.blocked` for tool gateway; existing `registry.events` or `policy.events` for registry denials  
**New fields**: none (existing envelope fields `agent_id`, `target`, `workspace_id`, `block_reason` already sufficient for SC-005 operator attribution)
