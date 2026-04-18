# Implementation Plan: Zero-Trust Default Visibility

**Branch**: `053-zero-trust-visibility` | **Date**: 2026-04-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/053-zero-trust-visibility/spec.md`

## Summary

The core data structures (per-agent `visibility_agents`/`visibility_tools` columns, `workspaces_visibility_grants` table, `resolve_effective_visibility()` service method, and FQN predicate in the registry repository) are already shipped. What is missing is the enforcement layer: a feature flag that gates the existing visibility logic, a visibility stage in the tool gateway, a delegation check in the interaction service, and a fix to the marketplace's visibility source to union per-agent + workspace grants and default to deny-all rather than see-all. Total scope: 5 modified Python files + 4 test modules. No schema migrations; no new Kafka topics; no new endpoints.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2 / pydantic-settings (feature flag), SQLAlchemy 2.x async, aiokafka 0.11+ (audit events), pytest + pytest-asyncio 8.x  
**Storage**: PostgreSQL (no new DDL; existing `workspaces_visibility_grants` + `registry_agent_profiles`); no ClickHouse or OpenSearch changes  
**Testing**: pytest + pytest-asyncio 8.x; min 95% coverage on modified files  
**Target Platform**: Linux / Kubernetes (same as control plane)  
**Project Type**: Brownfield modification to existing Python web service  
**Performance Goals**: Flag read is a single in-memory field access after startup (no per-request DB hits for the flag itself); visibility resolution reuses existing indexed DB queries  
**Constraints**: Brownfield Rules 1–8; no file rewrites; additive + backward-compatible only  
**Scale/Scope**: 5 modified Python source files, 4 new test modules, 0 new DB migrations

## Constitution Check

**GATE: Must pass before implementation**

| Principle | Status | Notes |
|-----------|--------|-------|
| Modular monolith (Principle I) | ✅ PASS | Changes confined to `common/`, `registry/`, `policies/`, `interactions/`, `marketplace/` — no new services |
| No cross-boundary DB access (Principle IV) | ✅ PASS | `ToolGatewayService` calls `registry_service.resolve_effective_visibility()` — already injected; no direct cross-context DB access |
| Policy is machine-enforced (Principle VI) | ✅ PASS | Visibility is enforced programmatically at gateway + query time; no human-gate path |
| Zero-trust default visibility (Principle IX) | ✅ PASS | This IS the implementation of Principle IX |
| Secrets not in LLM context (Principle XI) | ✅ PASS | N/A |
| Generic S3 storage (Principle XVI) | ✅ PASS | N/A |
| Brownfield Rule 1 (no rewrites) | ✅ PASS | Only line-level additions/modifications to 5 existing files |
| Brownfield Rule 2 (Alembic only) | ✅ PASS | No DDL changes; all required columns/tables exist |
| Brownfield Rule 3 (preserve tests) | ✅ PASS | 4 new test modules; no existing tests modified |
| Brownfield Rule 4 (use existing patterns) | ✅ PASS | Feature flag follows `VisibilitySettings(BaseSettings)` convention; gateway block follows existing `_blocked()` pattern; service pre-check follows existing guard patterns |
| Brownfield Rule 7 (backward-compatible APIs) | ✅ PASS | New params are optional with `None` defaults; flag OFF = identical to pre-feature behavior |
| Brownfield Rule 8 (feature flags) | ✅ PASS | `VISIBILITY_ZERO_TRUST_ENABLED=false` by default |

**Post-design re-check**: No violations.

## Project Structure

### Documentation (this feature)

```text
specs/053-zero-trust-visibility/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── contracts.md     # Phase 1 output
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code — What Changes

