# Phase 0 Research: Model Catalog and Fallback

**Feature**: 075-model-catalog-fallback
**Date**: 2026-04-23

## Scope

Introduce the `model_catalog/` bounded context, the new `common/clients/
model_router.py`, and one Alembic migration (059). Migrate all 2 existing
LLM call sites in the control plane to route through the new router.
Constitution gates: AD-19 (provider-agnostic routing), rule 11 (all LLM
calls via router), rule 10 (credentials via Vault), rule 39
(SecretProvider-only resolution), rule 44 (rotation never echoes secret).

## Decisions

### D-001 — Router scope: 2 migration sites, not 20

**Decision**: The router wraps only the two currently existing LLM call
sites:
1. `apps/control-plane/src/platform/composition/llm/client.py`
   `LLMCompositionClient.generate()` (lines 45–50).
2. `apps/control-plane/src/platform/evaluation/scorers/llm_judge.py`
   `LLMJudgeScorer._judge_once_provider()` (lines 307–312).

The Go reasoning engine does NOT make direct LLM calls — it delegates to
the control plane via gRPC. No Go changes required.

**Rationale**: Phase 0 codebase discovery found only these two sites;
both already use `httpx.AsyncClient` (no provider SDK imports), so the
router can wrap them with minimal invasiveness.

### D-002 — Router surface

**Decision**: Create `ModelRouter` class in `common/clients/
model_router.py` with a single primary method:

```python
class ModelRouter:
    async def complete(
        self,
        *,
        workspace_id: UUID,
        agent_id: UUID | None,       # None → use step-binding only
        step_binding: str | None = None,  # "provider:model_id" override
        messages: list[dict],
        response_format: dict | None = None,
        timeout_seconds: float = 25.0,
    ) -> ModelRouterResponse: ...
```

Resolution order at dispatch: step_binding > agent.default_model_binding
> fail. The method handles:
1. Binding resolution.
2. Catalogue validation (approved / deprecated / blocked).
3. Fallback policy lookup.
4. Per-workspace credential resolution via `RotatableSecretProvider`
   (UPD-024).
5. Provider HTTP call (OpenAI-compatible; the two existing sites already
   use this pattern).
6. Retry + fallback orchestration.
7. Telemetry emission.
8. Prompt-injection defence if enabled for the workspace.

**Rationale**: Single public method keeps the migration surface tiny;
both existing call sites can replace their inline httpx calls with one
`await router.complete(...)`.

### D-003 — Existing call-site migration

**Decision**: `LLMCompositionClient.generate()` becomes a thin wrapper
that delegates to `ModelRouter.complete(...)`. Its existing retry loop
is removed (router handles retries). Same for
`LLMJudgeScorer._judge_once_provider`.

A feature flag `FEATURE_MODEL_ROUTER_ENABLED` (default `false` during
rollout, `true` after cutover) gates the switch; when `false`, the old
direct-httpx path remains active for rollback safety.

**Rationale**: Brownfield Rule 1 (never rewrite) respected; existing
classes keep their public API, internals swap out.

### D-004 — Credential resolution: URL + header split

**Decision**: Current code embeds credentials in `llm_api_url` (e.g.
`https://api.openai.com/v1/chat/completions?api_key=...`). The new
model transitions to:

- Table `model_provider_credentials` stores `(workspace_id, provider,
  vault_ref)`; vault_ref points at a Vault path holding the API key.
- Router reads the key via `RotatableSecretProvider` (UPD-024) and
  injects as `Authorization: Bearer <key>` header.
- Per-provider `base_url` lives in config (`MODEL_ROUTER_OPENAI_BASE_URL`,
  etc.) — separated from the credential so rotation is clean.

During rollout (feature flag off), the old URL-embedded pattern still
works. When flag is on, workspaces without a credential row in the new
table fall back to the env-var URL pattern with a one-line deprecation
warning.

**Rationale**: Aligns with constitution rule 43 (OAuth client secrets in
Vault, never in DB) generalised to provider secrets.

### D-005 — Alembic migration number

**Decision**: **059**. Chain is 057 (feature 073) → 058 (feature 074) →
059 (this feature).

### D-006 — Seed catalogue

**Decision**: Migration 059 seeds the catalogue with six entries so the
feature is useful on day one:

| Provider | Model ID | Tier | Context window | Approval expires |
|---|---|---|---|---|
| `openai` | `gpt-4o` | `tier1` | 128000 | now + 90 days |
| `openai` | `gpt-4o-mini` | `tier2` | 128000 | now + 90 days |
| `anthropic` | `claude-opus-4-6` | `tier1` | 200000 | now + 90 days |
| `anthropic` | `claude-sonnet-4-6` | `tier1` | 200000 | now + 90 days |
| `anthropic` | `claude-haiku-4-5` | `tier2` | 200000 | now + 90 days |
| `google` | `gemini-2.0-pro` | `tier1` | 2000000 | now + 90 days |

