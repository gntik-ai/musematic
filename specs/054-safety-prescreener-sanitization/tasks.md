# Tasks: Safety Pre-Screener and Secret Sanitization

**Input**: Design documents from `specs/054-safety-prescreener-sanitization/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/contracts.md ✅, quickstart.md ✅

**Organization**: 6 modified Python files + 1 new Alembic migration across 5 user stories + 1 foundational phase. No new database tables, no new Kafka topics, no new bounded contexts.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no blocking dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)

---

## Phase 1: Foundational (GuardrailLayer Enum — Blocks US1 + US4)

**Purpose**: Add `pre_screener` to the `GuardrailLayer` Python enum and the PostgreSQL enum type. This is the prerequisite for US1 and US4 (pipeline wiring must be able to store `TrustBlockedActionRecord.layer = GuardrailLayer.pre_screener`).

- [X] T001 Add `pre_screener = "pre_screener"` as first value in `GuardrailLayer(StrEnum)` in `apps/control-plane/src/platform/trust/models.py` (before `input_sanitization`; additive, Brownfield Rule 6)
- [X] T002 [P] Create Alembic migration `apps/control-plane/migrations/versions/042_prescreener_guardrail_layer.py` with `revision = "042_prescreener_guardrail_layer"`, `down_revision = "041_fqn_backfill"`, `upgrade()` calls `op.execute("ALTER TYPE guardraillayer ADD VALUE IF NOT EXISTS 'pre_screener'")`, `downgrade()` is no-op

**Checkpoint**: `GuardrailLayer.pre_screener` importable in Python. Migration applies without error. `TrustBlockedActionRecord` can be created with `layer=GuardrailLayer.pre_screener`.

---

## Phase 2: User Story 2 — Pre-screener latency SLO (Priority: P1)

**Goal**: `SafetyPreScreenerService.screen()` measures its own elapsed time and exposes the active rule-set version; `PreScreenResponse` carries both as optional fields. US1's pipeline wiring reads these fields, so this phase is a prerequisite for Phase 3.

**Independent Test**: Call `prescreener.screen("content", "input")` → assert `latency_ms` is a non-negative float and `rule_set_version` matches the loaded rule set's version. Call with no active rule set → `rule_set_version is None`.

- [X] T003 [US2] Add `latency_ms: float | None = None` and `rule_set_version: str | None = None` to `PreScreenResponse` in `apps/control-plane/src/platform/trust/schemas.py` (additive fields with None defaults; Brownfield Rule 7)
- [X] T004 [US2] In `apps/control-plane/src/platform/trust/prescreener.py`: (a) add `self._active_version: str | None = None` instance attribute in `__init__`; (b) set `self._active_version = str(rule_set.version)` in `load_active_rules()` after the rule set is loaded (set to `None` when no rule set exists); (c) wrap the pattern loop in `screen()` with `time.perf_counter()` before and after; (d) return `PreScreenResponse(..., latency_ms=elapsed_ms, rule_set_version=self._active_version)`
- [X] T005 [P] [US2] Write unit tests in `apps/control-plane/tests/unit/trust/test_prescreener_latency.py`: (a) `screen()` returns `latency_ms` as non-negative float; (b) after `load_active_rules()` with mocked rule set version "7", `screen()` returns `rule_set_version == "7"`; (c) with no active rule set (`_compiled_patterns = {}`, `_active_version = None`), `screen()` returns `rule_set_version is None`; (d) `latency_ms` present even when no patterns match (blocked=False path)

**Checkpoint**: `screen()` always returns timing data. US2 user story independently verifiable.

---

## Phase 3: User Story 1 — Pipeline wiring as stage 0 (Priority: P1) 🎯 MVP

**Goal**: `GuardrailPipelineService` runs `SafetyPreScreenerService.screen()` as stage 0 (before `input_sanitization`). Blocks short-circuit the rest of the pipeline. When no `pre_screener` is injected the pipeline behaves identically to today.

**Prerequisites**: Phase 1 (enum), Phase 2 (PreScreenResponse fields)

**Independent Test**: Instantiate pipeline with a `SafetyPreScreenerService` whose `_compiled_patterns` includes `re.compile(r"ignore previous instructions")`. Call `evaluate_full_pipeline` with matching payload → `allowed=False`, `layer=GuardrailLayer.pre_screener`. Instantiate pipeline with `pre_screener=None` → same payload not blocked by pre-screener.

- [X] T006 [US1] In `apps/control-plane/src/platform/trust/guardrail_pipeline.py`: add `pre_screener: Any | None = None` to `GuardrailPipelineService.__init__()` parameter list (after `policy_engine`); add `self.pre_screener = pre_screener` assignment
- [X] T007 [US1] In `apps/control-plane/src/platform/trust/guardrail_pipeline.py`: (a) change `LAYER_ORDER` to `[GuardrailLayer.pre_screener, GuardrailLayer.input_sanitization, ...]` (prepend; all 6 existing values follow); (b) add `elif layer == GuardrailLayer.pre_screener: basis = await self._evaluate_pre_screener(payload, context)` as the first branch in `evaluate_layer()` (before the `if layer == GuardrailLayer.input_sanitization:` branch)
- [X] T008 [US1] In `apps/control-plane/src/platform/trust/guardrail_pipeline.py`: (a) add module-level helper `def _emit_prescreener_latency(latency_ms: float, version: str | None) -> None` that calls `opentelemetry.metrics.get_meter(__name__).create_histogram("prescreener.latency_ms").record(latency_ms, {"rule_set_version": version or "none"})`; (b) add private method `async def _evaluate_pre_screener(self, payload: dict[str, Any], context: dict[str, Any]) -> str | None` that: returns `None` if `self.pre_screener is None`; serializes payload with `json.dumps`; awaits `self.pre_screener.screen(content, context.get("context_type", "input"))`; calls `_emit_prescreener_latency(response.latency_ms, response.rule_set_version)` if `response.latency_ms is not None`; if `response.blocked`: sets `context["policy_basis_detail"] = json.dumps({"matched_rule": response.matched_rule, "rule_set_version": response.rule_set_version})`; returns `f"pre_screener:{response.matched_rule}"`; otherwise returns `None`
- [X] T009 [P] [US1] Write unit tests in `apps/control-plane/tests/unit/trust/test_guardrail_prescreener_wire.py`: (a) matching input → `allowed=False`, `layer=GuardrailLayer.pre_screener`; (b) non-matching input → `allowed=True`, pipeline continues to `input_sanitization` layer; (c) `pre_screener=None` → no `pre_screener` block regardless of content (FR-004, SC-006); (d) empty rule set (`_compiled_patterns = {}`) → pre-screener is no-op

**Checkpoint**: Default-deny pipeline wiring done. MVP deployable with `pre_screener=None` (zero behavior change) or injected for enforcement.

---

## Phase 4: User Story 3 — Tool output sanitization endpoint (Priority: P1)

**Goal**: `POST /api/v1/policies/gate/sanitize-output` provides a structural API surface guaranteeing that any caller (execution engine, connectors, test harness) can sanitize tool output before forwarding to LLM context.

**Independent Test**: POST with bearer token in `output` → response contains `[REDACTED:bearer_token]`; POST with clean output → response `output` is byte-identical to input, `redaction_count == 0`.

- [X] T010 [US3] Add `SanitizeToolOutputRequest(BaseModel)` to `apps/control-plane/src/platform/policies/schemas.py` with fields: `output: str`, `agent_id: UUID`, `agent_fqn: str = Field(min_length=1, max_length=512)`, `tool_fqn: str = Field(min_length=1, max_length=512)`, `execution_id: UUID | None = None`, `workspace_id: UUID | None = None`
- [X] T011 [US3] In `apps/control-plane/src/platform/policies/router.py`: add `from platform.policies.dependencies import get_tool_gateway_service` import; add `@router.post("/gate/sanitize-output", response_model=SanitizationResult)` endpoint `async def sanitize_tool_output_endpoint(payload: SanitizeToolOutputRequest, session: AsyncSession = Depends(get_db), gateway: ToolGatewayService = Depends(get_tool_gateway_service)) -> SanitizationResult` that delegates to `gateway.sanitize_tool_output(payload.output, agent_id=payload.agent_id, agent_fqn=payload.agent_fqn, tool_fqn=payload.tool_fqn, execution_id=payload.execution_id, workspace_id=payload.workspace_id, session=session)`
- [X] T012 [P] [US3] Write unit tests in `apps/control-plane/tests/unit/policies/test_sanitize_output_endpoint.py`: (a) bearer token in output → `[REDACTED:bearer_token]` present; (b) connection string in error payload → `[REDACTED:connection_string]` present; (c) JWT in JSON string → `[REDACTED:jwt_token]` present; (d) clean output → byte-identical response, `redaction_count == 0`, no `PolicyBlockedActionRecord`

**Checkpoint**: Structural sanitization guarantee delivered. US3 independently verifiable.

---

## Phase 5: User Story 4 — Pre-screener audit record (Priority: P2)

**Goal**: Verify that pre-screener blocks produce `TrustBlockedActionRecord` with `layer=GuardrailLayer.pre_screener`, `policy_basis_detail` carrying `matched_rule` + `rule_set_version`, and Kafka publish with `layer="pre_screener"`. The implementation is co-located with US1's `_evaluate_pre_screener()` (T008); this phase adds the verification tests.

**Prerequisites**: Phase 1 (enum), Phase 3 (US1 — pipeline wiring with policy_basis_detail injection)

**Independent Test**: Call `evaluate_full_pipeline` with matching input while capturing `repository.create_blocked_action_record` calls → assert exactly one call with `layer=GuardrailLayer.pre_screener` and parseable `policy_basis_detail`.

- [X] T013 [P] [US4] Write unit tests in `apps/control-plane/tests/unit/trust/test_prescreener_audit.py`: (a) pre-screener block → `TrustBlockedActionRecord.layer == GuardrailLayer.pre_screener`, `policy_basis` starts with `"pre_screener:"`, `policy_basis_detail` is valid JSON with `"matched_rule"` and `"rule_set_version"` keys; (b) pre-screener pass → `record_blocked_action` NOT called for `pre_screener` layer; (c) `publish_guardrail_blocked` called with `layer="pre_screener"` on block (Kafka audit event, SC-005)

**Checkpoint**: Operator visibility gap closed. Pre-screener blocks appear on `GET /trust/blocked-actions?layer=pre_screener`.

---

## Phase 6: User Story 5 — YAML rule-set administration (Priority: P2)

**Goal**: `POST /api/v1/trust/prescreener/rule-sets` accepts `Content-Type: application/yaml` bodies, parses them with `yaml.safe_load()`, and stores the same result as the equivalent JSON body. JSON behavior is unchanged.

**Independent Test**: POST with YAML body and `Content-Type: application/yaml` → 201 + correct `rule_count`. POST with malformed YAML → 422 with `YAML_PARSE_ERROR`. POST with JSON → unchanged 201 behavior.

- [X] T014 [US5] In `apps/control-plane/src/platform/trust/router.py`: add `import yaml` at the top (PyYAML is already a dependency); change `create_prescreener_rule_set` signature from `(payload: PreScreenerRuleSetCreate, ...)` to `(request: Request, ...)`; add `from fastapi import Request` import; in the handler body: extract `content_type = request.headers.get("content-type", "application/json").split(";")[0].strip()`; read `raw = await request.body()`; if `content_type == "application/yaml"`: wrap `yaml.safe_load(raw.decode("utf-8"))` in `try/except yaml.YAMLError` raising `ValidationError("YAML_PARSE_ERROR", str(exc))`; else: parse as JSON; validate with `PreScreenerRuleSetCreate.model_validate(data)`; delegate to `prescreener_service.create_rule_set(payload)`
- [X] T015 [P] [US5] Write unit tests in `apps/control-plane/tests/unit/trust/test_prescreener_yaml.py`: (a) YAML body with `Content-Type: application/yaml` → 201 + correct `name` and `rule_count`; (b) JSON body → 201 unchanged behavior; (c) malformed YAML → 422 response with `YAML_PARSE_ERROR` code; (d) YAML and JSON representations of the same rule set produce equal `rule_count` (SC-007 round-trip equivalence)

**Checkpoint**: YAML administration format delivered. US5 independently verifiable.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Foundational)**: No dependencies — start immediately
- **Phase 2 (US2)**: Requires Phase 1 complete (migration must exist before testing enum in blocked records)
- **Phase 3 (US1)**: Requires Phase 1 (enum) AND Phase 2 (PreScreenResponse fields) complete
- **Phase 4 (US3)**: Requires Phase 1 only (or can start immediately — policies/ files are independent)
- **Phase 5 (US4)**: Requires Phase 3 complete (tests verify US1 audit behavior)
- **Phase 6 (US5)**: No dependencies — independent of all phases (different file: `trust/router.py`)

### User Story Dependencies

- **US2 (P1)**: After Phase 1 — `schemas.py` + `prescreener.py` changes
- **US1 (P1)**: After Phase 1 + US2 — `guardrail_pipeline.py` changes
- **US3 (P1)**: After Phase 1 only (or parallel) — `policies/schemas.py` + `policies/router.py`
- **US4 (P2)**: After US1 — test-only phase; implementation is inside US1's `_evaluate_pre_screener()`
- **US5 (P2)**: No dependency — `trust/router.py` is untouched by all other phases

### Within Each Phase

- Implementation tasks before test tasks (TDD not mandated)
- Same-file tasks are sequential: T006 → T007 → T008 (all in `guardrail_pipeline.py`)
- Test tasks marked [P] can begin as soon as the files they mock are stable

### Parallel Opportunities

```bash
# After T001 + T002 (Foundational), these can run in parallel:
Task: T003+T004      # US2: trust/schemas.py + trust/prescreener.py
Task: T010+T011      # US3: policies/schemas.py + policies/router.py (different files)
Task: T014           # US5: trust/router.py (independent)