```text
apps/control-plane/
├── src/platform/
│   ├── common/
│   │   └── config.py                        MODIFIED — add VisibilitySettings(BaseSettings)
│   │                                                    with zero_trust_enabled: bool = False;
│   │                                                    add visibility: VisibilitySettings
│   │                                                    to PlatformSettings
│   ├── registry/
│   │   └── service.py                       MODIFIED — gate list_agents() visibility_filter
│   │                                                    on settings.visibility.zero_trust_enabled;
│   │                                                    gate _assert_agent_visible() on same;
│   │                                                    add audit emit in _assert_agent_visible()
│   ├── policies/
│   │   └── gateway.py                       MODIFIED — add visibility pre-check as stage 0 in
│   │                                                    validate_tool_invocation(); uses
│   │                                                    self.registry_service (already injected);
│   │                                                    block_reason="visibility_denied"
│   ├── interactions/
│   │   └── service.py                       MODIFIED — add optional requesting_agent_id: UUID | None
│   │                                                    param to add_participant(); add visibility
│   │                                                    pre-check when flag ON
│   └── marketplace/
│       └── search_service.py                MODIFIED — _get_visibility_patterns() accepts
│                                                        requesting_agent_id; unions per-agent +
│                                                        workspace patterns; defaults to [] not
│                                                        ["*"] when flag ON + agent provided
│
└── tests/
    ├── unit/
    │   ├── test_visibility_config.py         NEW — VisibilitySettings validation, flag read,
    │   │                                            env var coercion, default=False
    │   ├── registry/
    │   │   └── test_visibility_flag.py       NEW — list_agents flag ON/OFF, pattern grants,
    │   │                                            workspace grant union, _assert_agent_visible
    │   ├── policies/
    │   │   └── test_tool_gateway_visibility.py NEW — visibility stage 0: visible/invisible tool,
    │   │                                             flag OFF no-op, audit block_reason value
    │   ├── interactions/
    │   │   └── test_delegation_visibility.py  NEW — add_participant flag ON/OFF, visible/invisible
    │   │                                            target, legacy caller (no requesting_agent_id)
    │   └── marketplace/
    │       └── test_marketplace_visibility.py NEW — _get_visibility_patterns flag ON/OFF,
    │                                                 per-agent + workspace union, empty=deny-all,
    │                                                 total reflects post-filter count
```

**Structure Decision**: Strictly additive changes to 5 existing source files. No new bounded contexts, no new DB tables, no new Kafka topics, no new API endpoints.

## Implementation Phases

### Phase 1: Feature Flag

**Goal**: Introduce the `FEATURE_ZERO_TRUST_VISIBILITY` toggle as a `VisibilitySettings` class; default OFF.

**Files**:
- `apps/control-plane/src/platform/common/config.py` — add `VisibilitySettings(BaseSettings)` with `model_config = SettingsConfigDict(env_prefix="VISIBILITY_", extra="ignore")` and `zero_trust_enabled: bool = False`; add `visibility: VisibilitySettings = Field(default_factory=VisibilitySettings)` to `PlatformSettings`

**Independent test**: Unit tests — `VisibilitySettings()` with no env vars gives `zero_trust_enabled=False`; `VISIBILITY_ZERO_TRUST_ENABLED=true` gives `True`; invalid value raises `ValidationError`; `PlatformSettings` includes `visibility` sub-settings.

---

### Phase 2: Registry service — flag gate

**Goal**: Ensure the existing visibility filter and `_assert_agent_visible()` guard are only applied when the flag is ON, so flag-OFF behavior is strictly identical to the pre-feature codebase.

**Files**:
- `apps/control-plane/src/platform/registry/service.py` — in `list_agents()` (lines 344–393): change `if requesting_agent_id is not None:` to `if requesting_agent_id is not None and self.settings.visibility.zero_trust_enabled:`; apply same guard to the count path. In `_assert_agent_visible()` (lines 662–677): guard the `AgentNotFoundError` raise on the flag; add an audit event publish (using existing event infrastructure) with `block_reason="visibility_denied"` when flag ON and visibility is denied.

**Independent test**: Unit tests — flag OFF + requesting_agent_id → all agents returned (existing behavior); flag ON + requesting_agent_id + no patterns → empty list; flag ON + requesting_agent_id + `["finance-ops:*"]` → only matching FQNs; `_assert_agent_visible()` flag ON returns `AgentNotFoundError` for invisible agent; flag OFF returns agent normally.

---

### Phase 3: Tool gateway — visibility stage 0

**Goal**: Deny tool invocations whose `tool_fqn` does not match the calling agent's effective `visibility_tools` patterns when the flag is ON.

**Files**:
- `apps/control-plane/src/platform/policies/gateway.py` — in `validate_tool_invocation()` (lines 29–133): before the permission check, add:
  ```python
  if self.settings.visibility.zero_trust_enabled and self.registry_service is not None:
      effective = await self.registry_service.resolve_effective_visibility(agent_id, workspace_id)
      if not any(
          fnmatch(tool_fqn, p) or tool_fqn == p
          for p in (effective.visibility_tools or [])
      ):
          return await self._blocked(
              ..., block_reason="visibility_denied", ...
          )
  ```
  The `settings` object needs to be injected in `__init__`; add `settings: PlatformSettings | None = None` parameter (backward-compatible default `None`; when `None` the check is skipped).

**Independent test**: Unit tests — flag ON + matching tool pattern → proceeds to permission check; flag ON + non-matching tool → `GateResult(allowed=False, block_reason="visibility_denied")`; flag OFF → both tools proceed; `settings=None` (legacy init) → check skipped; audit event carries `block_reason="visibility_denied"`.

