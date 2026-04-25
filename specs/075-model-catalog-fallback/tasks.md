# Tasks: Model Catalog and Fallback

**Input**: Design documents from `/specs/075-model-catalog-fallback/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: Required (CI coverage gate ≥ 95%); every contract lists named test IDs (MR1–MR9, CA1–CA7, MC1–MC6, CR1–CR7, PI1–PI7) that are generated as explicit tasks.

**Organization**: Tasks are grouped by user story. US1 (catalogue) ships before US2 + US3 because binding validation and fallback depend on the catalogue service being operational. US1 + US2 + US3 are all P1 and form the MVP.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story label [US1]–[US6]

---

## Phase 1: Setup

**Purpose**: Scaffold BC directory + new common/client module structure.

- [X] T001 Create bounded-context directory `apps/control-plane/src/platform/model_catalog/` with `__init__.py`, empty `models.py`, `schemas.py`, `repository.py`, `events.py`, `router.py`, `exceptions.py`, plus `services/` and `workers/` subdirectories each with `__init__.py`.
- [X] T002 [P] Create `apps/control-plane/src/platform/common/clients/injection_defense/` directory with `__init__.py`, empty `input_sanitizer.py`, `system_prompt_hardener.py`, `output_validator.py`. Also create empty `apps/control-plane/src/platform/common/clients/model_router.py` and `apps/control-plane/src/platform/common/clients/model_provider_http.py`.
- [X] T003 [P] Install `respx` as a dev dependency in `apps/control-plane/pyproject.toml` `[dev]` extras (used by test tasks to mock provider HTTP failures). Confirm `cryptography` and `httpx` are already present (they are).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Alembic migration 059, config extensions, event registry, and the model router skeleton that US2, US3, and US6 all consume.

**⚠️ CRITICAL**: No user story can fully land until Phase 2 completes.

- [X] T004 Write Alembic migration `apps/control-plane/migrations/versions/059_model_catalog.py` creating all 5 tables per `data-model.md` §1 (`model_catalog_entries`, `model_cards`, `model_fallback_policies`, `model_provider_credentials`, `injection_defense_patterns`). Seed 6 catalogue entries (openai:gpt-4o, openai:gpt-4o-mini, anthropic:claude-opus-4-6, anthropic:claude-sonnet-4-6, anthropic:claude-haiku-4-5, google:gemini-2.0-pro) per research.md D-006 and ≥ 20 injection patterns per D-011. Split into `_create_*` and `_seed_*` functions for reviewability.
- [X] T005 [P] Extend `apps/control-plane/src/platform/common/config.py` with `ModelCatalogSettings` (fields: `router_enabled: bool = False`, `auto_deprecation_interval_seconds: int = 3600`, `default_recovery_window_seconds: int = 300`, `router_primary_timeout_seconds: float = 25.0`, per-provider `openai_base_url`, `anthropic_base_url`, `google_base_url`, `mistral_base_url`). Attach as `PlatformSettings.model_catalog`. `Field(description=...)` on every field (rule 37).
- [X] T006 [P] Register 4 new Kafka topics in `apps/control-plane/src/platform/model_catalog/events.py` following the `auth/events.py:publish_auth_event` pattern: `model.catalog.updated`, `model.card.published`, `model.fallback.triggered`, `model.deprecated`. Each with a typed Pydantic payload + `publish_*_event` helper + `event_registry.register(...)` call.
- [X] T007 [P] Implement all 5 SQLAlchemy models in `apps/control-plane/src/platform/model_catalog/models.py` per `data-model.md` §1.1–§1.5: `ModelCatalogEntry`, `ModelCard`, `ModelFallbackPolicy`, `ModelProviderCredential`, `InjectionDefensePattern`. Include all check constraints + unique constraints + indexes.
- [X] T008 [P] Implement `apps/control-plane/src/platform/model_catalog/repository.py` with async methods for every entity: `get_entry_by_provider_model`, `list_entries`, `get_card_by_entry_id`, `get_fallback_policy_for_scope`, `get_credential_by_workspace_provider`, `list_injection_patterns_for_layer`. All read methods cache-friendly (no side effects).
- [X] T009 Implement `apps/control-plane/src/platform/common/clients/model_provider_http.py`: a thin OpenAI-compatible HTTP adapter exposing `async def call(base_url, api_key, model_id, messages, response_format, timeout) -> ProviderResponse`. Raises typed exceptions: `ProviderOutage` (5xx), `ProviderTimeout`, `RateLimitedError` (429), `ProviderAuthError` (401/403). Replaces the inline `httpx.AsyncClient` usage from `composition/llm/client.py` lines 45–50.

**Checkpoint**: Migration applied; models + repository + HTTP adapter in place; Kafka topics registered. User stories can begin.

---

## Phase 3: User Story 1 — Model Steward Curates the Catalogue (Priority: P1) 🎯 MVP

**Goal**: Stewards create, approve, deprecate, and block catalogue entries. Auto-deprecation job handles calendar expiry.

**Independent Test**: Add a catalog entry → returns with `approved` status; block it → verify agent bindings to it fail on next dispatch; wait past `approval_expires_at` → auto-deprecation job transitions to `deprecated`.

### Tests for User Story 1

- [X] T010 [P] [US1] Unit tests CA1–CA7 in `apps/control-plane/tests/unit/model_catalog/test_catalog_service.py` per `contracts/catalog-admin.md`: create, duplicate rejection, block, auto-deprecation, fallback-cycle rejection, tier degradation rejection, reapprove.

### Implementation for User Story 1

- [X] T011 [P] [US1] Pydantic schemas in `apps/control-plane/src/platform/model_catalog/schemas.py` for catalogue CRUD + status-transition endpoints: `CatalogEntryCreate`, `CatalogEntryResponse`, `CatalogEntryPatch`, `BlockRequest`, `ReapproveRequest`, `ModelCardFields`, `FallbackPolicyCreate`, etc.
- [X] T012 [US1] Implement `CatalogService` in `apps/control-plane/src/platform/model_catalog/services/catalog_service.py`: `create_entry`, `list_entries`, `get_entry`, `update_entry`, `transition_status` (with validation per `contracts/catalog-admin.md`). Every status transition writes an `AuditChainEntry` (UPD-024) and emits `model.catalog.updated`.
- [X] T013 [US1] Implement `FallbackPolicyService` in `apps/control-plane/src/platform/model_catalog/services/fallback_service.py`: `create_policy` (enforcing all chain-validation rules from `contracts/catalog-admin.md` — cycle detection, context-window monotonicity, tier degradation bound), `resolve_policy_for_scope(workspace_id, agent_id, primary_model_id)`, `list_policies`, `update_policy`, `delete_policy`.
- [X] T014 [US1] Implement admin router in `apps/control-plane/src/platform/model_catalog/router.py` with all catalogue + fallback-policy endpoints per `contracts/catalog-admin.md`. Every mutating method depends on `require_admin`/`require_superadmin`; reapprove requires `require_superadmin` (stricter). Tag routes `['admin', 'model-catalog']`.
- [X] T015 [US1] Implement `auto_deprecation_scanner.py` worker in `apps/control-plane/src/platform/model_catalog/workers/`: APScheduler job (default 1 h cadence) that transitions expired entries to `deprecated`, writes audit chain entries, and emits `model.deprecated` Kafka events. Register in `main.py` under the `scheduler` runtime profile.
- [X] T016 [US1] Register the model_catalog router in `apps/control-plane/src/platform/main.py` alongside existing routers; confirm tagging picks up feature 073's admin OpenAPI filter.

**Checkpoint**: US1 complete. Stewards can curate; auto-deprecation runs; status changes flow through audit chain + Kafka.

---

## Phase 4: User Story 2 — Agent Binding + Runtime Validation (Priority: P1)

**Goal**: Agent creators bind agents to approved models; the router validates at dispatch; 2 existing LLM call sites migrate to route through the new `ModelRouter`.

**Independent Test**: Bind test agent → execute → verify uses bound model. Block model → execute → verify fails fast. Attempt to bind to unapproved model → verify rejected with suggested alternatives.

### Tests for User Story 2

- [X] T017 [P] [US2] Unit tests MR1–MR9 in `apps/control-plane/tests/unit/model_catalog/test_model_router.py` per `contracts/model-router.md`: happy path, blocked, deprecated warning, fallback triggered (covered by US3), sticky cache, credential resolution, rotation overlap, 2 migration sites delegating.
- [X] T018 [P] [US2] Integration test in `apps/control-plane/tests/integration/model_catalog/test_binding_validation.py`: drive a real execution against each catalogue-entry status (`approved` → succeeds, `deprecated` → succeeds + warning, `blocked` → fails); attempt to bind agent to unapproved model → rejected.

### Implementation for User Story 2

- [X] T019 [P] [US2] Implement `ModelRouter` class in `apps/control-plane/src/platform/common/clients/model_router.py` per `contracts/model-router.md` per-call algorithm: binding resolution, catalogue validation (in-process LRU cache, 60 s TTL), fallback policy lookup, credential resolution via `RotatableSecretProvider` (UPD-024), primary dispatch with retries, fallback chain walk, telemetry emission. Depends on T007, T008, T009.
- [X] T020 [US2] Extend `apps/control-plane/src/platform/registry/models.py` `AgentProfile` with a `default_model_binding VARCHAR(128)` column. Migration 059 (T004) MUST include `op.add_column(...)` for this. Confirm back-compat: existing agents land with NULL → the router raises `InvalidBindingError` with a clear message pointing at the admin endpoint to set one.
- [X] T021 [US2] Migrate `apps/control-plane/src/platform/composition/llm/client.py` `LLMCompositionClient.generate()`: replace the inline `httpx` call + retry loop with `await model_router.complete(...)`. Keep the public method signature unchanged (backwards-compat). Gated by `FEATURE_MODEL_ROUTER_ENABLED` — when `false`, the old path remains for rollback safety.
- [X] T022 [US2] Migrate `apps/control-plane/src/platform/evaluation/scorers/llm_judge.py` `LLMJudgeScorer._judge_once_provider()` similarly. Same feature-flag gate.
- [X] T023 [US2] Extend `apps/control-plane/src/platform/registry/router.py` `PATCH /agents/{id}` to accept `default_model_binding` as an optional field; on set, the handler validates the binding against the catalogue (status != `blocked`) OR returns a 400 with the 3 closest approved alternatives by capability (computed by a simple text-similarity match on purpose + tier match).
- [X] T024 [US2] Add a CI static-analysis check (new script `ci/lint_llm_calls.py` + CI step in `.github/workflows/ci.yml`) that greps the Python codebase for direct `httpx` calls to `/v1/chat/completions` or `/v1/messages` outside `common/clients/model_router.py` + `common/clients/model_provider_http.py` + pre-migration paths. Fails the build on any new hit. Enforces constitution rule 11.

**Checkpoint**: US2 complete. Two existing LLM call sites migrated; runtime validation enforced; CI gate protects against regressions.

---

## Phase 5: User Story 3 — Automatic Fallback on Provider Failure (Priority: P1)

**Goal**: Configured fallback policies trigger on primary failure with structured audit record; recovery window reverts to primary automatically.

**Independent Test**: Configure policy, inject provider 5xx failure via test hook, drive execution, verify fallback triggers and records structured audit.

### Tests for User Story 3

- [X] T025 [P] [US3] Unit test in `apps/control-plane/tests/unit/model_catalog/test_fallback.py`: primary succeeds (no fallback), primary 5xx → fallback[0] succeeds, primary + fallback[0] fail → fallback[1] succeeds, all fail → `FallbackExhaustedError` with per-tier failure list.
- [X] T026 [P] [US3] Integration test `test_fallback_e2e.py` using `respx` to mock provider responses: verify the `model.fallback.triggered` Kafka event payload matches `contracts/model-router.md` shape; verify `fallback_taken` field on `ModelRouterResponse` is populated.
- [X] T027 [P] [US3] Integration test `test_sticky_cache.py`: after a fallback, next call within 5 min skips primary (Redis sticky key honored); after 5 min TTL expiry, primary is retried.

### Implementation for User Story 3

- [X] T028 [US3] Extend `ModelRouter._call_chain` method (added to T019) with the fallback loop: for each chain entry in order, call `_call_provider` with ONE attempt; on failure, advance; on all-fail, raise `FallbackExhaustedError`. Per research.md D-007, each chain entry gets a single attempt (no per-entry retries), bounding total latency.
- [X] T029 [US3] Implement the sticky-cache logic in `ModelRouter`: Redis key `router:primary_sticky:{workspace_id}:{model_id}` with TTL = policy's `recovery_window_seconds`; on primary success → `use_primary`; on primary failure → `in_fallback`. Reads happen before primary dispatch (per-call algorithm step 4 in `contracts/model-router.md`).
- [X] T030 [US3] Emit `model.fallback.triggered` Kafka event with the payload shape from `contracts/model-router.md` on every fallback dispatch. Include in cost-attribution record (UPD-027 consumer populates evidence automatically).
- [X] T031 [US3] Add structured `fallback_taken` audit record to execution records (extend `execution.events` emission in `workflow/services/executor.py` if the router's fallback is invoked during a workflow step — the router returns `ModelRouterResponse.fallback_taken` which the executor copies into the execution event).
- [X] T032 [US3] Add Prometheus metrics in `common/clients/model_router.py` per `contracts/model-router.md` telemetry section: `model_router_calls_total`, `model_router_latency_seconds`, `model_router_fallback_rate` (derived), `model_router_validation_failures_total`.

**Checkpoint**: US3 complete. Fallback works; sticky cache prevents thundering-herd; fallback events visible to operators and compliance substrate.

---

## Phase 6: User Story 4 — Model Card Review During Certification (Priority: P2)

**Goal**: Trust reviewers see model cards inline during cert; missing cards block certification; material card changes trigger re-review.

**Independent Test**: Attach card → certification succeeds with card shown. Remove card → certification blocked with clear error. Update `safety_evaluations` → affected agents flagged for re-review.

### Tests for User Story 4

- [X] T033 [P] [US4] Unit tests MC1–MC6 in `apps/control-plane/tests/unit/model_catalog/test_model_card_service.py` per `contracts/model-cards.md`: attach, material change, non-material change, history, cert blocked, compliance gap after 7 days.

### Implementation for User Story 4

- [X] T034 [P] [US4] Implement `ModelCardService` in `apps/control-plane/src/platform/model_catalog/services/model_card_service.py`: `upsert_card` (computes `revision` + material flag per `contracts/model-cards.md`), `get_card`, `get_card_history`. On material change, calls `trust_service.flag_affected_certifications_for_rereview(catalog_entry_id)` (new method in trust BC — T036).
- [X] T035 [US4] Add `PUT/GET /api/v1/model-catalog/entries/{id}/card` + `GET .../card/history` routes to `model_catalog/router.py` per `contracts/model-cards.md`. PUT is admin-gated; GET is authenticated.
- [X] T036 [US4] Extend `apps/control-plane/src/platform/trust/services/certification_service.py` `request_certification` method per `contracts/model-cards.md` pre-flight check: reject with `CertificationBlocked(reason="model_card_missing")` when the bound model has no card. Also add the new `flag_affected_certifications_for_rereview(catalog_entry_id)` method (iterates agents bound to the entry, marks their certifications for re-review, emits notifications).
- [X] T037 [US4] Extend the `auto_deprecation_scanner` worker (T015) to also emit compliance gaps for approved catalogue entries older than 7 days without an attached card. Calls `compliance_service.record_gap(...)` from UPD-024.

**Checkpoint**: US4 complete. Cards wire into cert; material changes propagate; gaps surface in compliance dashboard.

---

## Phase 7: User Story 5 — Per-Workspace Provider Credentials + Rotation (Priority: P2)

**Goal**: Register credentials as Vault path references; rotate via UPD-024's dual-credential pattern; zero in-flight failures.

**Independent Test**: Register credential → execute LLM call successfully. Trigger rotation → drive 100 req/s → assert zero failures. After overlap expiry, old credential rejected.

### Tests for User Story 5

- [X] T038 [P] [US5] Unit tests CR1–CR7 in `apps/control-plane/tests/unit/model_catalog/test_credential_service.py` per `contracts/credentials-rotation.md`: register, empty Vault path rejected, credential resolution, workspace isolation, rotation delegation, zero-downtime, emergency 2PA.

### Implementation for User Story 5

- [X] T039 [P] [US5] Implement `CredentialService` in `apps/control-plane/src/platform/model_catalog/services/credential_service.py`: `register_credential` (verifies Vault path accessibility before persisting), `get_by_workspace_provider` (used by router), `update_vault_ref`, `delete_credential`, `trigger_rotation` (delegates to UPD-024's `SecretRotationService.trigger(rotation_schedule_id)`).
- [X] T040 [US5] Integrate `ModelRouter._resolve_credential` (added to T019) with `CredentialService.get_by_workspace_provider` → `RotatableSecretProvider.get_current(vault_ref)`. Raise `CredentialNotConfiguredError` when no row exists. Constitution rule 40: the resolved value is used as `Authorization: Bearer <key>` header and never logged.
- [X] T041 [US5] Add credential-admin endpoints to `model_catalog/router.py` per `contracts/credentials-rotation.md`: `POST /credentials`, `GET /credentials`, `PATCH /credentials/{id}/vault-ref`, `DELETE /credentials/{id}`, `POST /credentials/{id}/rotate`. Emergency rotation with `overlap_window_hours: 0` requires 2PA approval via the UPD-024 workflow (rule 33).
- [X] T042 [US5] Add a logging-audit unit test `apps/control-plane/tests/unit/model_catalog/test_no_credential_in_logs.py` that captures structlog output during a router call and asserts NO log line contains the credential material (bandit-style check + runtime assertion).

**Checkpoint**: US5 complete. Per-workspace credentials landed; rotation delegated cleanly to UPD-024.

---

## Phase 8: User Story 6 — Prompt-Injection Defence (Priority: P3)

**Goal**: Three-layer defence (input sanitiser / system-prompt hardener / output validator) enabled per workspace; ≥ 95% known-attack corpus blocked.

**Independent Test**: Enable all three layers; submit known injection payload → input layer strips/quotes it. Seed an LLM response with a JWT → output validator redacts. Attempt to delete a seeded pattern → rejected.

### Tests for User Story 6

- [X] T043 [P] [US6] Unit tests PI1–PI6 in `apps/control-plane/tests/unit/model_catalog/test_injection_defense.py` per `contracts/prompt-injection-defense.md`.
- [X] T044 [P] [US6] Corpus test PI7 in `apps/control-plane/tests/integration/model_catalog/test_injection_corpus.py`: feed a standardised corpus of ≥ 50 known injection payloads through the router with all layers enabled; assert ≥ 95% blocked or neutralised (SC-007).

### Implementation for User Story 6

- [X] T045 [P] [US6] Implement `input_sanitizer.py` in `apps/control-plane/src/platform/common/clients/injection_defense/`: loads patterns from `injection_defense_patterns` table filtered by `layer='input_sanitizer'` + workspace (platform-wide + workspace-scoped); applies `strip`/`quote_as_data`/`reject` per the pattern's action; emits telemetry rows.
- [X] T046 [P] [US6] Implement `system_prompt_hardener.py` in the same directory: wraps untrusted user text with the versioned delimiter + preamble from `contracts/prompt-injection-defense.md`; the exact wording lives in a module-level constant `_HARDENING_PREAMBLE_V1` (never modified in place; bumping adds `_V2`).
- [X] T047 [P] [US6] Implement `output_validator.py` in the same directory: runs the regex set from `common/debug_logging/redaction.py` (feature 073) PLUS model-specific patterns (role-reversal phrasing) against the LLM response. On high-severity matches, calls `attention_service.raise_request(...)` from feature 060.
- [X] T048 [US6] Wire all three layers into `ModelRouter.complete` per `contracts/model-router.md` per-call algorithm steps 5 + post-call output validation. Each layer reads its enabled flag from the workspace settings (new fields on the `Workspace.settings` JSONB introduced by a small schema-shim in T007, or via a separate `workspace_injection_defense_settings` table — whichever the existing workspace-settings extension pattern supports).
- [X] T049 [US6] Add injection-pattern + findings endpoints to `model_catalog/router.py` per `contracts/prompt-injection-defense.md`: `GET/POST/PATCH/DELETE /injection-patterns`, `GET /injection-findings`. Deletion of seeded patterns (where `seeded=true`) returns 403.

**Checkpoint**: US6 complete. All three defence layers live, per-workspace configurable, ≥ 95% corpus block rate.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T050 Run the CI static-analysis check from T024 against the full control-plane codebase; confirm zero direct LLM call sites remain outside the router (rule 11 enforcement). If any legacy site is discovered, migrate it in the same commit.
- [X] T051 [P] Update the feature-catalogue page `docs/features/075-model-catalog-fallback.md` (generated on the docs branch) — replace the 7 `TODO(andrea)` placeholders with grounded content now that the feature has shipped.
- [X] T052 [P] Update `docs/administration/integrations-and-credentials.md` with the per-workspace provider credential + Vault path scheme from this feature; cross-reference UPD-024 rotation documentation.
- [X] T053 [P] Update `docs/agents.md` with the new `default_model_binding` manifest/PATCH field; document the three closest-alternative suggestion on invalid binding.
- [X] T054 Run the six quickstart walkthroughs (Q1–Q6) against a local `make dev-up`; fix any divergence before marking the feature complete.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: no deps.
- **Foundational (Phase 2)**: depends on Phase 1 — **BLOCKS all user stories**.
- **US1 (Phase 3)**: depends on Phase 2. Foundational for US2–US6.
- **US2 (Phase 4)**: depends on Phase 2 + US1 (`CatalogService` must exist for binding validation).
- **US3 (Phase 5)**: depends on US2 (router must exist; fallback is an extension of the router).
- **US4 (Phase 6)**: depends on Phase 2 + US1. Independent of US2/US3/US5/US6.
- **US5 (Phase 7)**: depends on Phase 2. Independent — can run in parallel with US2–US4.
- **US6 (Phase 8)**: depends on US2 (router must exist to wire layers into). Independent of US3/US4/US5 otherwise.
- **Polish (Phase 9)**: depends on US1–US6.

### Within Phase 2

- T004 (migration) can start with T005, T006 in parallel.
- T007 (models) and T008 (repository) parallel.
- T009 (HTTP adapter) independent.

### Within each user story

- Tests + schemas + services all `[P]` where they touch different files.
- Router + router-registration tasks (T014, T016) depend on service.
- The 2 call-site migrations (T021, T022) are independent (different files).

### Parallel execution opportunities

```bash
# Phase 1 — 3 parallel:
Task: "BC scaffold (T001)"
Task: "common/clients scaffold (T002)"
Task: "respx dev-dep (T003)"

