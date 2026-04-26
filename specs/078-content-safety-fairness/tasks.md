# Tasks: Content Safety and Fairness

**Feature**: 078-content-safety-fairness
**Branch**: `078-content-safety-fairness`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

User stories (from spec.md):
- **US1 (P1)** — Workspace admin configures content moderation; agent outputs blocked / redacted / flagged
- **US2 (P1)** — First-time AI disclosure on user interaction (consent gate via feature 076)
- **US3 (P2)** — Evaluator runs fairness scorer with group-aware metrics
- **US4 (P2)** — Trust officer gates certification on fairness for high-impact agents
- **US5 (P3)** — Operator views moderation event log + aggregates

Each user story is independently testable as described in spec.md.

---

## Phase 1: Setup

- [X] T001 Create new submodule directories under `apps/control-plane/src/platform/trust/`: `services/`, `services/moderation_providers/`, `routers/`; add empty `__init__.py` to each
- [X] T002 [P] Add `ContentModerationSettings` extension to `apps/control-plane/src/platform/common/config.py`: `enabled` (bool, default False), `default_per_call_timeout_ms` (int, 2000), `default_per_execution_budget_ms` (int, 5000), `default_monthly_cost_cap_eur` (float, 50.0), `default_fairness_band` (float, 0.10), `default_min_group_size` (int, 5), `default_fairness_staleness_days` (int, 90), `audit_all_evaluations` (bool, False), `self_hosted_model_name` (str, `unitary/multilingual-toxic-xlm-roberta`); wire `FEATURE_CONTENT_MODERATION` env-var bootstrap
- [X] T003 [P] Add canonical category enum and constants to `apps/control-plane/src/platform/trust/services/__init__.py` (or a `constants.py`): `CANONICAL_CATEGORIES = {"toxicity","hate_speech","violence_self_harm","sexually_explicit","pii_leakage"}`; `MODERATION_ACTIONS = {"block","redact","flag"}`; `SAFETY_ORDER = ("block","redact","flag")`; `PROVIDER_FAILURE_ACTIONS = {"fail_closed","fail_open"}`; `TIE_BREAK_RULES = {"max_score","min_score","primary_only"}`

## Phase 2: Foundational (blocks every user story)

