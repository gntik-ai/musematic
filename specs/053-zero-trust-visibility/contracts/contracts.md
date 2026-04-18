# Interface Contracts: Zero-Trust Default Visibility

**Feature**: 053-zero-trust-visibility | **Date**: 2026-04-18

---

## Contract 1: Feature flag environment variable

**Interface**: Process environment / Kubernetes ConfigMap  
**Variable**: `VISIBILITY_ZERO_TRUST_ENABLED`  
**Type**: boolean string (`"true"` / `"false"`)  
**Default**: `"false"` (flag OFF)  
**Read by**: `PlatformSettings.visibility.zero_trust_enabled` on startup  
**Propagation**: Process restart or config-map reload; takes effect on subsequent requests within seconds (SC-008)

**Invariants**:
- `"false"` (or absent): all agent/tool visibility behavior is identical to pre-feature codebase; no new denials.
- `"true"`: zero-trust filter applied at registry query time, tool gateway, delegation, and marketplace surfaces.

---

## Contract 2: Tool gateway — visibility stage

**Interface**: `ToolGatewayService.validate_tool_invocation()` internal contract  
**Location**: `apps/control-plane/src/platform/policies/gateway.py`

**Pre-condition**: `settings.visibility.zero_trust_enabled is True`

**Call**:
```
validate_tool_invocation(
    agent_id: UUID,
    agent_fqn: str,
    tool_fqn: str,
    declared_purpose: str,
    execution_id: UUID | None,
    workspace_id: UUID,
    session: Any,
) -> GateResult
```

**New behavior when flag ON**:

| Condition | Result |
|---|---|
| `tool_fqn` matches a pattern in `effective_visibility.visibility_tools` | proceed to permission check (existing behavior) |
| `tool_fqn` matches no pattern (including when patterns = []) | `GateResult(allowed=False, block_reason="visibility_denied")` |
| flag OFF (regardless of patterns) | skip check; proceed to permission check |

**Error shape**: `GateResult(allowed=False, block_reason="visibility_denied")`. Callers receive the same HTTP status as `"permission_denied"` — tool existence is not disclosed (SC-006).

**Audit**: `_blocked()` publishes to `policy.gate.blocked` Kafka topic with `block_reason="visibility_denied"` (FR-012, SC-005).

---

## Contract 3: Registry service — flag-gated visibility filter

**Interface**: `RegistryService.list_agents()` and `RegistryService._assert_agent_visible()`  
**Location**: `apps/control-plane/src/platform/registry/service.py`

**`list_agents()` contract**:

| `requesting_agent_id` | flag ON | flag OFF |
|---|---|---|
| provided | visibility filter applied (union of per-agent + workspace grants) | no filter; return all workspace-scoped agents |
| None | no filter | no filter |

**`_assert_agent_visible()` contract** (used by `get_agent_by_id()`, `get_agent_by_fqn()`):

| Condition | flag ON | flag OFF |
|---|---|---|
| agent is outside caller's effective visibility | raise `AgentNotFoundError` + emit audit | pass through (no new denial) |
| agent is within effective visibility | pass through | pass through |

**Error shape**: `AgentNotFoundError` raised in both the genuine not-found and the visibility-denied cases — identical HTTP 404 shapes (FR-005, SC-006).

---

## Contract 4: Interaction service — delegation visibility check

**Interface**: `InteractionService.add_participant()`  
**Location**: `apps/control-plane/src/platform/interactions/service.py:371`

**New optional parameter**: `requesting_agent_id: UUID | None = None`

**Contract**:

| Condition | flag ON | flag OFF |
|---|---|---|
| `requesting_agent_id` provided AND `participant.identity` not in effective `visibility_agents` | raise `InteractionNotFoundError(interaction_id)` | no check; proceed |
| `requesting_agent_id` not provided | no check; proceed | no check; proceed |
| `participant.identity` in effective `visibility_agents` | proceed | proceed |

**Error shape**: `InteractionNotFoundError` — same HTTP 404 shape as "interaction not found". Target agent identity is not disclosed (FR-007, SC-006).

**Backward compatibility**: All existing callers that omit `requesting_agent_id` are unaffected (default `None`).

---

## Contract 5: Marketplace — effective visibility patterns

**Interface**: `SearchService._get_visibility_patterns()` internal contract  
**Location**: `apps/control-plane/src/platform/marketplace/search_service.py:432`

**New signature**: `async def _get_visibility_patterns(self, workspace_id: UUID, requesting_agent_id: UUID | None = None) -> list[str]`

**Return value semantics**:

| Condition | Return value | Meaning |
|---|---|---|
| flag OFF (any caller) | `["*"]` or workspace grant patterns (existing behavior) | see all / see workspace-granted |
| flag ON + no `requesting_agent_id` | `["*"]` | platform-internal call; no agent perspective |
| flag ON + `requesting_agent_id` + non-empty effective patterns | union list of FQN patterns | see matched agents only |
| flag ON + `requesting_agent_id` + empty effective patterns | `[]` | see nothing (zero-trust default) |

**Downstream**: `_is_visible(fqn, patterns)` with an empty `patterns` list returns `False` for all FQNs — correctly produces empty search/recommend results.

---

## Contract 6: Block reason values

**Context**: `GateResult.block_reason` field in tool gateway responses; audit event `block_reason` field.

| Value | Meaning | New in this feature |
|---|---|---|
| `"permission_denied"` | no policy permission for tool | No |
| `"maturity_level_insufficient"` | tool maturity below policy minimum | No |
| `"purpose_mismatch"` | declared purpose not allowed | No |
| `"budget_exceeded"` | execution budget exhausted | No |
| `"safety_rule_blocked"` | safety rule matched | No |
| `"visibility_denied"` | tool/agent FQN outside effective visibility | **YES** |

The `"visibility_denied"` value provides the distinguishable audit code for SC-005.