# Phase 2 — 5 parallel after T004:
Task: "Migration 059 (T004)"
Task: "ModelCatalogSettings (T005)"
Task: "Kafka events (T006)"
Task: "SQLAlchemy models (T007)"
Task: "Repository (T008)"
# T009 depends on T007, T008.

# Phase 3 US1 — tests parallel:
Task: "CA1-7 unit tests (T010)"
Task: "Pydantic schemas (T011)"
# T012–T016 serialise (shared service/router files)

# Phase 4 US2 — tests + router parallel:
Task: "MR1-9 unit tests (T017)"
Task: "Binding integration tests (T018)"
Task: "ModelRouter (T019)"
# T021, T022 parallel (different call-site files)
# T024 (CI script) parallel with everything

# Phase 5 US3 — tests parallel:
Task: "Fallback unit tests (T025)"
Task: "Fallback E2E with respx (T026)"
Task: "Sticky cache test (T027)"
# T028–T032 extend the router; serialise on model_router.py

# Phase 6 US4:
Task: "MC1-6 tests (T033)"
Task: "ModelCardService (T034)"
# T035, T036, T037 sequential

# Phase 7 US5:
Task: "CR1-7 tests (T038)"
Task: "CredentialService (T039)"
# T040, T041, T042 sequential

# Phase 8 US6:
Task: "PI1-6 tests (T043)"
Task: "Corpus test (T044)"
Task: "input_sanitizer (T045)"
Task: "system_prompt_hardener (T046)"
Task: "output_validator (T047)"
# T048, T049 sequential (router + router.py edits)

