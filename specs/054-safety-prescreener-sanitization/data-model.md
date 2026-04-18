# Data Model: Safety Pre-Screener and Secret Sanitization

**Feature**: 054-safety-prescreener-sanitization | **Date**: 2026-04-18

---

## Entities Modified

### 1. GuardrailLayer (StrEnum) — `trust/models.py`

**Change**: Add `pre_screener = "pre_screener"` as first logical value (additive; Brownfield Rule 6).

```python
class GuardrailLayer(StrEnum):
    pre_screener = "pre_screener"       # NEW — US1
    input_sanitization = "input_sanitization"
    prompt_injection = "prompt_injection"
    output_moderation = "output_moderation"
    tool_control = "tool_control"
    memory_write = "memory_write"
    action_commit = "action_commit"
```

**Database impact**: Requires Alembic migration 042 to issue:
```sql
ALTER TYPE guardraillayer ADD VALUE IF NOT EXISTS 'pre_screener';
```
The column `trust_blocked_action_records.layer` uses `SAEnum(GuardrailLayer)`; records with `layer='pre_screener'` are now storable.

---

### 2. PreScreenResponse (Pydantic schema) — `trust/schemas.py`

**Change**: Add two optional fields with `None` defaults (backward-compatible; Brownfield Rule 7).

```python
class PreScreenResponse(BaseModel):
    blocked: bool
    matched_rule: str | None = None
    passed_to_full_pipeline: bool
    latency_ms: float | None = None        # NEW — US2: measured in screen()
    rule_set_version: str | None = None    # NEW — US4: forwarded to audit record
```

**Callers**: `POST /prescreener/screen` (existing endpoint, now returns latency + version); `evaluate_layer` in `GuardrailPipelineService` (receives response, reads latency + version for audit).

---

### 3. SafetyPreScreenerService — `trust/prescreener.py`

**Change**: Add `_active_version: str | None = None` instance attribute. Set it in `load_active_rules()` from the loaded rule set's version. Measure elapsed time in `screen()` and return in `PreScreenResponse`.

**State tracking**:
```
_compiled_patterns: dict[str, re.Pattern[str]]  # existing
_active_version: str | None                      # NEW — holds version string for audit
```

**`screen()` signature** (unchanged externally):
```python
async def screen(self, content: str, context_type: str) -> PreScreenResponse
```
Return value: `PreScreenResponse(blocked=True/False, matched_rule=..., passed_to_full_pipeline=..., latency_ms=<float>, rule_set_version=self._active_version)`.

---

### 4. GuardrailPipelineService — `trust/guardrail_pipeline.py`

**Change 1** — Add `pre_screener` injection to `__init__` (optional, backward-compatible):
```python
def __init__(
    self,
    *,
    repository: TrustRepository,
    settings: Any,
    producer: Any | None,
    policy_engine: Any | None,
    pre_screener: Any | None = None,      # NEW
) -> None:
    ...
    self.pre_screener = pre_screener
```

**Change 2** — Prepend `GuardrailLayer.pre_screener` to `LAYER_ORDER`:
```python
LAYER_ORDER: ClassVar[list[GuardrailLayer]] = [
    GuardrailLayer.pre_screener,           # NEW — stage 0
    GuardrailLayer.input_sanitization,
    GuardrailLayer.prompt_injection,
    GuardrailLayer.output_moderation,
    GuardrailLayer.tool_control,
    GuardrailLayer.memory_write,
    GuardrailLayer.action_commit,
]
```

**Change 3** — Add `elif` case in `evaluate_layer()`:
```python
elif layer == GuardrailLayer.pre_screener:
    basis = await self._evaluate_pre_screener(payload, context)
```

