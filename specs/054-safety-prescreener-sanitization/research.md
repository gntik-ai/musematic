# Research: Safety Pre-Screener and Secret Sanitization

**Feature**: 054-safety-prescreener-sanitization | **Date**: 2026-04-18

---

## Decision 1: User plan steps 1–4 — Already shipped; no new files needed

**Decision**: The four "new file" steps in the user's input plan (trust/rules/ YAML directory, rule_loader.py, pre_screener.py, output_sanitizer.py) are fully implemented in the existing codebase. Scope for this feature is the five enforcement gaps identified in spec.md, not re-implementing these classes.

**Rationale**: `apps/control-plane/src/platform/trust/prescreener.py` contains `SafetyPreScreenerService` with `screen()`, `load_active_rules()`, `create_rule_set()`, `activate_rule_set()`, and the Redis/Kafka hot-reload path. `apps/control-plane/src/platform/policies/sanitizer.py` contains `OutputSanitizer` with 5 pre-compiled secret patterns and `[REDACTED:{type}]` audit logging. Rule-management endpoints (`GET/POST /prescreener/rule-sets`, `POST /prescreener/rule-sets/{id}/activate`) are live in `trust/router.py`.

**Alternatives considered**: Rewriting files (violates Brownfield Rule 1), creating a new rule loader (duplicate of existing `load_active_rules()`).

---

## Decision 2: Pipeline wiring approach — Prepend to LAYER_ORDER, inject prescreener into pipeline

**Decision**: Add `GuardrailLayer.pre_screener` as value 0 in `GuardrailPipelineService.LAYER_ORDER` (in `trust/guardrail_pipeline.py`) and add a corresponding `elif` branch in `evaluate_layer()`. Inject `SafetyPreScreenerService` as an optional parameter to `GuardrailPipelineService.__init__()`. When `pre_screener` is None, the stage is a no-op (FR-004, SC-006).

**Rationale**: `LAYER_ORDER` is the authoritative list; `evaluate_full_pipeline` iterates it in order. Prepending the new layer means it runs before all existing layers with zero changes to the existing layer logic. The `stop_index` calculation in `evaluate_full_pipeline` still works correctly: callers requesting evaluation up to `input_sanitization` will now also run the pre-screener first, which is the intended behavior.

**Alternatives considered**: (a) Calling `screen()` unconditionally before the `LAYER_ORDER` loop — would bypass the existing `record_blocked_action` / Kafka publish infrastructure already in `evaluate_layer`; (b) A separate pipeline bypass method — adds complexity not justified by the scope.

---

## Decision 3: Alembic migration for GuardrailLayer.pre_screener enum value

**Decision**: Add migration `042_prescreener_guardrail_layer.py` that issues `ALTER TYPE guardraillay_er ADD VALUE IF NOT EXISTS 'pre_screener'`. Add `pre_screener = "pre_screener"` to the `GuardrailLayer` Python `StrEnum` in `trust/models.py` (additive; Brownfield Rule 6).

**Rationale**: `TrustBlockedActionRecord.layer` is a PostgreSQL ENUM column backed by `SAEnum(GuardrailLayer)`. Writing a record with `layer=GuardrailLayer.pre_screener` without the migration will raise a database error. The `IF NOT EXISTS` clause makes the migration idempotent.

**Alternatives considered**: Using a string column instead — would break the existing strongly-typed `GuardrailLayer` filter queries on the blocked-actions endpoint.

---

## Decision 4: Latency measurement — time.perf_counter in screen(), latency_ms added to PreScreenResponse

**Decision**: Add `latency_ms: float | None = None` and `rule_set_version: str | None = None` to `PreScreenResponse` (additive with None defaults; Brownfield Rule 7). Add `_active_version: str | None = None` instance attribute to `SafetyPreScreenerService`; set it in `load_active_rules()`. Measure `time.perf_counter()` in `screen()` and populate both fields. In `evaluate_layer` (pipeline), emit an OTel histogram metric `prescreener.latency_ms` tagged with `rule_set_version` using the platform's existing OTel SDK.

**Rationale**: Keeping measurement in `screen()` means latency is always available regardless of whether the call comes from the pipeline or the standalone `POST /prescreener/screen` endpoint. The OTel histogram in `evaluate_layer` covers FR-006 and SC-003. Adding `rule_set_version` to `PreScreenResponse` lets `evaluate_layer` forward it into `policy_basis_detail` of `TrustBlockedActionRecord` without a separate DB lookup.

**Alternatives considered**: Measuring latency only in the pipeline — misses the standalone screen endpoint; using Redis TTL for version lookup at emit time — adds async I/O on the hot path.

---

## Decision 5: Pre-screener block audit record — reuse existing record_blocked_action infrastructure