# Within US2, T005 is parallel to US1 implementation start:
Task: T005           # US2 tests (can write while T006 starts)
Task: T006+T007+T008 # US1 pipeline wiring (same file, sequential)

# After US1 completes:
Task: T009           # US1 tests [P]
Task: T013           # US4 tests [P]
```

---

## Parallel Example: US1 + US3 + US5 simultaneous (after Foundational)

```bash
# After T001 + T002 complete:

# Developer A (US2 → US1):
T003 → T004 → T006 → T007 → T008 → T005 (US2 test)
                               T009 (US1 test, parallel with T013)

# Developer B (US3):
T010 → T011 → T012

# Developer C (US5):
T014 → T015
```

---

## Implementation Strategy

### MVP First (US1 + US2 — Pipeline Wiring with Latency)

1. Complete Phase 1: T001, T002 (enum + migration)
2. Complete Phase 2 (US2): T003 → T004 → T005 (latency measurement)
3. Complete Phase 3 (US1): T006 → T007 → T008 → T009 (pipeline wiring)
4. **STOP and VALIDATE**: Send matching input through pipeline → blocked at `pre_screener` layer. Inject `pre_screener=None` → no regression.
5. Deploy with `pre_screener=None` (DI wiring not yet active) — zero behavior change.

### Incremental Delivery

1. Phase 1 → Phase 2 (US2) → Phase 3 (US1): Pre-screener live in pipeline, SLO measured
2. Phase 4 (US3): Tool output sanitization endpoint active
3. Phase 5 (US4): Audit record tests confirm operator visibility
4. Phase 6 (US5): YAML administration format live

---

## Notes

- T002 [P]: modifies `migrations/versions/042_...py` — independent of T001's Python enum (different file)
- T005, T009, T012, T013, T015 are all [P] — each is a new test file, no same-file conflicts
- T014 is the only modification to `trust/router.py`; all other router changes are in `policies/router.py`
- Deploying all 15 tasks with `pre_screener=None` in DI wiring is a zero-impact deploy
- Activation: wire `SafetyPreScreenerService` into `GuardrailPipelineService` constructor in `dependencies.py`
- No Alembic column additions, no new Kafka topics required