- [X] T004 Create Alembic migration `apps/control-plane/migrations/versions/059_content_safety_fairness.py` (rebase to current head at merge): creates `content_moderation_policies`, `content_moderation_events`, `fairness_evaluations` per data-model.md; partial unique index on `(workspace_id) WHERE active=TRUE` for policies; indexes per data-model.md (`idx_moderation_events_workspace_created`, `idx_moderation_events_workspace_agent_created`, `idx_moderation_events_workspace_action` partial WHERE action_taken IN ('block','redact','flag'); `idx_fairness_eval_agent_revision`); CHECK constraints on `default_action`, `provider_failure_action`, `tie_break_rule`, `metric_name`, `fairness_band` range
- [X] T005 [P] Add SQLAlchemy models to `apps/control-plane/src/platform/trust/models.py`: `ContentModerationPolicy`, `ContentModerationEvent` (with relationships to existing `User`, `Workspace`, `AgentProfile` via FK columns; do NOT add cross-BC ORM relationships)
- [X] T006 [P] Add SQLAlchemy model `FairnessEvaluation` to `apps/control-plane/src/platform/evaluation/models.py` (preserves existing models)
- [X] T007 [P] Add Pydantic schemas to `apps/control-plane/src/platform/trust/schemas.py`: `ModerationPolicyCreateRequest`, `ModerationPolicyResponse`, `ModerationPolicyTestRequest`, `ModerationPolicyTestResponse`, `ModerationEventResponse`, `ModerationVerdict`, `ProviderVerdict`, `Category` enum, `ModerationAction` enum, `ModerationProviderName` enum, `TieBreakRule` enum, `ProviderFailureAction` enum, `AgentAllowlistEntry`
- [X] T008 [P] Add Pydantic schemas to `apps/control-plane/src/platform/evaluation/schemas.py`: `FairnessCase`, `FairnessScorerConfig`, `FairnessScorerResult`, `FairnessMetricRow`, `FairnessRunRequest`, `FairnessRunResponse`, `FairnessEvaluationSummary`
- [X] T009 [P] Add domain exceptions to `apps/control-plane/src/platform/trust/exceptions.py`: `ModerationProviderError`, `ModerationProviderTimeoutError`, `ModerationPolicyNotFoundError`, `ModerationCostCapExceededError`, `ResidencyDisallowedProviderError`, `InvalidModerationPolicyError`
- [X] T010 [P] Add domain exceptions to `apps/control-plane/src/platform/evaluation/exceptions.py`: `InsufficientGroupsError`, `FairnessRunFailedError`, `FairnessConfigError`
- [X] T011 Extend `apps/control-plane/src/platform/trust/repository.py` with: `get_active_moderation_policy(workspace_id)`, `list_moderation_policy_versions(workspace_id)`, `create_moderation_policy(...)`, `update_moderation_policy(...)`, `deactivate_moderation_policy(id)`, `get_moderation_policy(id)`, `insert_moderation_event(...)`, `list_moderation_events(filters)`, `aggregate_moderation_events(filters, group_by)`
- [X] T012 Extend `apps/control-plane/src/platform/evaluation/repository.py` with: `insert_fairness_evaluation_rows(rows)`, `get_fairness_evaluation_run(evaluation_run_id)`, `get_latest_passing_fairness_evaluation(agent_id, agent_revision_id, staleness_cutoff)`
- [X] T013 [P] Define `ModerationProvider` Protocol and `ProviderVerdict` dataclass in `apps/control-plane/src/platform/trust/services/moderation_providers/base.py`; signature: `score(text, *, language, categories) -> ProviderVerdict`; document canonical taxonomy mapping responsibility
- [X] T014 [P] Create `ModerationProviderRegistry` in `apps/control-plane/src/platform/trust/services/moderation_providers/__init__.py`: `register(name, provider)`, `get(name)`, `has(name)`, `registered_names()` (mirror existing `ScorerRegistry` pattern)
- [X] T015 Create `ContentModerator` skeleton at `apps/control-plane/src/platform/trust/services/content_moderator.py` with `__init__` (deps: repository, providers, policy_engine, residency_service, secrets, audit_chain, producer, redis, settings) and `moderate_output(*, execution_id, agent_id, workspace_id, original_content, canonical_audit_ref, elapsed_budget_ms)` method stub raising `NotImplementedError` (filled in Phase 3)
- [X] T016 Create `moderation_action_resolver.py` at `apps/control-plane/src/platform/trust/services/moderation_action_resolver.py`: `resolve_action(triggered, policy) -> str` implementing safer-action-wins (block > redact > flag) per D-009; pure function, no I/O
- [X] T017 [P] Add events to `apps/control-plane/src/platform/trust/events.py`: `ContentModerationPolicyChangedPayload`, `ContentModerationTriggeredPayload`, `ContentModerationProviderFailedPayload`, `CertificationFairnessGateBlockedPayload`; reuse `trust.events` topic
- [X] T018 [P] Add events to `apps/control-plane/src/platform/evaluation/events.py`: `FairnessEvaluationCompletedPayload`; reuse `evaluation.events` topic
- [X] T019 Wire dependency-injection providers in `apps/control-plane/src/platform/trust/dependencies.py`: `get_content_moderator`, `get_moderation_provider_registry`, `get_audit_chain_service`, `get_residency_service`, `get_secret_provider`; pre-register all four built-in providers (initially as not-yet-implemented placeholders so the registry contract holds)

---

## Phase 3: User Story 1 — Workspace admin configures content moderation; agent outputs blocked / redacted / flagged (P1) 🎯 MVP

**Story goal**: Workspace admins create a moderation policy; agent outputs that breach thresholds are blocked, redacted, or flagged before delivery; events are persisted for audit.

