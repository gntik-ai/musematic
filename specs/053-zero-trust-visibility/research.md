# Research: Zero-Trust Default Visibility

**Feature**: 053-zero-trust-visibility | **Date**: 2026-04-18

## Decision 1: What is already shipped

**Decision**: No schema migrations and no new endpoints are needed for this feature.  
**Rationale**: Codebase inspection confirmed the following are already in place:
- `registry_agent_profiles.visibility_agents` and `visibility_tools` columns with `[]` defaults (`apps/control-plane/src/platform/registry/models/agent.py`, feature 021)
- `workspaces_visibility_grants` table with unique index per workspace (`apps/control-plane/src/platform/workspaces/models.py:173–177`, feature 018)
- `PUT /api/v1/workspaces/{id}/visibility` and `GET /{workspace_id}/visibility` endpoints (`apps/control-plane/src/platform/workspaces/router.py:191–210`, feature 018)
- `resolve_effective_visibility(agent_id, workspace_id)` that unions per-agent patterns + workspace grants (`apps/control-plane/src/platform/registry/service.py:554–568`)
- Registry repository `_visibility_predicate()` applied to list/count queries before pagination (`apps/control-plane/src/platform/registry/repository.py:181–224`)
- `_assert_agent_visible()` that raises `AgentNotFoundError` for invisible agents (`apps/control-plane/src/platform/registry/service.py:662–677`)
- `fqn_matches()` and `compile_fqn_pattern()` FQN glob semantics (registry bounded context)
- Marketplace `SearchService._is_visible()` and `_get_visibility_patterns()` helpers (`apps/control-plane/src/platform/marketplace/search_service.py:432–449, 541+`)

**User input steps already done**: Step 1 (Alembic migration), step 4 (effective visibility union), step 5 (FQN pattern matching), step 6 (PUT endpoint).

---

## Decision 2: Feature flag location

**Decision**: Add a `VisibilitySettings(BaseSettings)` class to `apps/control-plane/src/platform/common/config.py` with `zero_trust_enabled: bool = False` and env prefix `VISIBILITY_`. Add `visibility: VisibilitySettings = Field(default_factory=VisibilitySettings)` to `PlatformSettings`.  
**Rationale**: Every existing bounded context setting follows this pattern (e.g., `WorkspacesSettings`, `RegistrySettings`, `AnalyticsSettings`). Using `pydantic-settings` with an env prefix makes the flag runtime-toggleable by restarting the process or through a config-map change, satisfying FR-014 and SC-008. Using a dedicated class keeps `PlatformSettings` flat and consistent with Brownfield Rule 4.  
**Alternatives considered**:
- Single bool on `PlatformSettings` directly: simpler but breaks the established sub-settings pattern.
- Redis-backed dynamic flag: satisfies near-zero propagation latency but introduces a new dependency on flag infrastructure that is explicitly out of scope per the spec Assumption on feature flag distribution.

---

## Decision 3: Registry service — flag gate

**Decision**: In `registry/service.py`, the `list_agents()` method currently applies `visibility_filter` whenever `requesting_agent_id is not None`. Change this predicate to `requesting_agent_id is not None and settings.visibility.zero_trust_enabled`. Apply the same flag guard in `_assert_agent_visible()`.  
**Rationale**: When the flag is OFF, even if callers pass `requesting_agent_id`, the filter must not be applied (FR-002). The `settings` object is already accessible via the service constructor (`self.settings`).  
**Impact**: Two guarded `if` branches in one file.

---

## Decision 4: Tool gateway — new visibility stage

**Decision**: Add a visibility pre-check as the first stage of `ToolGatewayService.validate_tool_invocation()` in `apps/control-plane/src/platform/policies/gateway.py`. The check:
1. Guards on `self.settings.visibility.zero_trust_enabled`
2. Calls `self.registry_service.resolve_effective_visibility(agent_id, workspace_id)` (the `registry_service` field already exists in `ToolGatewayService.__init__`)
3. If `tool_fqn` matches none of the returned `visibility_tools` patterns, calls `_blocked()` with `block_reason="visibility_denied"`

**Rationale**: The gateway is the single chokepoint for all tool use. Adding the check here satisfies FR-006. The `registry_service` is already injected (line 22 of `gateway.py`), so no constructor changes are needed. `block_reason="visibility_denied"` is a new value that flows through the existing `_blocked()` → `policy.gate.blocked` Kafka audit path, satisfying FR-012 and SC-005.  
**Alternatives considered**:
- Check in the tool router: too late, post-gateway; the gateway is already the enforcement boundary.

---

## Decision 5: Interaction service — delegation check