**Change 4** — New `_evaluate_pre_screener()` private method:
```python
async def _evaluate_pre_screener(
    self, payload: dict[str, Any], context: dict[str, Any]
) -> str | None:
    if self.pre_screener is None:
        return None
    content = json.dumps(payload, sort_keys=True, default=str)
    response = await self.pre_screener.screen(content, context.get("context_type", "input"))
    if response.latency_ms is not None:
        # emit OTel histogram: prescreener.latency_ms, tag rule_set_version
        _emit_prescreener_latency(response.latency_ms, response.rule_set_version)
    if not response.blocked:
        return None
    rule_detail = json.dumps({
        "matched_rule": response.matched_rule,
        "rule_set_version": response.rule_set_version,
    })
    # Store detail in context so record_blocked_action picks it up
    context["policy_basis_detail"] = rule_detail
    return f"pre_screener:{response.matched_rule}"
```

**OTel emit helper** (module-level private function in `guardrail_pipeline.py`):
```python
def _emit_prescreener_latency(latency_ms: float, version: str | None) -> None:
    from opentelemetry import metrics as otel_metrics
    meter = otel_metrics.get_meter(__name__)
    histogram = meter.create_histogram("prescreener.latency_ms")
    histogram.record(latency_ms, {"rule_set_version": version or "none"})
```

---

### 5. trust/router.py — YAML content-type for POST /prescreener/rule-sets

**Change**: Replace typed `PreScreenerRuleSetCreate` body with raw `Request` + content-type dispatch:

```python
from fastapi import Request
import yaml

@router.post("/prescreener/rule-sets", response_model=PreScreenerRuleSetResponse, ...)
async def create_prescreener_rule_set(
    request: Request,
    current_user: ...,
    prescreener_service: ...,
) -> PreScreenerRuleSetResponse:
    content_type = request.headers.get("content-type", "application/json").split(";")[0].strip()
    raw = await request.body()
    if content_type == "application/yaml":
        try:
            data = yaml.safe_load(raw.decode("utf-8"))
        except yaml.YAMLError as exc:
            raise ValidationError("YAML_PARSE_ERROR", str(exc)) from exc
    else:
        import json
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError("JSON_PARSE_ERROR", str(exc)) from exc
    payload = PreScreenerRuleSetCreate.model_validate(data)
    return await prescreener_service.create_rule_set(payload)
```

---

### 6. policies/router.py — New POST /api/v1/policies/gate/sanitize-output endpoint

**Change**: Add endpoint backed by `ToolGatewayService.sanitize_tool_output()`.

**Request schema** (new Pydantic model in `policies/schemas.py`):
```python
class SanitizeToolOutputRequest(BaseModel):
    output: str
    agent_id: UUID
    agent_fqn: str
    tool_fqn: str
    execution_id: UUID | None = None
    workspace_id: UUID | None = None
```

**Response**: existing `SanitizationResult` schema (from `policies/schemas.py`).

**Route**:
```python
@router.post("/gate/sanitize-output", response_model=SanitizationResult)
async def sanitize_tool_output_endpoint(
    payload: SanitizeToolOutputRequest,
    session: AsyncSession = Depends(get_db),
    gateway: ToolGatewayService = Depends(get_tool_gateway_service),
) -> SanitizationResult:
    return await gateway.sanitize_tool_output(
        payload.output,
        agent_id=payload.agent_id,
        agent_fqn=payload.agent_fqn,
        tool_fqn=payload.tool_fqn,
        execution_id=payload.execution_id,
        workspace_id=payload.workspace_id,
        session=session,
    )
```

---

## Alembic Migration 042

**File**: `apps/control-plane/migrations/versions/042_prescreener_guardrail_layer.py`

```python
"""Add pre_screener value to guardraillayer enum."""

from __future__ import annotations
from alembic import op

revision = "042_prescreener_guardrail_layer"
down_revision = "041_fqn_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE guardraillayer ADD VALUE IF NOT EXISTS 'pre_screener'")


def downgrade() -> None:
    pass  # PostgreSQL does not support removing enum values
```

---

## No New Tables or Columns

All storage changes are covered by:
1. Migration 042 (enum value addition — no new columns)
2. `PreScreenResponse` schema extensions (runtime schema, no DB impact)
3. `policy_basis_detail` JSON string on existing `TrustBlockedActionRecord` (existing TEXT column)

Zero new Kafka topics. Zero new bounded contexts.