**Independent test**: Create a policy with `block` on toxicity at threshold 0.8; force a deterministic toxic output; verify (1) the user gets a safe replacement, (2) one moderation event row is persisted, (3) the original content is preserved only in the audit chain, (4) downstream consumers (other agents, webhooks, alerts) do not receive the toxic content. Repeat with `redact` and `flag` to verify per-action behaviour.

- [X] T020 [P] [US1] Add unit tests for `moderation_action_resolver` in `tests/control-plane/unit/trust/test_moderation_action_resolver.py`: single category trivial passthrough; multi-category safer-wins (block over redact, redact over flag); empty triggered list returns `flag` fallback
- [X] T021 [P] [US1] Implement `OpenAIModerationProvider` in `apps/control-plane/src/platform/trust/services/moderation_providers/openai_moderation.py`: direct `httpx` call to `/v1/moderations`; map OpenAI native categories (`harassment`, `hate`, `violence`, `sexual`, `sexual/minors`, `self-harm`) to canonical taxonomy; key resolved via `SecretProvider` from `secret/data/trust/moderation-providers/openai/{deployment}`; respects `per_call_timeout_ms`; returns `ProviderVerdict`; never logs the API key
- [X] T022 [P] [US1] Implement `AnthropicSafetyProvider` in `apps/control-plane/src/platform/trust/services/moderation_providers/anthropic_safety.py`: routes through `common.clients.model_router` (rule 11 — D-005); emits structured-output safety classification; same canonical taxonomy; same secret resolution pattern
- [X] T023 [P] [US1] Implement `GooglePerspectiveProvider` in `apps/control-plane/src/platform/trust/services/moderation_providers/google_perspective.py`: direct `httpx` call to Perspective API; map native attributes (`TOXICITY`, `SEVERE_TOXICITY`, `IDENTITY_ATTACK`, `THREAT`, `SEXUALLY_EXPLICIT`) to canonical taxonomy; key resolution via `SecretProvider`
- [X] T024 [P] [US1] Implement `SelfHostedClassifierProvider` in `apps/control-plane/src/platform/trust/services/moderation_providers/self_hosted_classifier.py`: lazy-load HuggingFace model named in `settings.content_moderation.self_hosted_model_name` (default `unitary/multilingual-toxic-xlm-roberta`); cache the loaded model in module-level state; never bundle the weights with the platform image; fail open with provider_failed event when transformers package missing or model load fails
- [X] T025 [P] [US1] Add unit tests for each provider adapter in `tests/control-plane/unit/trust/test_moderation_providers/test_openai_moderation_adapter.py`, `test_anthropic_safety_adapter.py`, `test_google_perspective_adapter.py`, `test_self_hosted_classifier_adapter.py`: mocked HTTP / model_router responses; canonical taxonomy mapping correctness; timeout enforcement; error → raises `ModerationProviderError` (or `ModerationProviderTimeoutError`); secret material never appears in error messages or structlog fields
- [X] T026 [US1] Fill `ContentModerator.moderate_output()` per `contracts/content-moderator.md` algorithm: load active policy → if none return `deliver_unchanged`; check elapsed budget; resolve provider with language-pin override; pre-flight cost cap (Redis INCRBY `trust:moderation_cost:{ws}:{yyyy-mm}`); pre-flight residency via `residency_service.allow_egress`; provider call with timeout → fallback chain (primary → fallback → self_hosted) → `provider_failure_action`; normalise scores; resolve action (incl. multi-category resolver); apply allow-list overrides; construct `ModerationVerdict`; persist `content_moderation_events` row; emit `monitor.alerts` event for `flag`; return verdict
- [X] T027 [US1] Add unit tests `tests/control-plane/unit/trust/test_content_moderator.py` covering CM1–CM15 from `contracts/content-moderator.md`: no-policy passthrough (CM1); block / redact / flag verdicts (CM2-CM4); fallback chain with primary timeout (CM5-CM6); fail_closed and fail_open paths (CM7-CM8); multi-category safer-wins (CM9); allow-list (CM10); language pin (CM11); cost cap (CM12); residency disallow (CM13); no PII in observability labels (CM14); flag-action `monitor.alerts` exactly once (CM15)
- [X] T028 [US1] Modify `apps/control-plane/src/platform/trust/guardrail_pipeline.py` `output_moderation` layer: when active policy exists for the workspace, call `ContentModerator.moderate_output(...)` BEFORE the existing regex `_OUTPUT_MODERATION_PATTERNS` (regex acts as defence-in-depth floor); when no policy exists, behaviour is identical to today (rule 7 — backwards compat); pipeline downstream continues with whatever payload is produced (block → replacement, redact → redacted, flag → original)
- [X] T029 [US1] Implement workspace-admin policy CRUD router at `apps/control-plane/src/platform/trust/routers/moderation_policies_router.py` per `contracts/moderation-policy-api.md`: POST/GET/PATCH/DELETE `/api/v1/trust/moderation/policies(...)` and `POST .../{id}/test`; enforce `workspace_admin` role gate; cross-workspace 403; validation per data-model.md; mount on app router
- [X] T030 [US1] Wire audit-chain emissions in `routers/moderation_policies_router.py` (rule 32): emit on create/update/deactivate/delete with actor, before/after diff (mask secret refs); emit on `/test` with sample-input hash only (not the input itself)
- [X] T031 [US1] Add unit tests `tests/control-plane/unit/trust/test_moderation_policies_api.py` covering PA1–PA12 from `contracts/moderation-policy-api.md`: role gate; version bump; cross-workspace 403; soft-delete fallback to regex floor; test-mode does not persist event; validation rejects bad inputs; audit emissions on every CRUD
- [X] T032 [US1] Add integration test `tests/control-plane/integration/test_guardrail_with_moderation_e2e.py`: end-to-end through `GuardrailPipelineService.evaluate_full_pipeline` with a configured policy and a fake provider returning toxic scores; verify the verdict propagates correctly; verify the regex floor still runs alongside the new ContentModerator; verify legacy workspaces (no policy) see no behaviour change

