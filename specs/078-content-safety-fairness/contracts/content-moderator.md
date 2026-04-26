# Content Moderator Contract

**Feature**: 078-content-safety-fairness
**Module**: `apps/control-plane/src/platform/trust/services/content_moderator.py`

The `ContentModerator` is the orchestrator invoked from `guardrail_pipeline.py` at the `output_moderation` layer. It picks providers based on workspace policy, applies failure-mode logic, enforces budgets, applies the action resolver, and persists events.

## Service API

```python
class ContentModerator:
    def __init__(
        self,
        *,
        repository: TrustRepository,
        providers: ModerationProviderRegistry,
        policy_engine: Any,
        residency_service: ResidencyService,
        secrets: SecretProvider,
        audit_chain: AuditChainService,
        producer: EventProducer | None,
        redis: AsyncRedisClient,
        settings: PlatformSettings,
    ) -> None: ...

    async def moderate_output(
        self,
        *,
        execution_id: UUID,
        agent_id: UUID,
        workspace_id: UUID,
        original_content: str,
        canonical_audit_ref: str,
        elapsed_budget_ms: int = 0,
    ) -> ModerationVerdict:
        """Run the configured policy against the agent output.

        Returns a ModerationVerdict carrying:
          - action: "deliver_unchanged" | "deliver_replaced" | "deliver_redacted" | "block"
          - replacement_content: str | None  (for deliver_replaced / block)
          - redacted_content: str | None     (for deliver_redacted)
          - triggered_categories: list[str]
          - scores_per_category: dict[str, float]
          - latency_ms: int
          - provider: str
          - persisted_event_id: UUID
        """
```

## Algorithm

```
1. Load active policy for workspace_id.
   If none → run regex floor only (existing behaviour); return
   ModerationVerdict(action="deliver_unchanged"). No DB row.
2. If elapsed_budget_ms ≥ policy.per_execution_budget_ms:
       Apply provider_failure_action; persist event; emit alert; return.
3. Detect language (provider-specific or fasttext fallback).
4. Resolve provider:
       provider = policy.language_pins[lang] or policy.primary_provider
5. Pre-flight cost cap: redis INCRBY trust:moderation_cost:{ws}:{yyyy-mm}
   by est_cost; if past monthly_cost_cap_eur → fail action.
6. Pre-flight residency: residency_service.allow_egress(workspace_id,
   provider.region) — fail action on disallow.
7. Call provider with per_call_timeout_ms.
   On timeout/error → try fallback_provider, then self_hosted, then
   apply provider_failure_action; persist provider_failed event.
8. Normalise scores into canonical taxonomy.
9. action_resolver.resolve(triggered_categories, policy):
       Multi-category triggers → safer action wins (block > redact > flag).
10. Apply allow_list overrides (per-agent category exemptions).
11. Construct ModerationVerdict and persist event row.
12. If action == flag → emit monitor.alerts event.
13. Return verdict.
```

## ModerationProvider Protocol

```python
class ModerationProvider(Protocol):
    name: str

    async def score(
        self,
        text: str,
        *,
        language: str | None = None,
        categories: list[str],
    ) -> ProviderVerdict: ...

@dataclass(slots=True, frozen=True)
class ProviderVerdict:
    scores: dict[str, float]                   # canonical taxonomy keys
    extra: dict[str, Any]                      # provider-native scores not in taxonomy
    detected_language: str | None
    latency_ms: int
    region: str | None                         # for residency check audit
```

## Provider adapters

| Adapter | Authentication | Rule notes |
|---|---|---|
| `openai_moderation` | API key from `secret/data/trust/moderation-providers/openai/...` | NOT routed through model_router (D-004). Direct `httpx` call to `/v1/moderations`. |
| `anthropic_safety` | API key from Vault, but the actual call goes through `common.clients.model_router` (D-005, rule 11). | Moderation prompt + structured output. Cost attributed via existing model_router cost path. |
| `google_perspective` | API key from Vault. Direct `httpx` call. | Native categories mapped to canonical taxonomy in the adapter. |
| `self_hosted_classifier` | None. HuggingFace model lazy-loaded on first call. Model name from `settings.content_moderation.self_hosted_model_name`. | Always available as floor. |

## Action resolver (`moderation_action_resolver.py`)

```python
SAFETY_ORDER = ("block", "redact", "flag")

def resolve_action(
    triggered: list[str],
    policy: ModerationPolicy,
) -> str:
    actions = {policy.action_per_category.get(c, policy.default_action)
               for c in triggered}
    for safer in SAFETY_ORDER:
        if safer in actions:
            return safer
    return "flag"  # safe fallback
```

## Replacement content

| Action | Replacement |
|---|---|
| `block` | Configurable safe message; default: `"This response was withheld because it violates the workspace's content safety policy."` |
| `redact` | Per-category placeholder via existing `output_sanitizer` regex helpers (e.g., `[REDACTED:pii_leakage]`). |
| `flag` | None — original content delivered unchanged. |

## Failure modes

| Scenario | Behaviour |
|---|---|
| Provider timeout | Try fallback → self_hosted → `provider_failure_action`. Persist event with `action_taken='fail_closed_blocked'` or `'fail_open_delivered'`. |
| Cost cap hit mid-month | Same as failure: try self_hosted (if cap doesn't include it), else apply failure action. Operator alert on first hit per cooldown. |
| Residency disallow | Skip provider; try next; apply failure action if all disallowed. |
| Agent in allow-list for triggered category | Action becomes `flag` (still recorded), or `none` (no event) depending on `audit_all_evaluations`. |
| No active policy | Skip all of the above; existing regex floor runs; no event row. |

## Unit-test contract

- **CM1** — workspace with no policy → no event row; existing regex behaviour preserved.
- **CM2** — policy with `block` on toxicity at threshold 0.8; provider returns 0.9 → `action="block"`, replacement content delivered, original content NOT in event row (only `audit_chain_ref`).
- **CM3** — policy with `redact` on pii_leakage at threshold 0.5; provider returns 0.7 → `action="deliver_redacted"`, redacted content used downstream.
- **CM4** — policy with `flag` on violence at threshold 0.6; provider returns 0.7 → `action="deliver_unchanged"`, event row persisted, `monitor.alerts` event emitted.
- **CM5** — primary provider times out; fallback returns 0.9 → fallback verdict applied; provider_failed event NOT emitted because fallback succeeded.
- **CM6** — primary AND fallback time out; self_hosted returns 0.6 → self_hosted verdict applied; one provider_failed event for primary, one for fallback.
- **CM7** — all providers fail and `provider_failure_action='fail_closed'` → `action="block"` with replacement content; provider_failed events for each attempted provider.
- **CM8** — all providers fail and `provider_failure_action='fail_open'` → `action="deliver_unchanged"`; events recorded; operator alert emitted.
- **CM9** — multi-category trigger (toxicity flag + pii_leakage block) → `action="block"` (safer wins).
- **CM10** — agent in `agent_allowlist` for `violence_self_harm` triggered category → category dropped from triggered set; no enforcement.
- **CM11** — language pin selects per-language provider for Spanish output.
- **CM12** — cost cap exceeded → cost_cap_exceeded event; provider_failure_action applied; cooldown prevents alert flooding.
- **CM13** — residency disallows primary provider's region → primary skipped; next provider in chain attempted.
- **CM14** — group attributes / PII never appear in observability labels (assert via structured-log capture).
- **CM15** — `flag` action emits `monitor.alerts` exactly once per event (no double-emission on retry).
