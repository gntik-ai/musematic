# Interface Contracts: Safety Pre-Screener and Secret Sanitization

**Feature**: 054-safety-prescreener-sanitization | **Date**: 2026-04-18

---

## Contract 1 — GuardrailLayer enum extension

**Surface**: `GuardrailLayer` Python enum (trust/models.py) + PostgreSQL enum type `guardraillayer`

**New value**: `pre_screener`

**Guarantee**: Any caller passing `layer=GuardrailLayer.pre_screener` to `evaluate_layer()` or filtering `TrustBlockedActionRecord` by `layer="pre_screener"` MUST be supported after migration 042 is applied.

**Backward compatibility**: All existing `GuardrailLayer` values and their filter/query semantics are unchanged.

---

## Contract 2 — PreScreenResponse schema extension

**Surface**: `PreScreenResponse` Pydantic model — returned by `POST /prescreener/screen` and by `SafetyPreScreenerService.screen()`

| Field | Type | Since | Notes |
|---|---|---|---|
| `blocked` | `bool` | existing | Unchanged |
| `matched_rule` | `str \| None` | existing | Unchanged |
| `passed_to_full_pipeline` | `bool` | existing | Unchanged |
| `latency_ms` | `float \| None` | **new** | Time in ms `screen()` took; None if not measured |
| `rule_set_version` | `str \| None` | **new** | Active rule-set version string; None if no active set |

**Backward compatibility**: Both new fields default to `None`. All existing callers that pattern-match on `blocked` and `matched_rule` are unaffected.

---

## Contract 3 — GuardrailPipelineService.evaluate_layer() — pre_screener case

**Surface**: `GuardrailPipelineService` in `trust/guardrail_pipeline.py`

**Pre-screener semantics**:
- If `self.pre_screener is None` → returns `GuardrailEvaluationResponse(allowed=True, layer=GuardrailLayer.pre_screener)` (no-op; FR-004)
- If active rule set is empty (`_compiled_patterns == {}`) → same as above (FR-004)
- If a pattern matches → returns `GuardrailEvaluationResponse(allowed=False, layer=GuardrailLayer.pre_screener, policy_basis=f"pre_screener:{matched_rule}")` and creates `TrustBlockedActionRecord` with `policy_basis_detail=json({"matched_rule": ..., "rule_set_version": ...})`
- `evaluate_full_pipeline` with `request.layer=GuardrailLayer.input_sanitization` now also runs `pre_screener` first (LAYER_ORDER[0])

**Backward compatibility**: The `__init__` parameter `pre_screener` defaults to `None`. Existing instantiations without this parameter are unaffected.

---

## Contract 4 — POST /prescreener/rule-sets (YAML content type)

**Surface**: `POST /api/v1/trust/prescreener/rule-sets`

**Existing behavior** (unchanged): `Content-Type: application/json` body → 201 created

**New behavior**: `Content-Type: application/yaml` body → parsed as YAML → validated against `PreScreenerRuleSetCreate` → 201 created; stored JSON in MinIO is identical to the JSON path.

**Error cases**:
- Malformed YAML → 422 with `{"code": "YAML_PARSE_ERROR", "message": "<parse error detail>"}`
- Valid YAML but invalid schema → 422 (existing Pydantic validation behavior)

**Round-trip guarantee**: YAML and JSON representations of the same rule set produce byte-for-byte identical stored content (SC-007).

---

## Contract 5 — POST /api/v1/policies/gate/sanitize-output (NEW)

**Surface**: `policies/router.py` — new endpoint

**Request**:
```json
{
  "output": "<raw tool output string>",
  "agent_id": "<uuid>",
  "agent_fqn": "<namespace:name>",
  "tool_fqn": "<namespace:tool-name>",
  "execution_id": "<uuid or null>",
  "workspace_id": "<uuid or null>"
}
```

**Response** (`SanitizationResult`):
```json
{
  "output": "<sanitized string>",
  "redactions": [
    {"type": "bearer_token", "count": 1},
    ...
  ],
  "redaction_count": 1
}
```

**Semantics**:
- Applies all 5 existing secret patterns; returns sanitized output
- If at least one redaction occurs, creates `PolicyBlockedActionRecord` with `action_type="sanitizer_redaction"` (existing behavior)
- If no patterns match, `output` is byte-identical to input; `redactions=[]`; no audit record

**Authentication**: Requires valid JWT (standard platform dependency).

---

## Contract 6 — OTel metric: prescreener.latency_ms

**Surface**: OpenTelemetry meter `"platform.trust.guardrail_pipeline"` (emitted from `trust/guardrail_pipeline.py`)

**Metric type**: Histogram

**Unit**: milliseconds

**Attributes**:
- `rule_set_version` (string): active rule-set version, or `"none"` when no rule set loaded

**When emitted**: Once per `evaluate_layer(GuardrailLayer.pre_screener, ...)` call that runs the pre-screener (i.e., `self.pre_screener is not None`).

**Consumers**: Existing OTel Collector → Prometheus → Grafana (feature 047 observability stack). No new infrastructure.

---

## Contract 7 — TrustBlockedActionRecord for pre_screener blocks

**Surface**: `GET /api/v1/trust/blocked-actions?layer=pre_screener` (existing query surface)

**Record fields for pre-screener blocks**:

| Field | Value |
|---|---|
| `layer` | `"pre_screener"` |
| `policy_basis` | `"pre_screener:{matched_rule_name}"` |
| `policy_basis_detail` | `{"matched_rule": "<name>", "rule_set_version": "<version>"}` (JSON string) |
| `agent_id`, `agent_fqn` | From request context |
| `execution_id`, `interaction_id`, `workspace_id` | From request context (nullable) |

**Guarantee**: Pre-screener blocks appear on the same query surface as other guardrail-layer blocks within 60 seconds of occurrence (SC-005).