---

### Phase 4: Interaction service — delegation visibility check

**Goal**: Reject agent-to-agent delegation (`add_participant()`) when the target agent's FQN is outside the requesting agent's effective visibility.

**Files**:
- `apps/control-plane/src/platform/interactions/service.py` — in `add_participant()` (lines 371–383): add optional `requesting_agent_id: UUID | None = None` parameter; when flag ON and requesting_agent_id is provided, call `registry_service.resolve_effective_visibility()` and check `participant.identity` against `visibility_agents` patterns. If no match: raise `InteractionNotFoundError(interaction_id)`.

  The `InteractionService.__init__` must accept `registry_service: Any | None = None` (or the settings + registry_service can be injected similarly to the gateway). Add `registry_service` as an optional injected dependency.

**Independent test**: Unit tests — flag ON + requesting_agent_id + non-visible target → `InteractionNotFoundError`; flag ON + requesting_agent_id + visible target → participant created; flag OFF → no check, participant created regardless; `requesting_agent_id=None` (legacy) → no check.

---

### Phase 5: Marketplace — effective visibility source

**Goal**: Fix `SearchService._get_visibility_patterns()` to union per-agent + workspace visibility patterns and default to deny-all (`[]`) when flag is ON and requesting agent has no grants.

**Files**:
- `apps/control-plane/src/platform/marketplace/search_service.py` — extend `_get_visibility_patterns(workspace_id, requesting_agent_id=None)`:
  - When flag ON and `requesting_agent_id` is not None: call `registry_service.resolve_effective_visibility(requesting_agent_id, workspace_id)` and return `effective.visibility_agents or []`
  - When flag OFF or no agent_id: keep existing `["*"]` fallback behavior
  - Thread `requesting_agent_id` through `search()`, `get_listing()`, and `_get_recommendations_for_agent()` call sites

**Independent test**: Unit tests — flag ON + agent_id + non-empty patterns → union patterns returned; flag ON + agent_id + empty patterns → `[]` returned (deny-all); flag OFF → `["*"]` fallback (existing behavior preserved); `_is_visible(fqn, [])` → `False` for all FQNs; `total` in paginated result matches filtered count.

---

## API Endpoints Used / Modified

| Endpoint | Status | Change |
|----------|--------|--------|
| `GET /api/v1/workspaces/{id}/agents` (and all registry list/search routes) | Existing | Behavior changes when flag ON + requesting_agent_id header present |
| `GET /api/v1/workspaces/{id}/agents/{agent_id}` | Existing | 404 shape unified for invisible vs. not-found when flag ON |
| Tool gateway (internal service call) | Existing | New visibility stage 0 when flag ON |
| `POST /api/v1/interactions/{id}/participants` | Existing | Visibility pre-check added when flag ON + requesting agent header present |
| `GET /api/v1/marketplace/search`, `/recommend`, `/trending` | Existing | Effective visibility source corrected; deny-all default under flag ON |
| `PUT /api/v1/workspaces/{id}/visibility` | Existing | No change — already correct |

## Dependencies

- **Feature 021 (Agent Registry)**: Provides `visibility_agents`/`visibility_tools` columns. Already deployed.
- **Feature 018 (Workspaces)**: Provides `workspaces_visibility_grants` table and `PUT /workspaces/{id}/visibility`. Already deployed.
- **Feature 028 (Policy Engine)**: Provides `ToolGatewayService` and `_blocked()` audit path. Extended by Phase 3.
- **Feature 051 (FQN Namespace)**: Provides `fqn_matches()` / `compile_fqn_pattern()` used by `resolve_effective_visibility()`.

## Complexity Tracking

No constitution violations. No complexity justification table needed.

| Category | Count |
|---|---|
| Modified Python source files | 5 (`config.py`, `registry/service.py`, `policies/gateway.py`, `interactions/service.py`, `marketplace/search_service.py`) |
| New files | 0 |
| New test modules | 4 |
| New bounded contexts | 0 |
| New database tables or columns | 0 |
| New Alembic migrations | 0 |
| New Kafka topics | 0 |
| New API endpoints | 0 |

User input refinements discovered during research:

1. Steps 1, 4, 5, 6 of the user's plan are no-ops — the structures are already in place.
2. Step 9 (Redis cache) is out of scope — the existing indexed table lookup is sufficient.
3. Marketplace needed a deeper fix than a simple flag gate: the pattern source was workspace-only and the default was `["*"]`; both required correction.