Seed-time `approved_by` references a well-known "system_bootstrap" user
(seeded in an earlier migration if absent). Model cards for the six
entries are seeded with placeholder data (`TODO: replace with vendor
cards`) and surface compliance gaps until filled.

**Rationale**: Ensures the router can be used immediately after
migration; operators can swap for their preferred catalogue over time.

### D-007 — Fallback retry algorithm

**Decision**: Use exponential backoff with full jitter, computed per
(`retry_count`, `backoff_strategy`) from the fallback policy:

- `fixed`: `base_delay_seconds` between each retry.
- `linear`: `base_delay_seconds * attempt`.
- `exponential` (default): `min(max_delay_seconds, base_delay_seconds
  * 2^attempt) * random(0.5, 1.5)` (full jitter).

After retries are exhausted on the primary, advance to the next chain
entry. The chain is walked without further retries (each chain entry
gets ONE attempt); this keeps total latency bounded.

**Rationale**: Exponential + jitter is industry standard; per-entry
single-attempt on fallback bounds cumulative latency.

### D-008 — Primary-model sticky cache for recovery window

**Decision**: Redis key `router:primary_sticky:{workspace_id}:{model_id}`
stores:

- Value `"use_primary"` (TTL 5 min) — last primary call succeeded.
- Value `"in_fallback"` (TTL 5 min) — last primary call failed.
- Key absent — neutral, try primary.

Router reads the key before dispatch; if `"in_fallback"` AND TTL not
expired, it skips the primary and goes straight to the fallback chain.
On TTL expiry (or successful primary call), the key resets. This
prevents tight-loop retries against an out-of-service primary while
also recovering automatically within 5 minutes of provider recovery.

**Rationale**: Meets FR-019's 5-minute recovery window requirement
without a background health-checker.

### D-009 — Fallback chain validation at create time

**Decision**: On `POST /model-catalog/fallback-policies`:

1. Reject if any `fallback_chain` entry is not an approved catalogue
   entry.
2. Reject if cycles detected (DFS).
3. Reject if any chain entry's `context_window < primary.context_window`.
4. Reject if any chain entry's tier exceeds
   `acceptable_quality_degradation` below primary (e.g.
   `tier_plus_one` permits `tier1 → tier2`, rejects `tier1 → tier3`).

All reject responses include the failing chain index and a structured
error code.

**Rationale**: Catching shape errors at create time prevents surprise
failures at runtime.

### D-010 — Auto-deprecation job

**Decision**: APScheduler job `model_catalog_auto_deprecation` on the
`scheduler` runtime profile. Default interval 1 hour. Queries
`SELECT * FROM model_catalog_entries WHERE status = 'approved' AND
approval_expires_at < now()` and transitions each to `deprecated`;
emits audit chain entry + Kafka event per transition.

**Rationale**: Batch processing keeps it simple; 1-hour latency
between expiry and deprecation is acceptable per SC-006.

### D-011 — Prompt-injection defence layering

**Decision**: Three distinct modules, enabled independently via
workspace-scoped settings:

1. `common/clients/injection_defense/input_sanitizer.py` — consults a
   seeded pattern set + workspace overrides; applies strip / quote /
   reject per policy.
2. `common/clients/injection_defense/system_prompt_hardener.py` —
   injects an explicit delimiter + "treat as data" preamble around
   untrusted text.
3. `common/clients/injection_defense/output_validator.py` — post-call
   scanning; reuses feature 073's debug-logging redaction regex set
   (`common/debug_logging/redaction.py` regex constants) + adds model-
   specific patterns (role-reversal phrasing, exfiltration signals).

Each layer emits telemetry rows. The router wires them in:
input → sanitiser → hardened system prompt → LLM → output validator → caller.

**Rationale**: Clear separation; each layer is independently testable
and tunable; regex reuse from feature 073 avoids duplication.

### D-012 — Trust certification integration

**Decision**: In `trust/services/certification_service.py`, add a
pre-flight check in `request_certification()`:

```python
async def request_certification(self, agent_id):
    agent = await agents_repo.get(agent_id)
    binding = agent.default_model_binding
    card = await model_cards_service.get_by_binding(binding)
    if card is None:
        raise CertificationBlocked(
            reason="model_card_missing",
            detail=f"Model {binding} has no card; certification not permissible (FR-007)",
        )
    ...
```

This is a one-line-of-code addition that satisfies FR-007.

**Rationale**: Small, surgical change; no broader refactor of the trust
BC required.

## Deferred / future

- **Embedding router** for `MEMORY_EMBEDDING_API_URL` /
  `REGISTRY_EMBEDDING_API_URL` call sites — deferred to a follow-up
  feature.
- **Per-step context-window override** (fallback to smaller-context
  model with request-time validation) — deferred; current design
  requires chain-wide context-window monotonicity.
- **Automated model card generation** from vendor APIs — deferred; cards
  are hand-authored by model stewards.
- **Model benchmarks** (eval scores per catalogue entry) — deferred;
  this is evaluation BC territory (UPD-034 / feature 067).