**Decision**: When `screen()` returns `blocked=True`, `evaluate_layer` calls `record_blocked_action(context, GuardrailLayer.pre_screener, policy_basis)` with `policy_basis = f"pre_screener:{response.matched_rule}"` and stores `{matched_rule_id, rule_set_version}` JSON in `policy_basis_detail`. The existing `TrustBlockedActionRecord` + Kafka publish path in `evaluate_layer` handles the rest — no new tables or Kafka topics.

**Rationale**: The `record_blocked_action` method already creates `TrustBlockedActionRecord`, emits a `GuardrailBlockedPayload` Kafka event, and creates `TrustSignal` + `TrustProofLink`. Reusing it means pre-screener blocks appear on the existing `/trust/blocked-actions` query surface immediately (SC-005) with zero new plumbing.

**Alternatives considered**: A separate `PreScreenerBlockRecord` table — redundant duplication of existing infrastructure; a new Kafka topic — no new topic is needed per the constitution's Kafka registry.

---

## Decision 6: Tool output sanitization guarantee — add POST /api/v1/policies/gate/sanitize-output endpoint

**Decision**: Add `POST /api/v1/policies/gate/sanitize-output` to `policies/router.py`, backed by `ToolGatewayService.sanitize_tool_output()`. This is the canonical API surface through which any caller (execution engine, connectors, test harness) passes raw tool output and receives the sanitized form. The existing `sanitize_tool_output()` method is unchanged; the new endpoint is a thin wrapper.

**Rationale**: `sanitize_tool_output()` exists in `ToolGatewayService` but is never called in any production path (`grep` confirms only definition + one test file reference). The Go Runtime Controller returns tool results via the `workflow.runtime` Kafka topic; the Python execution engine receives them but currently has no sanitization hook. The new endpoint provides a structural enforcement point that any result-processing path can call. It is the lowest-risk additive change that satisfies FR-008 and SC-002 without modifying the execution engine's event processing loop.

**Alternatives considered**: (a) Modifying the execution service's Kafka event handler to call `sanitize_tool_output()` — requires reading and modifying `execution/service.py` which doesn't currently process tool results (execution is in Go); (b) Wrapping `validate_tool_invocation` to also return a sanitizer reference — conflates gate and sanitizer concerns.

---

## Decision 7: YAML content type for rule-set creation — raw body parsing in router

**Decision**: In `trust/router.py`, change the `create_prescreener_rule_set` endpoint to accept `Request` (raw Starlette request) instead of a typed Pydantic body. Inspect `Content-Type`; if `application/yaml`, parse with `yaml.safe_load()` and validate with `PreScreenerRuleSetCreate.model_validate()`; if `application/json`, parse as JSON. Respond 422 for malformed YAML with parse error detail. The stored format (MinIO JSON) is unchanged.

**Rationale**: FastAPI's `Body()` doesn't natively support YAML content negotiation. Using the raw `Request` object is the standard approach for multi-content-type endpoints in FastAPI. `yaml.safe_load()` is already available via PyYAML (already a dependency per CLAUDE.md for CLI features). Validation via `model_validate` happens after parsing, so the same Pydantic schema covers both content types.

**Alternatives considered**: A custom FastAPI `Depends` for YAML parsing — more testable but adds a new dependency pattern not used elsewhere in the codebase; a separate `POST /prescreener/rule-sets/yaml` endpoint — violates Brownfield Rule 7 (backward-compatible) and fragments the API.

---

## Decision 8: User plan step 9 (Redis cache for rules) — Out of scope

**Decision**: Latency reduction via Redis caching of compiled patterns is out of scope. The existing `_compiled_patterns` in-process dict already provides O(1) pattern lookup per call. Redis would add async I/O overhead (RTT ~1ms) on the hot path, which would make the <10ms SLO harder to meet, not easier.

**Rationale**: Patterns are compiled once on `load_active_rules()` and held in memory. The only scenario where Redis caching would help is multi-instance horizontal scaling — but in that case, the Kafka event on activation already triggers `load_active_rules()` on each instance via `handle_rule_set_activated()`. Redis caching of the compiled patterns themselves is redundant.

---

## Summary of Genuine Scope (5 gaps, 7 modified files, 1 migration, 4 test modules)

| Gap | File(s) modified | Complexity |
|---|---|---|
| Pre-screener not wired into pipeline | `trust/models.py`, `trust/guardrail_pipeline.py`, migration 042 | Medium |
| No latency SLO metric | `trust/schemas.py`, `trust/prescreener.py`, `trust/guardrail_pipeline.py` | Low |
| Tool sanitization not guaranteed on all paths | `policies/router.py` | Low |
| Pre-screener blocks not in unified audit stream | `trust/guardrail_pipeline.py` (handled by same evaluate_layer change) | Low |
| No YAML administration format | `trust/router.py` | Low |