**Checkpoint**: US1 deliverable. Workspace admins can configure content moderation; outputs are blocked/redacted/flagged through the ContentModerator; events persisted; audit chain populated; backwards compat preserved for non-configured workspaces.

---

## Phase 4: User Story 2 — First-time AI disclosure on user interaction (P1)

**Story goal**: Users see a non-dismissible AI disclosure on their first agent interaction; subsequent interactions do not re-prompt; material updates re-prompt. Backed by feature 076's consent service via in-process call — no new persistence here.

**Independent test**: As a user with no `ai_interaction` consent record, attempt to start a conversation; verify HTTP 428 with `disclosure_text_ref`; acknowledge consent; verify subsequent attempts succeed; update disclosure with `material=true`; verify re-prompt on next attempt.

- [X] T033 [US2] Insert `consent_service.require_or_prompt(user_id, workspace_id)` call inside `apps/control-plane/src/platform/interactions/service.py` `create_conversation` per feature 076 contract `specs/076-privacy-compliance/contracts/consent-service.md`; on `ConsentRequired` raise `HTTPException(status_code=428, detail={"error":"consent_required","missing_consents":e.missing_types,"disclosure_text_ref":"/api/v1/me/consents/disclosure"})`; place AFTER existing auth/visibility checks and BEFORE any DB write so failed checks do not produce side effects
- [X] T034 [US2] Confirm machine-consumer (A2A / API) path: ensure the same 428 response is produced when a non-UI client invokes the API; structured `disclosure_text_ref` is sufficient for machine consumers (FR-021); verify with an integration assertion that the response body shape matches the consent contract exactly
- [X] T035 [US2] Add a workspace-admin endpoint to update the disclosure text material flag at `/api/v1/trust/disclosure/version` (POST) — mounted on the trust router; payload `{text, material}`; delegates to feature 076's existing disclosure-version repository; emits audit chain entry; gated by `workspace_admin` role
- [X] T036 [US2] Add integration test `tests/control-plane/integration/test_disclosure_first_interaction.py`: clean user with no consent → 428 with correct payload; acknowledge → next call succeeds; revoke (via feature 076 self-service) → next call 428 again; update disclosure with `material=true` → next call 428 for prior-acknowledged user
- [X] T037 [US2] Update `quickstart.md` Q6 + Q7 to confirm the integration matches feature 076's contract verbatim (no platform-side disclosure persistence introduced here)