# Polish — 3 parallel:
Task: "Catalogue doc update (T051)"
Task: "Credentials doc update (T052)"
Task: "Agents doc update (T053)"
# T050 (CI check), T054 (quickstart) serialise
```

---

## Implementation Strategy

### MVP scope (US1 + US2 + US3)

All three are P1. Minimum shippable:

1. Complete Phase 1 (T001–T003).
2. Complete Phase 2 (T004–T009).
3. Complete US1 (T010–T016).
4. Complete US2 (T017–T024).
5. Complete US3 (T025–T032).
6. **STOP and VALIDATE**: 2 existing call sites route through the router; validation blocks unapproved models; fallback triggers on provider failure; static analysis guards against new direct calls. Two compliance claims (constitution rule 11 + AD-19) ship simultaneously.

### Incremental delivery

1. US1 → catalogue + auto-deprecation.
2. **+ US2** → runtime validation + 2 call-site migrations + CI gate. Rule 11 enforced.
3. **+ US3** → fallback with zero-failure provider outages.
4. **+ US4** → cert integration + material-change tracking.
5. **+ US5** → per-workspace Vault-backed credentials + rotation.
6. **+ US6** → three-layer prompt-injection defence.
7. Polish + docs.

### Parallel team strategy (3 developers)

- **Dev A**: Phase 2 + US1 (T001–T016) → foundation + catalogue.
- **Dev B**: US2 + US3 (T017–T032) → router + fallback (lead integrator; owns `model_router.py`).
- **Dev C**: US4 + US5 + US6 in sequence (T033–T049) → cards, credentials, injection defence.
- All devs on Polish (T050–T054).

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks in the same phase.
- [Story] label maps each task to its user story for traceability.
- **Tests are part of each user story's phase** per the constitution's 95% coverage gate.
- Every v1.3.0 constitution rule the plan flagged load-bearing has a corresponding task: rule 10 → T040; rule 11 → T019 + T021 + T022 + T024; rule 39 → T040; AD-19 → T019.
- `model_router.py` (T019) grows across US2/US3/US6 — serialise edits under one developer or use a shared interface file to reduce merge conflicts.
- The migration 058 → 059 chain is preserved; T004 is `down_revision = "058"`.
- **UPD-024 dependency** load-bearing for US5. If UPD-024's `RotatableSecretProvider` is not yet live at implementation time, the env-var fallback path (per UPD-024's transitional design) is acceptable; migrate to Vault once UPD-024 lands.
