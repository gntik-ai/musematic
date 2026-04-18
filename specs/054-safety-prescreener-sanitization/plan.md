# Implementation Plan: Safety Pre-Screener and Secret Sanitization

**Branch**: `054-safety-prescreener-sanitization` | **Date**: 2026-04-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/054-safety-prescreener-sanitization/spec.md`

## Summary

The `SafetyPreScreenerService` class, `OutputSanitizer`, versioned rule sets (PostgreSQL + MinIO), hot-reload via Redis/Kafka, and rule-management REST endpoints are all already shipped. What is missing is the enforcement layer: (1) the pre-screener is not wired into `GuardrailPipelineService.LAYER_ORDER`; (2) `screen()` does not measure or emit latency; (3) tool output sanitization has no structural call guarantee; (4) pre-screener blocks produce no `TrustBlockedActionRecord`; (5) the rule-set create endpoint accepts only JSON. Total scope: 6 modified Python files + 1 Alembic migration + 4 new test modules. No new bounded contexts. No new Kafka topics.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+, opentelemetry-sdk 1.27+, PyYAML 6.x (already present), pytest + pytest-asyncio 8.x
**Storage**: PostgreSQL (enum value addition via Alembic migration 042; no new tables or columns); MinIO (existing bucket unchanged)
**Testing**: pytest + pytest-asyncio 8.x; min 95% coverage on modified files
**Target Platform**: Linux / Kubernetes (same as control plane)
**Project Type**: Brownfield modification to existing Python web service
**Performance Goals**: `screen()` p99 < 10 ms at 200 patterns × 10 000 inputs (SC-003); existing pipeline latency unchanged (additive cost ≤ the screen() measurement)
**Constraints**: Brownfield Rules 1–8; no file rewrites; additive + backward-compatible only
**Scale/Scope**: 6 modified Python source files, 1 Alembic migration, 4 new test modules

## Constitution Check

**GATE: Must pass before implementation**

| Principle | Status | Notes |
|-----------|--------|-------|
| Modular monolith (Principle I) | ✅ PASS | Changes confined to `trust/`, `policies/` — no new bounded contexts |
| No cross-boundary DB access (Principle IV) | ✅ PASS | `GuardrailPipelineService` calls `SafetyPreScreenerService` in-process; no direct cross-context DB queries |
| Policy is machine-enforced (Principle VI) | ✅ PASS | Pre-screener enforcement is programmatic at pipeline stage 0 |
| Zero-trust (Principle IX) | ✅ PASS | N/A to this feature |
| Secrets not in LLM context (Principle XI) | ✅ PASS | This feature closes the enforcement gap behind Principle XI (US3 + FR-008) |
| Generic S3 storage (Principle XVI) | ✅ PASS | MinIO/S3 access via existing `AsyncObjectStorageClient`; no new direct MinIO references |
| Brownfield Rule 1 (no rewrites) | ✅ PASS | Only line-level additions/modifications to 6 existing files |
| Brownfield Rule 2 (Alembic only) | ✅ PASS | Migration 042 for the `pre_screener` enum value; no raw DDL |
| Brownfield Rule 3 (preserve tests) | ✅ PASS | 4 new test modules; no existing tests modified |
| Brownfield Rule 4 (use existing patterns) | ✅ PASS | `evaluate_layer` elif chain; `record_blocked_action` reuse; OTel `get_meter` pattern |
| Brownfield Rule 5 (reference existing files) | ✅ PASS | All modified files cited with exact function names in data-model.md |
| Brownfield Rule 6 (additive enum values) | ✅ PASS | `pre_screener` added to existing `GuardrailLayer` enum, never recreated |
| Brownfield Rule 7 (backward-compatible APIs) | ✅ PASS | `pre_screener=None` default; `latency_ms/rule_set_version` default None; existing endpoints unchanged |
| Brownfield Rule 8 (feature flags) | ✅ PASS | Pre-screener is a no-op when `pre_screener=None` (no injection); behavior change occurs only after DI wiring |

**Post-design re-check**: No violations.

## Project Structure

### Documentation (this feature)

```text
specs/054-safety-prescreener-sanitization/
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
│   ├── trust/
│   │   ├── models.py                        MODIFIED — add pre_screener to GuardrailLayer enum
│   │   ├── schemas.py                       MODIFIED — add latency_ms + rule_set_version
│   │   │                                               to PreScreenResponse
│   │   ├── prescreener.py                   MODIFIED — add _active_version attr;
│   │   │                                               measure latency in screen()
│   │   ├── guardrail_pipeline.py            MODIFIED — prepend pre_screener to LAYER_ORDER;
│   │   │                                               inject prescreener in __init__;
│   │   │                                               add _evaluate_pre_screener() method;
│   │   │                                               emit OTel prescreener.latency_ms
│   │   └── router.py                        MODIFIED — YAML content-type for
│   │                                                    POST /prescreener/rule-sets
│   └── policies/
│       ├── schemas.py                       MODIFIED — add SanitizeToolOutputRequest schema
│       └── router.py                        MODIFIED — add POST /gate/sanitize-output endpoint
│
├── migrations/versions/
│   └── 042_prescreener_guardrail_layer.py   NEW — ALTER TYPE guardraillayer ADD VALUE
│                                                   IF NOT EXISTS 'pre_screener'
│
└── tests/
    └── unit/
        ├── trust/
        │   ├── test_guardrail_prescreener_wire.py   NEW — US1 pipeline wiring (4 scenarios)
        │   ├── test_prescreener_latency.py           NEW — US2 latency metric (4 scenarios)
        │   └── test_prescreener_audit.py             NEW — US4 audit record (3 scenarios)
        └── policies/
            ├── test_prescreener_yaml.py              NEW — US5 YAML content-type (4 scenarios)
            └── test_sanitize_output_endpoint.py      NEW — US3 endpoint (4 scenarios)
