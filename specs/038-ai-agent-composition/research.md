# Research: AI-Assisted Agent Composition

**Feature**: 038-ai-agent-composition  
**Date**: 2026-04-15  
**Branch**: `038-ai-agent-composition`

---

## Decision 1: LLM Call Pattern

**Decision**: Use direct `httpx.AsyncClient()` POST calls to a configurable LLM API endpoint, wrapped in a thin `LLMCompositionClient` class with structured prompt templates.

**Rationale**: This matches the existing platform pattern used in `evaluation/scorers/llm_judge.py` and `evaluation/scorers/semantic.py`. No unified LLM wrapper exists in the platform — each bounded context owns its own httpx call logic. The Reasoning Engine (Go gRPC service) handles hot-path reasoning budget tracking, not blueprint generation. Blueprint generation is a one-shot structured output call — not a tree-of-thought or self-correction problem — so using the Go reasoning engine would be over-engineering.

**Alternatives considered**:
- Call the Go Reasoning Engine via gRPC: Rejected — the reasoning engine is optimized for iterative tree-of-thought with budget tracking, not one-shot structured output generation. Adding composition prompts to the reasoning engine would violate bounded context separation.
- Build a shared LLM client wrapper: Rejected — no such wrapper exists yet and the Constitution does not require one; adding it would be a speculative abstraction. The composition service creates its own thin `LLMCompositionClient` following the existing httpx pattern.

**Implementation note**: The LLM API URL and model identifier are injected via `PlatformSettings.COMPOSITION_LLM_API_URL` and `COMPOSITION_LLM_MODEL`. Constitution Principle XI (Secrets Never in LLM Context) requires that connector credentials, API keys, and secrets are never included in the generation prompt — only connector type names and tool capability descriptions.

---

## Decision 2: Bounded Context Placement

**Decision**: New `composition/` bounded context under `apps/control-plane/src/platform/composition/`. No sub-module for each generator type beyond a thin `llm/` sub-module for the client and `validation/` for constraint checks.

**Rationale**: Following the existing bounded context layout (modular monolith, Principle I). The composition feature is small enough (5 DB tables, ~8 source files) that over-sub-packaging would add indirection without value. The `llm/` sub-module isolates the httpx call logic from business logic.

**Structure**:
```text
apps/control-plane/src/platform/composition/
├── __init__.py
├── models.py           # 5 SQLAlchemy models
├── schemas.py          # Pydantic v2 request/response schemas
├── service.py          # CompositionService (main orchestration)
├── repository.py       # Async DB access (insert-only audit entries)
├── router.py           # FastAPI router (/api/v1/compositions)
├── events.py           # Kafka publisher (composition.events)
├── exceptions.py       # CompositionError hierarchy
├── dependencies.py     # FastAPI DI: get_composition_service
├── llm/
│   ├── __init__.py
│   └── client.py       # LLMCompositionClient: prompt → structured response
├── generators/
│   ├── __init__.py
│   ├── agent.py        # AgentBlueprintGenerator
│   └── fleet.py        # FleetBlueprintGenerator
└── validation/
    ├── __init__.py
    └── validator.py    # BlueprintValidator: 5 constraint checks
```

---

## Decision 3: Blueprint Data Storage

**Decision**: PostgreSQL JSONB for blueprint payloads. `composition_requests` + `agent_blueprints` + `fleet_blueprints` + `composition_validations` + `composition_audit_entries` (5 tables). No ClickHouse or vector store required for this feature.

**Rationale**: Blueprint data is relational (one request → one blueprint → many validations → many audit entries). Blueprints are structured JSON objects but are not time-series analytics (no ClickHouse needed) and are not semantically searched by vector (no Qdrant needed). JSONB gives schema flexibility for the blueprint payload while keeping standard ACID semantics for the state machine. Constitution Principle III is satisfied.

**Audit trail design**: `composition_audit_entries` is insert-only (no UPDATE/DELETE), analogous to `agentops_governance_events` from feature 037. This satisfies the append-only requirement from the spec.

---

## Decision 4: Blueprint Validation Approach

**Decision**: Call existing service interfaces for constraint checking. Five checks run concurrently via `asyncio.gather`:
1. Tool availability: `RegistryServiceInterface.get_available_tools(workspace_id)` — verify tool names in blueprint exist
2. Model availability: `RegistryServiceInterface.get_available_models(workspace_id)` — verify model identifier is accessible
3. Connector status: `ConnectorServiceInterface.check_connector_status(connector_id, workspace_id)` — verify connectors are configured and operational
4. Policy compatibility: `PolicyServiceInterface.evaluate_conformance(agent_fqn_draft, workspace_id)` — check no policy conflicts
5. Fleet cycle detection: Pure in-process graph analysis (no external call) — DFS cycle detection on delegation/escalation graph

**Rationale**: No cross-boundary DB access (Principle IV). All resource data accessed through service interfaces. Cycle detection is a pure algorithm requiring no external state.

**Note**: `RegistryServiceInterface` needs two new methods (`get_available_tools`, `get_available_models`) that may not yet be defined. These are documented as new additions in `contracts/service-interfaces.md`. If not yet implemented, the validation module falls back to returning "validation_unavailable" status for those checks.

---

## Decision 5: Kafka Topic

**Decision**: Add `composition.events` topic to the Kafka topics registry. Key: `composition_request_id`. Consumers: audit service (if separate), analytics.

**Rationale**: Constitution Principle III + platform pattern. All bounded contexts publish lifecycle events to Kafka. The composition events topic allows downstream consumers (analytics, audit dashboards) to track blueprint creation and validation without direct DB access.

---

## Decision 6: Structured Output Format

**Decision**: Use a prompt engineering approach with JSON mode (structured output) where the LLM API supports it. The prompt includes the workspace's available tools, models, connectors, and policies as structured context. The response is parsed as a typed Pydantic schema.

**Rationale**: Structured output (JSON mode) from the LLM produces reliably parseable responses without brittle string parsing. The `LLMCompositionClient` sends a system prompt with workspace context and a user prompt with the description, requesting a JSON response conforming to the `AgentBlueprintRaw` or `FleetBlueprintRaw` schema.

**Constitution XI compliance**: The workspace context sent to the LLM contains only resource names and capability descriptions — never API keys, credentials, database connection strings, or any secrets.

---

## Decision 7: Response Confidence and Low-Confidence Flagging

**Decision**: Include a `confidence_score` (0.0–1.0) and `follow_up_questions` list in the blueprint response. Score < 0.5 sets `low_confidence: true`. Confidence is estimated by the LLM based on description specificity and is included in the structured JSON response.

**Rationale**: The spec requires (FR-023) that vague descriptions are flagged. Rather than a binary flag based on description length, trusting the LLM's self-assessed confidence gives more nuanced results. The LLM is prompted to self-assess confidence and generate follow-up questions when uncertain.

---

## New Service Interface Methods Needed

`RegistryServiceInterface` (feature 021) needs two new methods for validation:
```python
async def get_available_tools(workspace_id: UUID) -> list[ToolSummary]: ...
    # Returns: [{tool_id, name, capability_description, tool_type}]

async def get_available_models(workspace_id: UUID) -> list[ModelSummary]: ...
    # Returns: [{model_id, identifier, provider, tier}]
```

These may need to be coordinated with the feature 021 team. If not available, validation falls back to a "partial_validation" status.
