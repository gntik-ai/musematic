# Model Router Contract

**Feature**: 075-model-catalog-fallback
**Module**: `apps/control-plane/src/platform/common/clients/model_router.py`

## Public interface

```python
@dataclass(frozen=True)
class ModelRouterResponse:
    content: str
    model_used: str              # e.g. "openai:gpt-4o" — possibly a fallback
    tokens_in: int
    tokens_out: int
    latency_ms: int
    fallback_taken: FallbackAuditRecord | None

class ModelRouter:
    async def complete(
        self,
        *,
        workspace_id: UUID,
        agent_id: UUID | None = None,
        step_binding: str | None = None,
        messages: list[dict],
        response_format: dict | None = None,
        timeout_seconds: float = 25.0,
    ) -> ModelRouterResponse: ...
```

## Per-call algorithm

```
1. Resolve binding:
   primary_binding = step_binding
                   ?? (agent.default_model_binding if agent_id else None)
                   ?? raise InvalidBindingError("no model binding")

2. Resolve catalogue entry for primary_binding (cache 60s LRU):
   entry = await catalog_service.get(primary_binding)
   if entry is None: raise CatalogEntryNotFoundError
   if entry.status == "blocked": raise ModelBlockedError
   if entry.status == "deprecated": emit warning_log + proceed

3. Resolve fallback policy (cache 60s LRU):
   policy = await fallback_service.resolve(workspace_id, agent_id, primary_binding)
   # Returns FallbackPolicy or None

4. Check sticky cache:
   sticky = await redis.get(f"router:primary_sticky:{workspace_id}:{entry.id}")
   if sticky == "in_fallback" and policy is not None:
       # Skip primary; go straight to fallback chain
       return await _call_chain(policy.fallback_chain, ...)

5. Apply prompt-injection input sanitisation + system-prompt hardening
   (per contracts/prompt-injection-defense.md).

6. Resolve credential:
   credential = await rotatable_secret_provider.get_current(
       f"providers/{workspace_id}/{entry.provider}"
   )
   # May accept previous credential during rotation overlap (UPD-024)

7. Call primary with retries (policy.retry_count, policy.backoff_strategy):
   try:
       resp = await _call_provider(entry, credential, messages, ...)
       await redis.set(
           f"router:primary_sticky:{workspace_id}:{entry.id}",
           "use_primary",
           ex=policy.recovery_window_seconds if policy else 300,
       )
       return _apply_output_validation(resp)
   except (ProviderOutage, ProviderTimeout, RateLimitedError) as e:
       if policy is None: raise
       await redis.set(
           f"router:primary_sticky:{workspace_id}:{entry.id}",
           "in_fallback",
           ex=policy.recovery_window_seconds,
       )
       return await _call_chain(policy.fallback_chain, ...)
```

## Fallback chain walking

Each chain entry gets ONE attempt (no retries per fallback). If it
fails, the router advances to the next entry. If all fail, raises
`FallbackExhaustedError` with structured per-tier failure list.

Each successful fallback emits a `model.fallback.triggered` Kafka event
with payload:

```json
{
  "workspace_id": "...",
  "agent_id": "...",
  "primary_model_id": "...",
  "fallback_chain_index": 1,
  "fallback_model_used": "openai:gpt-4o",
  "failure_reason": "provider_5xx",
  "elapsed_latency_ms": 1240,
  "retry_attempts_on_primary": 3
}
```

## Telemetry

Prometheus metrics emitted:

- `model_router_calls_total{workspace_id, model_id, outcome}` —
  counter (`outcome ∈ {success, fallback, error}`).
- `model_router_latency_seconds{workspace_id, model_id}` — histogram.
- `model_router_fallback_rate{primary_model_id}` — counter
  ratio (derived in Grafana).
- `model_router_validation_failures_total{reason}` — counter
  (`reason ∈ {blocked, deprecated_warn, not_found, credential_missing}`).

## Failure modes

| Error | HTTP status (when propagated to caller) | Behaviour |
|---|---|---|
| `InvalidBindingError` | 400 | Neither `agent_id` nor `step_binding` provided. |
| `CatalogEntryNotFoundError` | 502 | Binding references a non-existent catalogue entry. |
| `ModelBlockedError` | 503 | Catalogue entry is `blocked`. |
| `CredentialNotConfiguredError` | 503 | No `model_provider_credentials` row for workspace/provider. |
| `FallbackExhaustedError` | 502 | All chain entries failed; includes per-tier failure list. |
| `ProviderOutage` | 502 (if no fallback) | Primary provider 5xx without fallback policy. |
| `ProviderTimeout` | 504 | Primary timed out without fallback. |
| `PromptInjectionBlocked` | 400 | Output validator blocked response per policy. |

## Unit-test contract

- **MR1** — happy path: binding resolves, primary succeeds, no fallback.
- **MR2** — blocked: catalogue entry status=`blocked` → immediate error.
- **MR3** — deprecated: warning logged, call proceeds.
- **MR4** — fallback triggered: primary 5xx → retry exhausts → chain[0]
  succeeds.
- **MR5** — fallback exhausted: all chain entries fail → structured
  error.
- **MR6** — sticky cache: in-fallback state skips primary for 5 minutes.
- **MR7** — credential resolution: router uses `Authorization: Bearer`
  header; value comes from RotatableSecretProvider.
- **MR8** — rotation overlap: both current and previous credentials
  accepted during overlap window (delegates to UPD-024).
- **MR9** — 2 existing call-site migrations: `LLMCompositionClient.generate()`
  and `LLMJudgeScorer._judge_once_provider()` both delegate to
  `ModelRouter.complete()` under the feature flag.
