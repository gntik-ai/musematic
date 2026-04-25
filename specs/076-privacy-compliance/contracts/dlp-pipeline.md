# DLP Pipeline Contract

**Feature**: 076-privacy-compliance
**Modules**:
- `apps/control-plane/src/platform/privacy_compliance/services/dlp_service.py`
- `apps/control-plane/src/platform/privacy_compliance/dlp/scanner.py`

## Rule engine + scanner

```python
@dataclass(frozen=True)
class DLPMatch:
    rule_id: UUID
    rule_name: str
    classification: str  # pii | phi | financial | confidential
    action: str          # redact | block | flag
    start: int
    end: int

class DLPScanner:
    def scan(
        self,
        text: str,
        workspace_id: UUID | None,
    ) -> list[DLPMatch]:
        """Returns all matches across enabled rules.
        Matches include ranges; match TEXT is never returned/stored."""

    def apply_actions(
        self,
        text: str,
        matches: list[DLPMatch],
    ) -> DLPScanResult:
        """Applies actions in order: redact/block/flag.
        Returns transformed text + events to emit."""

@dataclass
class DLPScanResult:
    output_text: str           # post-transformation
    blocked: bool              # True if any match's action was 'block'
    events: list[DLPEventInput]
```

Rules are cached in-process with a 60 s TTL; workspace → enabled-rules
lookup is the hot path.

## Insertion points

### Point 1 — `policies/gateway.py` (tool output scan)

```python
# policies/gateway.py — ToolGatewayService.sanitize_tool_output()
# Existing (line 187–206)
sanitized = await self.sanitizer.sanitize(...)
# NEW — after sanitisation:
scan_result = await self._dlp.scan_and_apply(
    sanitized.content, workspace_id=request.workspace_id
)
if scan_result.blocked:
    await self._dlp_service.emit_events(
        scan_result.events, execution_id=request.execution_id
    )
    raise ToolOutputBlocked(...)
for event in scan_result.events:
    await self._dlp_service.emit_event(event, execution_id=request.execution_id)
return sanitized.copy_with(content=scan_result.output_text)
```

### Point 2 — `trust/guardrail_pipeline.py` (new layer)

```python
# trust/guardrail_pipeline.py — GuardrailLayer enum
class GuardrailLayer(StrEnum):
    pre_screener = "pre_screener"
    input_sanitization = "input_sanitization"
    prompt_injection = "prompt_injection"
    output_moderation = "output_moderation"
    dlp_scan = "dlp_scan"          # NEW — inserted here
    tool_control = "tool_control"
    memory_write = "memory_write"
    action_commit = "action_commit"

# In LAYER_ORDER, insert after output_moderation.
# dlp_scan layer calls dlp_service.scan_and_apply(...) the same way.
```

## Event emission

Every match produces a `DLPEvent` row AND a `privacy.dlp.event` Kafka
event with payload:

```json
{
  "rule_id": "<UUID>",
  "rule_name": "ssn_us",
  "classification": "pii",
  "workspace_id": "<UUID>",
  "execution_id": "<UUID|null>",
  "action_taken": "redact",
  "match_summary": "pii:ssn",        // CLASSIFICATION LABEL ONLY — never raw text
  "timestamp": "<ISO8601>"
}
```

The `match_summary` is a short label (classification + pattern name),
NOT the matched content, per FR-020.

## REST endpoints

Admin under `/api/v1/privacy/dlp/*`:

| Method + path | Purpose | Role |
|---|---|---|
| `GET /api/v1/privacy/dlp/rules` | List rules | `privacy_officer`, `platform_admin`, `superadmin` |
| `POST /api/v1/privacy/dlp/rules` | Create workspace-scoped rule | `privacy_officer`, `platform_admin`, `superadmin` |
| `PATCH /api/v1/privacy/dlp/rules/{id}` | Update rule (enabled, action) — cannot alter seeded patterns | same |
| `DELETE /api/v1/privacy/dlp/rules/{id}` | Delete workspace-scoped rule (seeded rejected with 403) | same |
| `GET /api/v1/privacy/dlp/events?workspace_id=&from=&to=&rule_id=` | List events | `privacy_officer`, `auditor`, `compliance_officer`, `superadmin` |
| `GET /api/v1/privacy/dlp/events/aggregate?workspace_id=&window=` | Aggregate counts | same |

## Seeded rules (platform floor, per research.md D-009)

10+ rules shipped with `seeded=true` in migration 060. Cannot be
deleted; operators can disable per-workspace via a
`workspace_dlp_overrides` future table (v1: the rule's `enabled`
column is global; workspace-scoped disable is a follow-up).

| Name | Classification | Pattern (regex) | Action |
|---|---|---|---|
| `ssn_us` | pii | `\b\d{3}-\d{2}-\d{4}\b` | redact |
| `phone_us` | pii | `\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b` | flag |
| `email` | pii | `[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}` | redact |
| `iban` | pii | `\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b` | flag |
| `credit_card` | financial | `\b(?:\d[ -]*?){13,16}\b` (Luhn-verified app-side) | block |
| `us_routing_number` | financial | `\b\d{9}\b` with hash-check | flag |
| `jwt` | confidential | `eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+` | redact |
| `platform_api_key` | confidential | `msk_[A-Za-z0-9]{32,}` | redact |
| `bearer_token` | confidential | `Bearer\s+[A-Za-z0-9_\-.=]+` | redact |
| `openai_api_key` | confidential | `sk-[A-Za-z0-9]{48}` | redact |

## Unit-test contract

- **DLP1** — scan against a seeded SSN pattern returns one match;
  `redact` transforms output to `[REDACTED:pii]`.
- **DLP2** — scan against a seeded `credit_card` pattern with Luhn
  validation rejects non-Luhn numbers.
- **DLP3** — `block` action: scanner marks `blocked=True`; caller
  raises.
- **DLP4** — `flag` action: output unchanged; event written.
- **DLP5** — workspace-scoped rule augments platform-seeded rules.
- **DLP6** — deleting a seeded rule returns 403.
- **DLP7** — `match_summary` in DB contains classification label,
  NOT matched text.
- **DLP8** — integration with `policies/gateway.py` — blocked tool
  output raises upstream.
- **DLP9** — integration with `trust/guardrail_pipeline.py` — new
  layer runs after output_moderation.