**Checkpoint**: US2 deliverable. First-time AI disclosure enforced via feature 076's consent service through an explicit `require_or_prompt` call site in `interactions.create_conversation`. No duplicate consent persistence.

---

## Phase 5: User Story 3 — Evaluator runs fairness scorer with group-aware metrics (P2)

**Story goal**: Evaluators run the fairness scorer over a labelled test suite; per-attribute, per-group metrics (demographic parity, equal opportunity, calibration) are computed deterministically; the report identifies passing and failing metrics within the configured fairness band.

**Independent test**: Run the scorer against a 100-case suite with two group attributes (`language=en|es`, `gender=f|m|nb`); verify per-attribute, per-metric rows in `fairness_evaluations` table; verify coverage stats; verify determinism across two re-runs (ε ≤ 0.001).

- [X] T038 [P] [US3] Implement metric helpers in `apps/control-plane/src/platform/evaluation/scorers/fairness_metrics.py`: `demographic_parity(cases, attr, *, predicted_positive_fn, min_group_size) -> tuple[per_group_rate, spread]`; `equal_opportunity(cases, attr, *, positive_class, min_group_size)`; `calibration_brier(cases, attr, *, positive_class, min_group_size)`; raise `InsufficientGroupsError` when fewer than 2 groups; pure NumPy / SciPy with no RNG (D-018)
- [X] T039 [P] [US3] Add unit tests `tests/control-plane/unit/evaluation/scorers/test_fairness_metrics.py`: parametric cases for each metric; deterministic check (re-run produces identical floats); single-group raises; group-below-min-size excluded with coverage report; calibration on classification-only output raises `unsupported`
- [X] T040 [US3] Implement `FairnessScorer` in `apps/control-plane/src/platform/evaluation/scorers/fairness.py`: implements `Scorer` Protocol with stub `score(actual, expected, config)` returning `ScoreResult` carrying `evaluation_run_id`; primary suite-level entry point `score_suite(*, evaluation_run_id, agent_id, agent_revision_id, suite_id, cases, config)` returning `FairnessScorerResult`; iterates configured metrics × attributes, calls helpers, builds rows, emits result
- [X] T041 [US3] Register `fairness` scorer in `apps/control-plane/src/platform/evaluation/scorers/registry.py` `default_scorer_registry.register("fairness", FairnessScorer())`; preserve all existing registrations (rule 4 — established patterns)
- [X] T042 [US3] Add `run_fairness_evaluation(request)` and `get_fairness_run(evaluation_run_id)` to `apps/control-plane/src/platform/evaluation/service.py`: orchestrates scorer invocation; persists per-(metric, attribute) rows via repository; emits `FairnessEvaluationCompletedPayload` on `evaluation.events`; emits audit chain entries for each metric computation (rule 9 — group-attribute access)
- [X] T043 [US3] Add fairness REST endpoints to `apps/control-plane/src/platform/evaluation/router.py`: `POST /api/v1/evaluations/fairness/run` (returns 202 + `evaluation_run_id`; local implementation completes inline with `status="completed"`); `GET /api/v1/evaluations/fairness/runs/{evaluation_run_id}` (returns `FairnessRunResponse`); enforce `evaluator` / `workspace_admin` / `superadmin` role
- [X] T044 [US3] Add unit tests `tests/control-plane/unit/evaluation/scorers/test_fairness_scorer.py` covering FS1–FS10 from `contracts/fairness-scorer.md`: determinism (FS1); missing group attribute handled (FS2); group-below-min excluded (FS3); single group → `insufficient_groups` (FS4); calibration unsupported on classification-only (FS5); pass/fail per band (FS6); group attributes never in structured-log labels (FS7); REST async pattern (FS8); audit chain emissions (FS10)
- [X] T045 [US3] Add integration test `tests/control-plane/integration/test_fairness_evaluation_e2e.py`: build a 100-case suite with synthetic group attributes against a deterministic mock agent; trigger run via REST POST; poll until completed; verify per-row persistence + coverage statistics + deterministic re-run within ε