**Decision**: Add an optional `requesting_agent_id: UUID | None = None` parameter to `InteractionService.add_participant()`. When the flag is ON and `requesting_agent_id` is provided, resolve effective visibility for the requesting agent and check whether `participant.identity` (an agent FQN string) matches any of the `visibility_agents` patterns. If not, raise a `ConversationNotFoundError` (or an equivalent 404-shape error) so presence of the target cannot be inferred.  
**Rationale**: `add_participant()` is the delegation entry point — when agent A adds agent B as a participant, that IS the delegation act. The parameter is optional with default `None`, so all existing callers that do not pass it are unaffected (Brownfield Rule 7). Using the same error class as "not found" (and returning the same HTTP shape) satisfies FR-007 / SC-006.  
**Alternatives considered**:
- Check in the router layer: fragile, any future internal caller would bypass it. Service layer is correct.
- New `delegate_to_agent()` method: adds scope beyond what is asked; `add_participant()` is the existing path.

---

## Decision 6: Marketplace — per-agent patterns and flag-aware default

**Decision**: Modify `SearchService._get_visibility_patterns()` in `apps/control-plane/src/platform/marketplace/search_service.py` to:
1. Accept an optional `requesting_agent_id: UUID | None` parameter.
2. When flag ON and `requesting_agent_id` is provided: call `registry_service.resolve_effective_visibility()` to get the union of per-agent + workspace patterns; return the union (empty list `[]` if no patterns match, **not** `["*"]`).
3. When flag OFF (or `requesting_agent_id` is None): keep the existing `["*"]` fallback.

**Rationale**: The current implementation only fetches workspace-level grant patterns and defaults to `["*"]` when the workspace has no patterns. This means:
- Per-agent patterns are ignored (a correctness gap regardless of the flag).
- An agent with empty per-agent AND empty workspace grant sees everything (wrong under zero-trust).

The `registry_service` must be injected into `SearchService` (it is currently `None`-guarded via duck-typing on `workspaces_service`). Passing `requesting_agent_id` down through `search()`, `recommend()`, and `trending()` calls is the correct change; all these paths already thread a workspace_id.  
**Alternatives considered**:
- Keep workspace-only patterns: leaves per-agent grants silently ignored; violates FR-003.
- Always return `[]` when flag ON and agent ID provided but no patterns: correct and is what the spec says — an agent with no grants sees nothing.

---

## Decision 7: Audit code for visibility denials

**Decision**: Use `block_reason="visibility_denied"` as the new distinct code in:
1. Tool gateway `_blocked()` calls (when visibility check fails).
2. Registry service `_assert_agent_visible()` — add an audit event publish using the existing `policy.events` Kafka topic convention when the flag is ON and a denial occurs.

**Rationale**: FR-012 and SC-005 require 100% of visibility denials to carry a code that operators can distinguish. The tool gateway already routes all denials through `_blocked()` → `policy.gate.blocked` topic. Registry denials currently raise an exception silently; they need a matching audit emit.  
**Impact**: One new `block_reason` string in gateway; one new audit publish call in `_assert_agent_visible()`.

---

## Decision 8: Redis cache for workspace grants

**Decision**: NOT implemented in this feature.  
**Rationale**: The user's plan step 9 proposed caching workspace visibility grants in Redis (`ws:{id}:visibility`, TTL 60s). The `workspaces_visibility_grants` table has a unique index on `workspace_id`, so a single indexed row-fetch per request is already fast. The added cache invalidation complexity is not justified by the data-access pattern. The spec Assumptions confirm this feature relies on the existing infrastructure; no new caching layer is introduced. FR-014 is satisfied by the `pydantic-settings` env-var approach, not Redis.

---

## Decision 9: User input — steps mapping to real scope

| User plan step | Disposition |
|---|---|
| 1. Alembic migration for `visibility_grants` | NOT NEEDED — `workspaces_visibility_grants` table exists |
| 2. Add feature flag to `config.py` | IN SCOPE — `VisibilitySettings` class |
| 3. Registry query service visibility filter | IN SCOPE — flag gate on existing filter in `registry/service.py` |
| 4. Compute effective visibility | NOT NEEDED — `resolve_effective_visibility()` exists |
| 5. FQN pattern matching | NOT NEEDED — `fqn_matches()` exists |
| 6. PUT endpoint for visibility grants | NOT NEEDED — already exists |
| 7. Tool gateway visibility check | IN SCOPE — new first stage in `gateway.py` |
| 8. Interaction service delegation check | IN SCOPE — `add_participant()` pre-check |
| 9. Redis cache | OUT OF SCOPE — see Decision 8 |
| 10. Tests | IN SCOPE — all phases have independent tests |
