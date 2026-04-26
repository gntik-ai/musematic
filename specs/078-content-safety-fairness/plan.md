# Implementation Plan: Content Safety and Fairness

**Branch**: `078-content-safety-fairness` | **Date**: 2026-04-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/078-content-safety-fairness/spec.md`

## Summary

Add a content-moderation stage to the existing trust guardrail pipeline; register a new fairness scorer in the existing evaluation scorer registry; gate certification on fairness pass for high-impact agents; reuse feature 076's consent service for first-time AI disclosure (no new consent infrastructure). Provider-agnostic moderation via a `ContentModerator` service with pluggable adapters (OpenAI Moderation, Anthropic safety via the model router, Google Perspective, self-hosted classifier). Per-workspace policies; default fail-closed on provider failure with an explicit fail-open opt-in. All work fits inside the existing `trust/` and `evaluation/` bounded contexts plus three new tables.

## Technical Context

**Language/Version**: Python 3.12+ (control plane). No Go changes.
**Primary Dependencies** (already present): FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic 1.13+, aiokafka 0.11+, redis-py 5.x async, httpx 0.27+, scipy ≥ 1.13 (existing — used by parity calculations), numpy ≥ 1.26 (existing). **Conditionally optional** at deployment time: an installed self-hosted classifier model (HuggingFace Transformers) — only loaded when the workspace selects the `self_hosted` provider; the platform image does NOT bundle the model weights.
**Storage**: PostgreSQL — 3 new tables (`content_moderation_policies`, `content_moderation_events`, `fairness_evaluations`). No new Redis keys (cost cap and threshold-cooldown counters reuse existing notifications counters where applicable). Vault — 1 new path family (`secret/data/trust/moderation-providers/{provider}/{deployment}`).
**Testing**: pytest + pytest-asyncio 8.x. Existing test fixtures for guardrail pipeline + scorer registry are reused.
**Target Platform**: Linux server (control plane), Kubernetes deployment.
**Project Type**: Web service (FastAPI control plane bounded context extension).
**Performance Goals**: Moderation adds ≤ 500 ms p95 to a healthy provider; ≤ 2 s p99 (per-call timeout); cumulative per-execution latency budget ≤ 5 s. Fairness scorer over a 100-case suite completes in < 5 min wall-clock.
**Constraints**: Provider call timeouts MUST be enforced; cost cap MUST prevent runaway spend; consent gating reuses feature 076's HTTP 428 contract verbatim — no parallel consent persistence; group-attribute values MUST never appear in observability labels (rule 22 — low-cardinality only).
**Scale/Scope**: Up to 6 categories per policy; up to 4 providers configurable per workspace (1 primary + 1 fallback + 1 self-hosted floor + 1 per-language pin). Fairness suites up to ~10 000 cases; per-group sample-size minimum 5 (configurable).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Source | Status | Notes |
|---|---|---|---|
| Brownfield rule 1 — never rewrite | Constitution § Brownfield | ✅ Pass | Extends `trust/guardrail_pipeline.py` and `evaluation/scorers/registry.py` with new modules; no file is rewritten wholesale. |
| Brownfield rule 2 — Alembic only | Constitution § Brownfield | ✅ Pass | Single migration `059_content_safety_fairness.py` adds 3 tables. No raw DDL. |
| Brownfield rule 3 — preserve tests | Constitution § Brownfield | ✅ Pass | Existing pre-screener, output_moderation regex, DLP, and scorer-registry tests stay green; new behaviour is gated by per-workspace policy presence. |
| Brownfield rule 4 — use existing patterns | Constitution § Brownfield | ✅ Pass | New files follow `trust/` BC layout (`services/`, `models.py`, `schemas.py`, `events.py`); fairness scorer follows the existing `evaluation/scorers/` layout (Scorer Protocol with `score(...)`). |
| Brownfield rule 5 — cite exact files | Constitution § Brownfield | ✅ Pass | Project Structure below names every file. |
| Brownfield rule 6 — additive enums | Constitution § Brownfield | ✅ Pass | No enum mutations: `GuardrailLayer.output_moderation` already exists (used as the insertion point for the new `ContentModerator` adapters); category and action are stored as VARCHARs / `JSONB` rather than enums to keep the door open for per-deployment extensions. |
| Brownfield rule 7 — backwards-compatible APIs | Constitution § Brownfield | ✅ Pass | Workspaces with no moderation policy see no behaviour change. Existing `/api/v1/guardrail/*` endpoints unchanged. New endpoints under `/api/v1/trust/moderation/*` and `/api/v1/evaluations/fairness/*` are additive. |
| Brownfield rule 8 — feature flags | Constitution § Brownfield | ✅ Pass | New behaviour gated by `FEATURE_CONTENT_MODERATION` (default OFF for existing deployments — already in constitution § Feature Flag Inventory). Fairness scorer always registered but only invoked when an evaluation explicitly references `fairness`. Certification gate gated by per-agent `high_impact_use=true` declaration. |
| Rule 9 — every PII operation audited | Constitution § Domain | ✅ Pass | Group-attribute access on fairness evaluations writes audit-chain entries (rule 9 + FR-031 + FR-037). |
| Rule 10 — vault for credentials | Constitution § Domain | ✅ Pass | Provider API keys (OpenAI, Anthropic, Google Perspective) resolve via `SecretProvider`. Self-hosted classifier needs no credentials. |
| Rule 11 — every LLM call through model_router | Constitution § Domain | ✅ Pass | When the `anthropic_safety` adapter is selected (Anthropic safety model is itself an LLM), the call goes through `common.clients.model_router`, not the Anthropic SDK directly. The `openai_moderation` adapter calls the dedicated moderation endpoint (not chat completion) so it is not an LLM call in the rule's sense; the `google_perspective` and `self_hosted` adapters are not LLM calls. |
| Rule 18 — residency at query time | Constitution § Domain | ✅ Pass | Per-workspace residency rules (feature 076) restrict which provider regions a workspace may dispatch moderation calls to. Adapter selection at runtime checks the workspace's `data_residency_configs` before reaching out. |
| Rule 20 — structured JSON logs | Constitution § Domain | ✅ Pass | All new modules use `structlog`. No `print`. |
| Rule 22 — Loki labels low-cardinality only | Constitution § Domain | ✅ Pass | `category`, `action`, `provider`, `workspace_id` (already a labelled dimension) appear as labels; group-attribute values are placed in JSON payload only — never as labels (rule 22 + FR-031 + SC-013). |
| Rule 23 — secrets never in logs | Constitution § Domain | ✅ Pass | Provider API keys never appear in error_detail or structlog fields. CI gitleaks already covers source. |
| Rule 24 — every BC dashboard | Constitution § Domain | ✅ Pass | Trust BC already has a dashboard; this feature contributes new panels (moderation events per category, action breakdown, provider failure rate, fairness evaluations over time) to the existing trust dashboard. |
| Rule 32 — audit chain on config changes | Constitution § Domain | ✅ Pass | Moderation policy CRUD and fairness-evaluation persistence emit audit-chain entries. |
| Rule 33 — 2PA enforced server-side | Constitution § Domain | ✅ Pass | Material disclosure-text changes that re-prompt all users are flagged as high-impact and require 2PA via the existing privacy compliance path (feature 076). |
| Rule 34 — DLP on outbound | Constitution § Domain | ✅ Pass | DLP runs after moderation in the existing layer order (`output_moderation` precedes `dlp_scan`), so redaction by moderation is preserved as input to DLP. |
| Rule 39 — SecretProvider only | Constitution § Domain | ✅ Pass | Provider credentials resolve via `common.secrets.secret_provider`. No `os.getenv` for `*_API_KEY` outside SecretProvider. |
| Rule 45 — backend has UI | Constitution § Domain | ⚠️ Deferred | Workspace-admin moderation policy CRUD UI lands in UPD-043 (Workspace Owner Workbench). Operator moderation event log + aggregates land in UPD-044 (Creator UIs / extended operator dashboard). Disclosure UI lands as part of UPD-042 (User Notification Center) when applicable. Recorded in Complexity Tracking. |
| Rule 50 — mock LLM for previews | Constitution § Domain | ✅ Pass | Fairness scorer "preview" runs (creator-side dry-run before a real evaluation) default to the mock LLM provider when probability outputs are needed; real-LLM scoring is an explicit opt-in with a cost indicator. |
| Principle I — modular monolith | Constitution § Core | ✅ Pass | All Python work inside `trust/` and `evaluation/` BCs. |
| Principle III — dedicated stores | Constitution § Core | ✅ Pass | PostgreSQL only for relational state; ClickHouse used by analytics for time-series rollups (already in place). |
| Principle IV — no cross-BC table access | Constitution § Core | ✅ Pass | Fairness gate consults the existing `trust/services/certification_service.py` via in-process service interface; consent enforcement uses feature 076's `consent_service` interface; no SQL crosses BC boundaries. |

## Project Structure

### Documentation (this feature)

```text
specs/078-content-safety-fairness/
├── plan.md              # This file
├── spec.md              # Feature spec
├── research.md          # Phase 0 (this command)
├── data-model.md        # Phase 1 (this command)
├── quickstart.md        # Phase 1 (this command)
├── contracts/           # Phase 1 (this command)
│   ├── content-moderator.md
│   ├── moderation-policy-api.md
│   ├── fairness-scorer.md
│   └── certification-fairness-gate.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Created by /speckit-tasks
```

### Source Code (repository root)

```text
apps/control-plane/
├── migrations/versions/
│   └── 059_content_safety_fairness.py                  # NEW (3 tables; rebase to current head at merge time)
└── src/platform/
    ├── trust/
    │   ├── models.py                                   # MODIFIED — add ContentModerationPolicy,
    │   │                                               #   ContentModerationEvent ORM models
    │   ├── schemas.py                                  # MODIFIED — add ModerationPolicy*,
    │   │                                               #   ModerationEvent*, ModerationVerdict schemas
    │   ├── events.py                                   # MODIFIED — add ContentModerationTriggered,
    │   │                                               #   ContentModerationProviderFailed payloads
    │   ├── repository.py                               # MODIFIED — moderation policy + event queries
    │   ├── exceptions.py                               # MODIFIED — add ModerationProviderError,
    │   │                                               #   ModerationPolicyNotFoundError,
    │   │                                               #   ModerationCostCapExceededError
    │   ├── guardrail_pipeline.py                       # MODIFIED — call ContentModerator before the
    │   │                                               #   regex output_moderation as the primary check,
    │   │                                               #   keep regex as the safety floor when no policy
    │   │                                               #   is configured (backwards compat)
    │   ├── services/                                   # NEW SUBDIR (trust/ already has loose files;
    │   │   │                                           #   migrating moderation-related services in)
    │   │   ├── content_moderator.py                    # NEW — ContentModerator orchestrator;
    │   │   │                                           #   provider routing, failure mode, cost cap,
    │   │   │                                           #   per-language pin, allow-list, action selector
    │   │   ├── moderation_providers/                   # NEW — adapter implementations
    │   │   │   ├── base.py                             # NEW — ModerationProvider Protocol
    │   │   │   ├── openai_moderation.py                # NEW
    │   │   │   ├── anthropic_safety.py                 # NEW (calls via model_router)
    │   │   │   ├── google_perspective.py               # NEW
    │   │   │   └── self_hosted_classifier.py           # NEW (HuggingFace; lazy-loaded)
    │   │   └── moderation_action_resolver.py           # NEW — applies block/redact/flag and chooses
    │   │                                               #   safer action on multi-category triggers
    │   ├── routers/                                    # NEW SUBDIR (similar to notifications routers
    │   │   │                                           #   pattern from feature 077)
    │   │   ├── moderation_policies_router.py           # NEW — /api/v1/trust/moderation/policies/*
    │   │   └── moderation_events_router.py             # NEW — /api/v1/trust/moderation/events/*
    │   ├── certification_service.py                    # MODIFIED — add fairness gate for
    │   │                                               #   high-impact agents
    │   └── dependencies.py                             # MODIFIED — wire ContentModerator,
    │                                                   #   ProviderRegistry, fairness gate
    ├── evaluation/
    │   ├── scorers/
    │   │   ├── fairness.py                             # NEW — FairnessScorer Scorer impl
    │   │   ├── fairness_metrics.py                     # NEW — demographic parity, equal opportunity,
    │   │   │                                           #   calibration helper functions (scipy-based)
    │   │   └── registry.py                             # MODIFIED — register `fairness` scorer
    │   ├── models.py                                   # MODIFIED — add FairnessEvaluation ORM model
    │   ├── schemas.py                                  # MODIFIED — add FairnessEvaluation* schemas
    │   ├── service.py                                  # MODIFIED — add `run_fairness_evaluation`,
    │   │                                               #   `get_latest_passing_evaluation` interfaces
    │   ├── router.py                                   # MODIFIED — POST /api/v1/evaluations/fairness/run,
    │   │                                               #   GET /api/v1/evaluations/fairness/runs/{run_id}
    │   ├── repository.py                               # MODIFIED — fairness query helpers
    │   └── events.py                                   # MODIFIED — FairnessEvaluationCompleted payload
    └── common/
        └── config.py                                   # MODIFIED — add ContentModerationSettings
                                                       #   subsection (FEATURE_CONTENT_MODERATION,
                                                       #   provider keys, cost caps, latency budgets,
                                                       #   fairness staleness window)

tests/control-plane/unit/trust/
├── test_content_moderator.py                           # NEW
├── test_moderation_action_resolver.py                  # NEW
├── test_moderation_providers/
│   ├── test_openai_moderation_adapter.py               # NEW
│   ├── test_anthropic_safety_adapter.py                # NEW
│   ├── test_google_perspective_adapter.py              # NEW
│   └── test_self_hosted_classifier_adapter.py          # NEW
└── test_certification_fairness_gate.py                 # NEW

tests/control-plane/unit/evaluation/scorers/
├── test_fairness_scorer.py                             # NEW
└── test_fairness_metrics.py                            # NEW

tests/control-plane/integration/
├── test_guardrail_with_moderation_e2e.py               # NEW
├── test_moderation_policies_api.py                     # NEW
├── test_fairness_evaluation_e2e.py                     # NEW
└── test_certification_blocked_on_fairness.py           # NEW
```

**Structure Decision**: All work fits within the existing `trust/` and `evaluation/` bounded contexts. Two small new subpackages (`trust/services/` and `trust/routers/`) follow the directory pattern introduced by feature 077 in `notifications/` and by `connectors/` earlier — consistent with existing project conventions. No new bounded context. Frontend surfaces are deliberately deferred to UPD-042/043/044 in the audit-pass per rule 45.

## Complexity Tracking

| Item | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| New `trust/services/` subpackage | The trust BC currently has loose top-level files; moderation needs at minimum 8 files (orchestrator + 4 adapters + base protocol + action resolver + future expansion); placing them at the top level of `trust/` would clutter the BC and obscure the architecture. The `services/` subpackage isolates the moderation cluster cleanly. | Putting all moderation files at `trust/` top level: rejected — file-count clutter and unclear boundary. |
| Pluggable provider adapters (4) instead of one provider | Customers have different vendor relationships (OpenAI moderation is free + low-latency; Google Perspective is best-in-class for English toxicity; Anthropic safety integrates with the model router; self-hosted is the on-prem option). Locking to one defeats the purpose. | Single provider: rejected — vendor lock-in is a non-starter for enterprise. |
| `output_moderation` regex layer kept alongside `ContentModerator` | Provides a safety floor for workspaces that have NOT enabled content moderation but still need basic profanity / suicide-keyword blocking. Removing it would regress those deployments. | Replacing regex with `ContentModerator` only: rejected — workspaces without a moderation policy would lose the existing baseline (rule 7 backwards compat). |
| Three new tables (policies, events, evaluations) | Each has a distinct lifecycle: policies are versioned config, events are an append-only audit stream, evaluations are per-(agent, suite) records with their own staleness rules. Conflating them produces a wide table with sparse columns. | Single `trust_safety_records` polymorphic table: rejected — sparse columns + ambiguous query paths. |
| `FairnessEvaluation` lives in `evaluation/` even though gate is in `trust/` | Fairness evaluation is an evaluation activity (run by data scientists with the existing scorer + suite mechanics), not a trust activity. The certification gate consumes the latest passing evaluation via an in-process interface, respecting Principle IV. | Putting `FairnessEvaluation` in `trust/`: rejected — wrong BC ownership; would require trust to own scorer execution. |
| Rule 45 deferred to UPD-042/043/044 | Frontend work is large (workspace-admin policy editor, operator event log + aggregates dashboard, optional disclosure UI), each better placed in its own UPD slot. Backend is independently testable via REST + integration tests. | Building UI in this feature: rejected — would balloon scope from 3 SP to 8+ SP and entangle two separate workbench efforts. |
| Calibration treated as `unsupported` for non-probability agents | Calibration mathematically requires probability outputs; computing it for classification-only outputs would produce meaningless numbers and false signals. | Force calibration always: rejected — would produce meaningless metrics for the majority of agents. |

## Dependencies

- **Existing trust BC** — extended, not replaced. Existing `guardrail_pipeline.py` `output_moderation` regex layer is preserved as a baseline floor.
- **Existing evaluation BC** — extended, not replaced. Existing scorers continue to run; fairness scorer is registered alongside.
- **Privacy compliance / consent (feature 076)** — required for FR-017 to FR-022 disclosure & consent enforcement. Reuses `consent_service.require_or_prompt(user_id, workspace_id)` exactly as defined in `specs/076-privacy-compliance/contracts/consent-service.md`. No new consent persistence introduced by this feature.
- **Audit chain (UPD-024 / `security_compliance/services/audit_chain_service.py`)** — required by rules 9, 32, 37 audit emissions on moderation events, fairness evaluations, policy changes.
- **Model router (feature 075 / `common.clients.model_router`)** — required for the Anthropic safety adapter, which calls an LLM (rule 11). Other adapters do not call LLMs.
- **Vault / SecretProvider (UPD-040 / `common.secrets.secret_provider`)** — required for FR-041 storage of moderation-provider API keys.
- **Notifications (feature 077)** — required for `flag` action delivery to operator channels.
- **DLP & residency (feature 076)** — DLP runs immediately after `output_moderation` in the existing layer order, unchanged. Residency restricts which provider regions a workspace may dispatch to.
- **Existing certification workflow (`trust/certification_service.py`)** — required for FR-032 to FR-036 fairness-gate integration.

## Wave Placement

Wave 5 — same wave as feature 077 (multi-channel notifications). Compatible with later waves; downstream UPD-042/043/044 frontend work depends on it.