**Checkpoint**: US3 deliverable.

---

## Phase 6: User Story 4 — Trust officer gates certification on fairness for high-impact agents (P2)

**Story goal**: Certification of agents declared `high_impact_use=true` is blocked unless a recent passing fairness evaluation against the current revision exists; agents not declared high-impact are unaffected.

**Independent test**: Submit certification for high-impact agent without fairness eval → blocked with `fairness_evaluation_required`; run passing fairness eval → certification proceeds. Submit for non-high-impact → unaffected.

- [X] T046 [P] [US4] Add unit tests `tests/control-plane/unit/trust/test_certification_fairness_gate.py` covering CFG1–CFG8 from `contracts/certification-fairness-gate.md`: gate blocks when no eval (CFG1); gate passes within staleness (CFG2); gate blocks when stale (CFG3); non-high-impact bypassed (CFG4); revision change requires fresh eval (CFG5); failed eval treated as no-pass (CFG6); audit emissions per outcome (CFG7); existing PIA/model-card gates still fire alongside (CFG8)
- [X] T047 [US4] Implement `FairnessGateInterface` in `apps/control-plane/src/platform/evaluation/service.py`: `get_latest_passing_evaluation(*, agent_id, agent_revision_id, staleness_days) -> FairnessEvaluationSummary | None` querying `fairness_evaluations` for `overall_passed=True` rows for the exact `agent_revision_id`, ordering by `computed_at DESC`, applying staleness filter
- [X] T048 [US4] Modify `apps/control-plane/src/platform/trust/certification_service.py` `request_certification(agent_id)` to call the new fairness gate AFTER existing model-card / pre-screener / PIA gates: when `revision.declared.high_impact_use` is true, look up latest passing evaluation; raise `CertificationBlocked(reason="fairness_evaluation_required")` when none; raise `CertificationBlocked(reason="fairness_evaluation_stale")` when older than staleness window; emit audit chain entry for every gate firing (passed / required / stale)
- [X] T049 [US4] Add `CertificationBlocked` exception variants if not present (extend existing exception in `trust/exceptions.py`); ensure router maps `CertificationBlocked` to HTTP 409 with structured body `{error:"certification_blocked", reason:"...", detail:"..."}`
- [X] T050 [US4] Add integration test `tests/control-plane/integration/test_certification_blocked_on_fairness.py`: full path through `request_certification` for high-impact agent without eval (409 + reason); run fairness eval that passes; resubmit (proceeds); create new revision (eval no longer satisfies); resubmit (blocks again); fast-forward clock past staleness (blocks with `_stale`)

**Checkpoint**: US4 deliverable.

---

## Phase 7: User Story 5 — Operator views moderation event log + aggregates (P3)

**Story goal**: Workspace admins (own workspace) and platform operators (all workspaces) can list, filter, drill into, and aggregate moderation events for tuning and incident response.

**Independent test**: Generate ~100 events across categories and actions; list filtered by category + action; verify counts; open the aggregate view; verify counts reconcile with raw list.