```

**Structure Decision**: Strictly additive changes to 6 existing source files + 1 new migration + 5 new test modules. No new bounded contexts, no new database tables, no new Kafka topics, no new endpoints beyond the one explicit addition for US3.

## Implementation Phases

### Phase 1: Enum + Migration (blocks all phases)

**Goal**: Add `GuardrailLayer.pre_screener` to both the Python enum and the PostgreSQL enum type. This is the single prerequisite for all other work.

**Files**:
- `apps/control-plane/src/platform/trust/models.py` — prepend `pre_screener = "pre_screener"` to `GuardrailLayer` StrEnum
- `apps/control-plane/migrations/versions/042_prescreener_guardrail_layer.py` — new Alembic migration; `ALTER TYPE guardraillayer ADD VALUE IF NOT EXISTS 'pre_screener'`; `downgrade()` is no-op

**Independent test**: Import `GuardrailLayer.pre_screener`; run `alembic upgrade 042_prescreener_guardrail_layer`; create a `TrustBlockedActionRecord` with `layer=GuardrailLayer.pre_screener` and verify it persists.

---

### Phase 2: Latency measurement in screen() (US2 — P1)

**Goal**: `PreScreenResponse` carries `latency_ms` and `rule_set_version`; `SafetyPreScreenerService` tracks the active version.

**Files**:
- `apps/control-plane/src/platform/trust/schemas.py` — add `latency_ms: float | None = None` and `rule_set_version: str | None = None` to `PreScreenResponse`
- `apps/control-plane/src/platform/trust/prescreener.py` — add `self._active_version: str | None = None`; set from `rule_set.version` in `load_active_rules()`; measure `time.perf_counter()` in `screen()`, return both new fields

**Independent test**: Call `screen()` → assert `latency_ms` is a non-negative float. Call `load_active_rules()` with a mocked rule set at version 7 → assert `response.rule_set_version == "7"`.

---

### Phase 3: Pipeline wiring + pre-screener stage 0 (US1 + US4 — P1)

**Goal**: `GuardrailPipelineService` runs `SafetyPreScreenerService.screen()` as stage 0; blocks create `TrustBlockedActionRecord` with `layer=GuardrailLayer.pre_screener` and emit Kafka event.

**Prerequisites**: Phase 1 (enum), Phase 2 (latency fields on PreScreenResponse)

**Files**:
- `apps/control-plane/src/platform/trust/guardrail_pipeline.py`:
  1. Add `pre_screener: Any | None = None` to `__init__` parameter list (with `self.pre_screener = pre_screener`)
  2. Prepend `GuardrailLayer.pre_screener` to `LAYER_ORDER`
  3. Add `elif layer == GuardrailLayer.pre_screener: basis = await self._evaluate_pre_screener(payload, context)` in `evaluate_layer`
  4. Add `_evaluate_pre_screener()` private method (returns `str | None` basis; stores `rule_set_version` + `matched_rule` in `context["policy_basis_detail"]`)
  5. Add `_emit_prescreener_latency()` module-level helper using `opentelemetry.metrics.get_meter`

**Independent test**: Pipeline with mocked `pre_screener` that returns `blocked=True` → assert `evaluate_full_pipeline` returns `allowed=False`, `layer=GuardrailLayer.pre_screener`; `record_blocked_action` called with correct layer; Kafka `publish_guardrail_blocked` called with `layer="pre_screener"`.

---

### Phase 4: Tool output sanitization endpoint (US3 — P1)

**Goal**: `POST /api/v1/policies/gate/sanitize-output` provides the structural call surface for all tool-result paths.

**Files**:
- `apps/control-plane/src/platform/policies/schemas.py` — add `SanitizeToolOutputRequest(BaseModel)` with fields: `output: str`, `agent_id: UUID`, `agent_fqn: str`, `tool_fqn: str`, `execution_id: UUID | None = None`, `workspace_id: UUID | None = None`
- `apps/control-plane/src/platform/policies/router.py` — add `@router.post("/gate/sanitize-output", response_model=SanitizationResult)` delegating to `tool_gateway_service.sanitize_tool_output()`

**Independent test**: POST with bearer token in `output` → assert `[REDACTED:bearer_token]` in response; POST with clean output → assert byte-identical output + `redaction_count == 0`.

---

### Phase 5: YAML content type for rule-set creation (US5 — P2)

**Goal**: `POST /api/v1/trust/prescreener/rule-sets` accepts `application/yaml` bodies; JSON body behavior unchanged.

**Files**:
- `apps/control-plane/src/platform/trust/router.py` — replace `payload: PreScreenerRuleSetCreate` parameter with `request: Request`; dispatch on `Content-Type`; validate with `PreScreenerRuleSetCreate.model_validate(data)`; `import yaml` at top of file

**Independent test**: POST with YAML body → 201 + correct rule_count; POST with JSON → unchanged behavior; POST with malformed YAML → 422 + `YAML_PARSE_ERROR`.

---

## API Endpoints Used / Modified

| Endpoint | Status | Change |
|----------|--------|--------|
| `POST /api/v1/trust/guardrail/evaluate` | Existing | Returns `layer="pre_screener"` for pre-screener blocks |
| `GET /api/v1/trust/blocked-actions?layer=pre_screener` | Existing | Now returns pre-screener blocks |
| `POST /api/v1/trust/prescreener/screen` | Existing | Response now includes `latency_ms`, `rule_set_version` |
| `POST /api/v1/trust/prescreener/rule-sets` | Existing | Now also accepts `Content-Type: application/yaml` |
| `POST /api/v1/policies/gate/sanitize-output` | **NEW** | Structural sanitization surface for tool results |

## Dependencies

- **Feature 028 (Policy Governance Engine)**: Provides `OutputSanitizer`, `ToolGatewayService`, `SanitizationResult` schema. Already deployed; used by Phase 4.
- **Feature 012 (Trust bounded context)**: Provides `SafetyPreScreenerService`, `GuardrailPipelineService`, `TrustBlockedActionRecord`. Extended by Phases 2–3.
- **Feature 051 (FQN Namespace)**: Migration 041 is `down_revision` for 042.
- **Feature 047 (Observability Stack)**: OTel collector already deployed; `prescreener.latency_ms` histogram is consumed by existing Prometheus + Grafana without new infrastructure.

## Complexity Tracking

No constitution violations. No complexity justification required.

| Category | Count |
|---|---|
| Modified Python source files | 6 (`trust/models.py`, `trust/schemas.py`, `trust/prescreener.py`, `trust/guardrail_pipeline.py`, `trust/router.py`, `policies/router.py`) |
| Modified Python schema files | 1 (`policies/schemas.py`) |
| New files | 1 migration (`042_prescreener_guardrail_layer.py`) |
| New test modules | 5 |
| New bounded contexts | 0 |
| New database tables or columns | 0 |
| New Alembic migrations | 1 (enum value addition only) |
| New Kafka topics | 0 |
| New API endpoints | 1 (`POST /gate/sanitize-output`) |

User input refinements discovered during research:

1. Steps 1–4 of the user's plan (trust/rules/ directory, rule_loader.py, pre_screener.py, output_sanitizer.py) are no-ops — all already implemented.
2. Step 7 (POST/GET /api/v1/trust/rules endpoints) — already exist; only YAML content-type extension for POST is new.
3. Step 8 (latency tracking) is genuine but scoped to `screen()` measurement + OTel histogram; no Redis caching needed (in-process `_compiled_patterns` already O(1)).
4. US3 tool sanitization guarantee is delivered via a new canonical REST endpoint rather than execution-engine modifications — the Go runtime handles tool execution; Python provides the sanitization API boundary.
