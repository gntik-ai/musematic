# Implementation Plan: Model Catalog and Fallback

**Branch**: `075-model-catalog-fallback` | **Date**: 2026-04-23 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/075-model-catalog-fallback/spec.md`

## Summary

Create the `model_catalog/` bounded context with four new tables and an
admin REST surface; ship `common/clients/model_router.py` as the single
dispatch point for all LLM calls with binding validation, fallback
orchestration, per-workspace credential resolution via Vault, and
three-layer prompt-injection defence; migrate the two existing direct
LLM call sites (`composition/llm/client.py`,
`evaluation/scorers/llm_judge.py`) to route through the new router.
Integrate with `trust/services/certification_service.py` to block
certification when the bound model has no card. One Alembic migration
(059) seeds six approved models on day one.

## Technical Context

**Language/Version**: Python 3.12+ (control plane). No Go changes —
the reasoning-engine satellite already delegates LLM calls via gRPC.
**Primary Dependencies**:
- FastAPI 0.115+, SQLAlchemy 2.x async, Pydantic v2, aiokafka 0.11+,
  APScheduler 3.x (all existing)
- `httpx 0.27+` (existing; both current LLM call sites use it)
- UPD-024's `RotatableSecretProvider` for provider credential resolution
  (env-var fallback acceptable during UPD-024's rollout)
- No new third-party libraries
**Storage**:
- **PostgreSQL** — 4 new tables via Alembic migration 059
  (`model_catalog_entries`, `model_cards`, `model_fallback_policies`,
  `model_provider_credentials`) + 1 new configuration table for
  prompt-injection pattern sets (`injection_defense_patterns`)
- **Redis** — `router:primary_sticky:{workspace_id}:{model_id}` (sticky
  recovery cache, 5 min TTL)
- **Kafka** — 4 new topics per constitution §7:
  `model.catalog.updated`, `model.card.published`,
  `model.fallback.triggered`, `model.deprecated`
- **Vault** — `secret/data/musematic/{env}/providers/{workspace_id}/
  {provider}` for per-workspace API keys (via UPD-024's
  `RotatableSecretProvider`)
**Testing**: pytest + pytest-asyncio; mock provider failures via
`respx` (new dev dep — already installed for other integration tests).
CI coverage gate ≥ 95%.
**Target Platform**: Linux (K8s / Docker / local native).
**Project Type**: One new bounded context + one new common client
module + 2 call-site migrations.
**Performance Goals**:
- Router dispatch adds ≤ 5 ms overhead above the raw provider call
  (catalogue validation + credential resolution cached).
- Fallback triggers within 1 s of primary's failed retry budget exhaust.
- Auto-deprecation job processes 1,000 expired entries in ≤ 10 s.
**Constraints**:
- Router must be fail-closed on catalogue lookup failure (no silent
  bypass).
- Provider credentials never appear in logs (rule 40).
- Rotation response never echoes the new secret (rule 44).
- 100% of LLM calls from business logic go through the router (rule 11);
  a CI static-analysis check enforces no direct `httpx` calls to
  `/chat/completions` outside `common/clients/` and `model_router.py`.
**Scale/Scope**:
- 4 new tables + 1 injection-pattern config table, 1 Alembic migration,
  1 new BC, 4 new Kafka topics, 1 new Redis key pattern.
- ~15 new REST endpoints under `/api/v1/model-catalog/*`.
- 2 existing call sites migrated.
- 6 seed catalogue entries; ≥ 20 seed injection patterns.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*
Evaluated against `.specify/memory/constitution.md` at v1.3.0.

| Gate | Status | Notes |
|------|--------|-------|
| **Principle I** — Modular monolith | ✅ PASS | Single new BC; router module under `common/clients/`. |
| **Principle III** — Dedicated data stores | ✅ PASS | Postgres + Redis + Kafka + Vault per their charters. |
| **Principle IV** — No cross-boundary DB access | ✅ PASS | `model_catalog/` owns its tables; `trust/` reads via in-process service interface only. |
| **Principle VI** — Policy machine-enforced | ✅ PASS | Binding validation runs at dispatch time; no markdown drives enforcement. |
| **Brownfield Rule 1** — Never rewrite | ✅ PASS | Existing `LLMCompositionClient` + `LLMJudgeScorer` keep public API; internals delegate to router. |
| **Brownfield Rule 2** — Alembic migration | ✅ PASS | Migration 059. |
| **Brownfield Rule 3** — Preserve existing tests | ✅ PASS | Net-additive. |
| **Brownfield Rule 4** — Use existing patterns | ✅ PASS | FastAPI router + SQLAlchemy mixins + APScheduler worker + `publish_*_event`. |
| **Brownfield Rule 7** — Backward-compatible APIs | ✅ PASS | New endpoints are additive; existing public classes retain signatures. |
| **Brownfield Rule 8** — Feature flags | ✅ PASS | `FEATURE_MODEL_ROUTER_ENABLED` gates the rollout per workspace. |
| **Rule 9** — PII audit chain entries | ✅ PASS | Catalogue transitions, fallback events, credential rotations all write audit chain via UPD-024's `AuditChainService`. |
| **Rule 10** — Every credential through vault | ✅ PASS — **load-bearing** | `model_provider_credentials` stores Vault paths only; raw keys never in DB. |
| **Rule 11** — Every LLM call through model router | ✅ PASS — **load-bearing** | This feature implements the rule; CI static-analysis check enforces no direct provider calls from business logic. |
| **Rule 29** — Admin endpoints segregated | ✅ PASS | All mutating endpoints under `/api/v1/model-catalog/` tagged `admin`. |
| **Rule 30** — Admin endpoints declare role gate | ✅ PASS | Every mutating method depends on `require_admin` / `require_superadmin`. |
| **Rule 37** — Env vars auto-documented | ✅ PASS | `Field(description=...)` on every new setting. |
| **Rule 39** — Every secret via SecretProvider | ✅ PASS — **load-bearing** | Router reads keys via `RotatableSecretProvider`; no direct `os.getenv`. |
| **Rule 40** — Provider secret never in logs | ✅ PASS | Router logging redacts `Authorization` header; CI check enforces (bandit-style rule). |
| **Rule 41** — Vault failure doesn't bypass auth | ✅ PASS | Vault outage → credential resolution fails → call fails fast; no hardcoded key fallback at runtime. |
| **Rule 44** — Rotation response never echoes secret | ✅ PASS | Rotation delegates to UPD-024's pattern. |
| **AD-19** — Provider-agnostic model routing | ✅ PASS — **load-bearing** | This feature implements AD-19. |

**No violations.**

## Project Structure

### Documentation (this feature)

```text
specs/075-model-catalog-fallback/
├── plan.md                          ✅ This file
├── spec.md                          ✅ 6 user stories, 29 FRs, 10 SC
├── research.md                      ✅ 12 decisions
├── data-model.md                    ✅ 5 tables + Redis + Kafka + Vault
├── quickstart.md                    ✅ 6 walkthroughs
├── contracts/
│   ├── model-router.md              ✅ Router API + fallback semantics
│   ├── catalog-admin.md             ✅ Catalogue CRUD + lifecycle
│   ├── model-cards.md               ✅ Card attach + material-change semantics
│   ├── credentials-rotation.md      ✅ Per-workspace credential + UPD-024 integration
│   └── prompt-injection-defense.md  ✅ Three-layer pipeline + telemetry
└── checklists/
    └── requirements.md              ✅ Spec validation (all pass)
```

### Source Code (extending `apps/control-plane/`)

```text
apps/control-plane/src/platform/
├── model_catalog/                                  # NEW BC
│   ├── __init__.py
│   ├── models.py                                   # 4 tables
│   ├── schemas.py
│   ├── repository.py
│   ├── events.py                                   # 4 Kafka topics
│   ├── router.py                                   # /api/v1/model-catalog/* (admin)
│   ├── exceptions.py
│   ├── services/
│   │   ├── catalog_service.py                      # approval lifecycle
│   │   ├── model_card_service.py                   # card CRUD + material-change detection
│   │   ├── fallback_service.py                     # chain resolution + validation
│   │   └── credential_service.py                   # per-workspace credential mgmt
│   └── workers/
│       └── auto_deprecation_scanner.py             # APScheduler job
├── common/
│   ├── clients/
│   │   ├── model_router.py                         # NEW — ModelRouter class
│   │   ├── model_provider_http.py                  # NEW — thin OpenAI-compatible HTTP adapter
│   │   └── injection_defense/
│   │       ├── __init__.py                         # NEW
│   │       ├── input_sanitizer.py                  # NEW
│   │       ├── system_prompt_hardener.py           # NEW
│   │       └── output_validator.py                 # NEW — reuses debug_logging/redaction.py regexes
│   └── config.py                                   # EXTEND — ModelCatalogSettings
├── composition/
│   └── llm/client.py                               # MIGRATE — LLMCompositionClient delegates to ModelRouter
├── evaluation/
│   └── scorers/llm_judge.py                        # MIGRATE — _judge_once_provider delegates to ModelRouter
├── trust/
│   └── services/certification_service.py           # EXTEND — block cert when no model card
├── workflow/
│   └── services/executor.py                        # no-op if LLM dispatch already delegates via composition; add a defence-in-depth check
└── migrations/versions/
    └── 059_model_catalog.py                        # 5 tables + seed data

.github/workflows/
└── ci.yml                                          # MODIFY — add "no direct LLM calls" static-analysis check
```

### Key Architectural Boundaries

- **Router is the single LLM dispatch choke point.** Every LLM call in
  business logic goes through `ModelRouter.complete(...)` — no direct
  `httpx` calls to `/chat/completions` anywhere outside
  `common/clients/model_router.py`. CI enforces.
- **`model_catalog/` owns its tables.** `trust/` reads via
  `model_card_service.get_by_binding()` — no cross-BC DB access.
- **Credentials are resolved per-call.** The router calls
  `RotatableSecretProvider.get_current(f"providers/{ws_id}/{provider}")`
  on every dispatch; the provider caches for 60s (UPD-024 pattern), so
  hot-path latency is minimal.
- **Injection-defence layers are independent modules.** Each is
  configurable per-workspace; can be enabled/disabled without affecting
  the others.

## Complexity Tracking

No constitution violations. Highest-risk areas:

1. **Router hot-path latency.** Adding catalogue + credential lookups to
   every LLM call risks latency inflation. Mitigation: in-process LRU
   cache for catalogue entries (60s TTL); Redis-backed credential cache
   (60s TTL from UPD-024's provider); both reads are sub-ms. Budget ≤
   5 ms p99 overhead.
2. **Silent fallback degrading quality.** A tier-1 primary failing
   over to a tier-3 fallback could degrade quality invisibly.
   Mitigation: `acceptable_quality_degradation` bound enforced at
   policy-create time (D-009) and at chain-walk time; tier-3 fallback
   requires explicit policy configuration and emits a warning event.
3. **Catalogue staleness vs provider reality.** A model could be
   removed by the provider before its catalogue expiry. Mitigation:
   the router propagates provider 404 / model-not-found errors as a
   structured "catalogue_entry_stale" error that operators see in the
   dashboard; auto-deprecation does not run on provider responses
   (only on calendar expiry).
4. **Feature-flag rollout gaps.** During the cutover, some code paths
   may still hit the old direct-httpx flow. Mitigation: the flag is
   per-workspace so rollout can be staged; the CI static-analysis check
   fails the build on any new direct LLM call sites added after the
   migration date (PR-time enforcement).
5. **Prompt-injection pattern false positives.** Over-aggressive
   pattern-matching could strip legitimate content. Mitigation:
   seeded patterns are conservative; operators tune per workspace;
   each layer emits telemetry so false-positive rates are measurable;
   defaults can be loosened without a code deploy.
6. **Vault credential resolution failure on every LLM call.**
   Vault outage would kill all LLM calls. Mitigation: UPD-024's
   `RotatableSecretProvider` already caches with a short TTL; router
   caches the resolved value for the call's duration; a 5-second stale
   window after Vault outage is acceptable (constitution rule 41 —
   fail closed, not silently bypass, but do allow short cache windows).

## Phase 0: Research

**Status**: ✅ Complete — see [research.md](research.md).

12 decisions (D-001 through D-012) cover router scope (only 2 migration
sites), router surface, existing call-site migration approach, credential
resolution split (URL + header), migration numbering, seed catalogue,
fallback retry algorithm, primary-sticky Redis cache for recovery window,
fallback chain validation rules, auto-deprecation APScheduler job,
prompt-injection defence layering, and trust certification integration.

## Phase 1: Design & Contracts

**Status**: ✅ Complete.

- [data-model.md](data-model.md) — 5 Postgres tables (4 per spec DDL +
  1 `injection_defense_patterns`), Redis key schema, Kafka topics,
  Vault path scheme, seed data.
- [contracts/model-router.md](contracts/model-router.md) — Router API
  signature, resolution order, telemetry, fail-modes.
- [contracts/catalog-admin.md](contracts/catalog-admin.md) — catalogue
  CRUD + status transitions + auto-deprecation.
- [contracts/model-cards.md](contracts/model-cards.md) — card attach +
  material-change detection + trust-service integration.
- [contracts/credentials-rotation.md](contracts/credentials-rotation.md)
  — per-workspace credential + UPD-024 rotation delegation.
- [contracts/prompt-injection-defense.md](contracts/prompt-injection-defense.md)
  — three-layer pipeline + pattern config + telemetry.
- [quickstart.md](quickstart.md) — six walkthroughs Q1–Q6.

## Phase 2: Tasks

**Status**: ⏳ Deferred to `/speckit.tasks`.