- [X] T051 [US5] Implement operator event router at `apps/control-plane/src/platform/trust/routers/moderation_events_router.py`: `GET /api/v1/trust/moderation/events` with filters (workspace_id, agent_id, category, action, since, until, limit, cursor); `GET .../{id}` (single, no original content in body — only `audit_chain_ref`); `GET .../aggregate` with `group_by` query param (combinable: `category,agent,action,day`); enforce `workspace_admin` (own workspace only) / `auditor` / `superadmin` roles; cross-workspace 403 with no leakage
- [X] T052 [US5] Add aggregate query helpers to `apps/control-plane/src/platform/trust/repository.py` `aggregate_moderation_events(...)`: SQL-level `GROUP BY` per requested dimension; bounded limit; index-friendly query plan via existing indexes from migration 059
- [X] T053 [US5] Wire audit-chain emission for event-row access in `routers/moderation_events_router.py` (rule 9 — operator viewed PII-adjacent data) on detail GET only (list/aggregate omitted to avoid event flood)
- [X] T054 [US5] Add unit tests `tests/control-plane/unit/trust/test_moderation_events_router.py`: list filters (category, action, time range); cross-workspace 403 (no info leakage); `auditor` cross-workspace allowed; aggregate counts reconcile with raw list; audit emission on detail-fetch only
- [X] T055 [US5] Add Grafana dashboard JSON `deploy/helm/observability/templates/dashboards/trust-content-moderation.json` (rule 24, 27): per-category trigger rate, action breakdown, provider failure rate, fairness evaluations over time; labels limited to low-cardinality dimensions (rule 22 — workspace_id allowed; group attribute values forbidden)

**Checkpoint**: US5 deliverable.

---

## Phase 8: Polish & Cross-Cutting

- [X] T056 [P] Add OpenAPI tags `trust-content-moderation`, `trust-moderation-events`, `evaluation-fairness` and ensure all new routers carry them
- [X] T057 [P] Update `apps/control-plane/src/platform/trust/dependencies.py` final wiring: ensure `ContentModerator`, all 4 provider adapters, action resolver are registered for the api + worker runtime profiles; ensure `evaluation/dependencies.py` exposes `get_fairness_gate` for consumption by `trust/certification_service.py`
- [X] T058 [P] Add receiver-side mock-LLM preview path (rule 50): when fairness scorer config sets `preview=True` and the agent under test would issue LLM calls, route to the platform's mock LLM provider via `model_router` mock mode; document the cost-vs-real-LLM tradeoff in `quickstart.md`
- [X] T059 [P] Smoke-run all 15 quickstart scenarios in `quickstart.md` against a local control-plane; capture any deviations; update behaviour or quickstart accordingly
- [X] T060 [P] Run `ruff check .`, `mypy --strict apps/control-plane/src/platform/trust apps/control-plane/src/platform/evaluation`, and `pytest tests/control-plane/{unit,integration}/{trust,evaluation} -q`; resolve all warnings
- [X] T061 [P] Add a CI gate that scans structured-log capture files for any leakage of group-attribute values, provider API keys, or original (pre-redaction) content (SC-013); fails the build on any finding
- [X] T062 Update `CLAUDE.md` Recent Changes section to surface this feature; verify the auto-generated entry from `update-agent-context.sh` is accurate

---

## Dependencies

```
Phase 1 (Setup) ──▶ Phase 2 (Foundational) ──▶ Phase 3 (US1, P1) ──▶ Checkpoint MVP
                                              ──▶ Phase 4 (US2, P1) ──▶ Checkpoint MVP
                                                          │
                                                          ▼
                                              ┌─────────────────────┐
                                              │ Phase 5 US3 (P2)    │ — independent
                                              │ Phase 6 US4 (P2)    │ — depends on US3 fairness scorer
                                              │ Phase 7 US5 (P3)    │ — depends on US1 events
                                              └─────────────────────┘
                                                          │
                                                          ▼
                                                 Phase 8 (Polish)
```

**MVP scope**: Phase 1 + Phase 2 + Phase 3 + Phase 4 = 32 tasks. Delivers content moderation enforcement (US1) and first-time AI disclosure (US2). Fairness scorer, certification gate, and operator log come in subsequent waves.

**Parallel opportunities**:
- Phase 1: T002 ∥ T003 (different config sections).
- Phase 2: T005 ∥ T006 ∥ T007 ∥ T008 ∥ T009 ∥ T010 ∥ T013 ∥ T014 ∥ T017 ∥ T018 (independent files); T011 and T012 sequential after their respective models land.
- Phase 3: T020 ∥ T021 ∥ T022 ∥ T023 ∥ T024 ∥ T025 (provider adapters + their tests); T026 (orchestrator) sequential after providers; T027 (orchestrator tests) parallel to T028 (pipeline integration); T029 / T030 / T031 parallel to T032.
- Phase 5: T038 ∥ T039 (helpers + their tests); T040 sequential; T041 trivial; T042 / T043 / T044 / T045 parallel.
- Phase 6: T046 (tests) parallel to T047–T049 implementation; T050 sequential.
- Phase 7: T051 / T052 / T053 / T054 / T055 — most are parallel once T051 router skeleton lands.
- Phase 8: T056 ∥ T057 ∥ T058 ∥ T059 ∥ T060 ∥ T061 (independent surfaces).

---

## Implementation strategy

1. **Wave A (MVP)** — Phases 1, 2, 3, 4. Two devs in parallel: dev A on Phase 3 (US1 — content moderator + 4 providers + policy CRUD + pipeline integration), dev B on Phase 4 (US2 — disclosure call site + admin disclosure-version endpoint + integration test). Joint smoke-run in Phase 4.
2. **Wave B (P2 expansion)** — Phases 5 and 6. Phase 5 (US3 fairness scorer) ships first; Phase 6 (US4 certification gate) consumes it. Single dev can do both sequentially or two devs with a clean handoff after T044.
3. **Wave C (P3)** — Phase 7 (US5 operator log + aggregates) — solo dev work; depends only on Phase 3 events being present.
4. **Wave D (Polish)** — Phase 8: dashboard, OpenAPI tags, lint/types/tests gate, CI label-leak scanner, smoke-run quickstart.

**Constitution coverage matrix**:

| Rule | Where applied | Tasks |
|---|---|---|
| 1, 4, 5 (brownfield) | All phases — extends `trust/`, `evaluation/`; exact files cited | T015, T028, T040, T041, T048 |
| 2 (Alembic) | Phase 2 | T004 |
| 6 (additive enums) | Phase 2 | T003 (no enum mutation; uses VARCHAR + check constraints) |
| 7 (backwards compat), 8 (feature flag) | Phase 1, 3 | T002, T028 |
| 9 (PII audit) | US3, US5 | T042 (group attribute access), T053 (event row inspection) |
| 10, 39 (Vault, SecretProvider) | Phase 3 | T021, T022, T023 |
| 11 (LLM through model_router) | US1 | T022 (Anthropic safety routes through model_router) |
| 18 (residency at query time) | US1 | T026 (residency.allow_egress check before each provider call) |
| 22 (low-cardinality labels) | US3 | T040 (group attributes in JSON only); T061 (CI scanner) |
| 23 (no secrets in logs) | All adapters | T021–T024, T030, T061 |
| 24, 27 (BC dashboard via Helm) | Phase 7 | T055 |
| 32 (audit chain on config) | US1, US3, US4 | T030, T042, T048 |
| 33 (2PA enforced server-side) | Phase 4 | Disclosure material-flag updates flow through feature 076's existing 2PA path (T035) |
| 34 (DLP outbound) | US1 — preserved layer order | T028 (output_moderation precedes dlp_scan; verified in integration test T032) |
| 37 (events to audit) | US1, US3, US4 | T030, T042, T048 |
| 39 (SecretProvider) | Phase 3 | T021–T024 |
| 44 (rotation does not echo) | Out of scope (no rotation surface in this feature) | n/a |
| 45 (backend has UI) | Deferred to UPD-042/043/044. Recorded in plan.md Complexity Tracking. |
| 46 (self-service current_user) | Phase 4 | Reuses feature 076's `/api/v1/me/consents/*` self-service endpoints; this feature adds NO `/me/*` surface for moderation/fairness (workspace-admin and operator only) |
| 47 (workspace vs platform scope) | US1, US5 | T029, T051 |
| 50 (mock LLM previews) | Phase 8 | T058 |

---

## Format validation

All 62 tasks above use the required format `- [ ] T### [P?] [Story?] Description with file path`. Every task identifies an exact path under `apps/control-plane/src/platform/{trust,evaluation,interactions,common}/` or `apps/control-plane/migrations/versions/` or `tests/control-plane/{unit,integration}/{trust,evaluation}/` so an LLM can complete each task without further context.
