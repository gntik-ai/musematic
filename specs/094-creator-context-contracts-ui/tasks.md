# Tasks: UPD-044 — Creator-Side UIs: Context Engineering and Agent Contracts

**Feature**: 094-creator-context-contracts-ui
**Branch**: `094-creator-context-contracts-ui`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

User stories (from spec.md):
- **US1 (P1)** — Creator authors a context profile via Monaco-based editor at `/agent-management/{fqn}/context-profile`; test-with-query uses NEW MockLLMProvider per Constitution Rule 50.
- **US2 (P2)** — Creator inspects provenance via NEW `<ProvenanceViewer>` reusable on (a) profile Test tab AND (b) `<ExecutionDrilldown>` NEW Context tab.
- **US3 (P2)** — Creator rolls back profile to previous version via NEW `context_engineering_profile_versions` table (versioning is GREENFIELD per spec correction §2).
- **US4 (P1)** — Creator authors agent contract via Monaco YAML/JSON toggle at `/agent-management/{fqn}/contract` with live JSON Schema validation + auto-completion.
- **US5 (P1)** — Creator previews contract via NEW MockLLMProvider per Rule 50; real-LLM preview is opt-in with explicit "USE_REAL_LLM" confirmation per design D5.
- **US6 (P2)** — Creator forks template from NEW contract template library; upstream-update notifications via UPD-042 notification center.
- **US7 (P1)** — Creator publishes agent with profile + contract via EXTENDED `CompositionWizard` (4 steps today + 5 NEW steps).

Independent-test discipline: every US MUST be verifiable in isolation. US1 = profile editor + Monaco + JSON Schema validation + MockLLMProvider preview. US2 = `<ProvenanceViewer>` reusable on 2 surfaces (DRY). US3 = greenfield versioning + diff + non-destructive rollback. US4 = contract editor + auto-completion from existing `GET /exposed-tools` + NEW schema-enums endpoint. US5 = MockLLMProvider preview + opt-in real-LLM confirmation per Rule 50. US6 = greenfield template library + fork attribution + upstream notifications. US7 = wizard extension + 5 NEW steps + high-trust-tier validation gates.

**Wave-19 sub-division** (per plan.md "Effort & Wave"):
- W19.0 — Setup: T001-T004
- W19A — Track A Backend additions + greenfield MockLLMProvider (depends on UPD-040+041+042+043 / Waves 15-18): T005-T037
- W19B — Track B Frontend pages + Monaco editors (depends on Track A schemas): T038-T080
- W19C — Track C E2E + journey extension: T081-T093
- W19D — Cross-cutting verification (Rule 9 + Rule 41 + Rule 45 + Rule 50): T094-T098
- W19E — SC verification + documentation polish: T099-T110

---

## Phase 1: Setup

- [X] T001 [W19.0] Verify the on-disk repo state per plan.md "Phase 0 — Research" + spec.md scope-discipline section: confirm UPD-040 + UPD-041 + UPD-042 + UPD-043 are on `main`; confirm `apps/control-plane/src/platform/context_engineering/router.py:50-261` has 16 existing endpoints; confirm `apps/control-plane/src/platform/trust/router.py:206-327` has 8 existing contract endpoints; confirm `apps/control-plane/src/platform/context_engineering/service.py` has 20 existing methods per research R1; confirm `apps/control-plane/src/platform/trust/contract_service.py` has 13 existing methods per research R2; confirm `ContextEngineeringProfile` has NO versioning columns per spec correction §2 (greenfield); confirm `AgentContract` has NO `revision_id` FK per spec correction §5; confirm zero matches for `mock_llm`, `MockProvider`, `MockModel` in the codebase per spec correction §6 (greenfield per Rule 50); confirm `apps/web/package.json` has `@monaco-editor/react ^4.7.0` + `monaco-yaml ^5.4.1` per spec correction §10; confirm `apps/web/components/features/workflows/editor/MonacoYamlEditor.tsx` exists per research R6 (precedent for new Monaco usage); confirm `apps/web/components/features/agent-management/CompositionWizard.tsx` has 4 steps today per research R3; confirm `apps/web/components/features/operator/ExecutionDrilldown.tsx` has 4 tabs today per research R4; confirm `tests/e2e/journeys/test_j02_creator_to_publication.py` is 579-line skeleton with 1 async function at line 154 per research R9; confirm migration sequence at `071_workspace_owner_workbench.py` so `072` is the next slot per research R12. Document inventory in `specs/094-creator-context-contracts-ui/contracts/repo-inventory.md` (NEW file). If any of UPD-040/041/042/043 is NOT merged, BLOCK UPD-044 implementation.
- [X] T002 [P] [W19.0] Verify the migration sequence per research R12: confirm `apps/control-plane/migrations/versions/` highest-numbered migration is `071_workspace_owner_workbench.py`; if UPD-043 owns additional slots beyond 071, document the actual next sequence in `specs/094-creator-context-contracts-ui/contracts/migration-sequence.md` (NEW file). Default `072`; may shift to `073+`.
- [X] T003 [P] [W19.0] Verify the constitutional anchors per plan.md Constitutional Anchors table: open `.specify/memory/constitution.md` and confirm Rule 9 (PII audit), Rule 41 (AA accessibility), Rule 45 (lines 258-262 — every user-facing backend capability has UI), **Rule 50 lines 282-286 (Mock LLM provider for creator previews — THE canonical anchor for this feature; verified verbatim per research R14)**. If any rule has been renumbered or rewritten, escalate via spec amendment. Document confirmation in `specs/094-creator-context-contracts-ui/contracts/constitution-confirmation.md` (NEW file).
- [X] T004 [P] [W19.0] Cross-feature coordination check per plan.md "Cross-feature dependency map": confirm UPD-006 agent contracts backend on `main`; confirm UPD-042 notification center on `main` (used for upstream template-update notifications per FR-672); confirm UPD-053 zero-trust visibility on `main` (used for source-picker filtering per User Story 1); confirm UPD-077 multi-channel notifications on `main`; confirm UPD-039 (Documentation) status — if landed, runbooks land in `docs/operator-guide/`; if not, runbooks live in feature `contracts/`. Document in `specs/094-creator-context-contracts-ui/contracts/cross-feature-deps.md` (NEW file).

---

## Phase 2: Track A — Backend Additions + Greenfield MockLLMProvider

**Story goal**: Alembic migration `072` (2 NEW tables + 1 NEW column + 5 platform-template seeds); NEW `mock_llm/` BC per Constitution Rule 50 + spec correction §6 (greenfield); EXTENDS `ContextEngineeringService` with 4 new methods + `ContractService` with 3 new methods; 11 net-new endpoints; 7 new audit-event types under NEW `creator.{domain}.{action}` namespace. Honors Rule 9 + Rule 41 + Rule 45 + Rule 50.

### Alembic migration + model extensions

- [X] T005 [W19A] [US1, US3, US4, US6] Create `apps/control-plane/migrations/versions/072_creator_context_contracts.py` (or verified next-sequence number from T002) per plan.md design D1 + D2 + D6: 2 CREATE TABLE statements — `context_engineering_profile_versions` (`id` UUID PK, `profile_id` UUID FK ON DELETE CASCADE, `version_number` int NOT NULL, `content_snapshot` JSONB NOT NULL, `change_summary` text, `created_by` UUID FK users.id, `created_at` timestamptz; UNIQUE constraint on `(profile_id, version_number)`); `contract_templates` (`id` UUID PK, `name` String(255) UNIQUE, `description` text, `category` String(64), `template_content` JSONB NOT NULL, `version_number` int DEFAULT 1, `forked_from_template_id` UUID FK NULL ON DELETE SET NULL, `created_by_user_id` UUID FK users.id NULL, `is_platform_authored` bool DEFAULT false, `is_published` bool DEFAULT false, `created_at` timestamptz, `updated_at` timestamptz). 1 ALTER TABLE adding `attached_revision_id: UUID NULL` FK to `registry_agent_revisions.id` ON DELETE SET NULL on `agent_contracts` per spec correction §5 + research R7. Plus `op.execute(...)` data-migration step inserting 5 platform-authored templates per design D6 (customer-support / code-review / data-analysis / db-write / external-api-call). Reversible downgrade.
- [ ] T006 [W19A] Run `alembic upgrade head` locally; verify migration applies cleanly + downgrade -1 removes 2 tables + 1 column + 5 seeded templates without affecting existing data.
- [X] T007 [W19A] [US3] Modify `apps/control-plane/src/platform/context_engineering/models.py` per plan.md design D1: add NEW `class ContextProfileVersion(Base, UUIDMixin, TimestampMixin)` model — `profile_id: Mapped[UUID] = mapped_column(ForeignKey("context_engineering_profiles.id", ondelete="CASCADE"))`, `version_number: Mapped[int]`, `content_snapshot: Mapped[dict[str, Any]]` JSONB, `change_summary: Mapped[str | None]`, `created_by: Mapped[UUID]` FK users. Existing 6 models preserved unchanged.
- [X] T008 [W19A] [US4, US6] Modify `apps/control-plane/src/platform/trust/models.py:163-191` per plan.md design D2 + D6: add NEW `attached_revision_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("registry_agent_revisions.id", ondelete="SET NULL"), nullable=True)` column on `AgentContract` per spec correction §5; add NEW `class ContractTemplate(Base, UUIDMixin, TimestampMixin)` model per spec correction §13. Preserve existing 9 columns on `AgentContract` unchanged.

### `mock_llm/` BC (foundational greenfield primitive per Rule 50)

- [X] T009 [W19A] [US1, US5] Create `apps/control-plane/src/platform/mock_llm/__init__.py` (NEW empty module).
- [X] T010 [W19A] [US1, US5] Create `apps/control-plane/src/platform/mock_llm/schemas.py` (NEW per design D3): Pydantic schemas — `MockLLMRequest(input_text: str, context: dict | None)`, `MockLLMResponse(output_text: str, completion_metadata: dict, was_fallback: bool)`, `CannedResponse(input_hash: str, output_text: str, completion_metadata: dict)`.
- [X] T011 [W19A] [US1, US5] Create `apps/control-plane/src/platform/mock_llm/fixtures.yaml` (NEW per design D6): 5 default canned scenarios — customer-support / code-review / data-analysis / content-generation / generic-fallback. Each entry has `input_hash` (SHA-256 hex first 16 chars), `output_text` (canned response), `completion_metadata` (mock token counts + model name).
- [X] T012 [W19A] [US1, US5] Create `apps/control-plane/src/platform/mock_llm/provider.py` (NEW per design D3 + Rule 50): `class MockLLMProvider` implementing the same Protocol as real providers per research R5. Methods: `async def complete(self, request: MockLLMRequest) -> MockLLMResponse` — hashes input via `hashlib.sha256(request.input_text.encode()).hexdigest()[:16]`; looks up in fixture dict; returns canned response if matched; else returns `generic-fallback` with `was_fallback=true` + emits structured-log entry `mock_llm.fallback_used` for fixture-coverage tracking per design D3. NEVER calls real LLM endpoints.
- [X] T013 [W19A] [US1, US5] Create `apps/control-plane/src/platform/mock_llm/service.py` (NEW per design D3): `class MockLLMService` drop-in replacement that injects `MockLLMProvider` into preview flows. Single dependency-injected service usable by `ContextEngineeringService.preview_retrieval` and `ContractService.preview_contract`.
- [X] T014 [W19A] [US1, US5] Author `apps/control-plane/tests/mock_llm/test_provider.py` (NEW pytest test file): ~12 cases per Constitution Rule 50 invariants — deterministic hash matching (same input → same response 100 times), generic-fallback path (unknown hash → fallback + `was_fallback=true`), `mock_llm.fallback_used` log emission, NO real LLM calls (verified via metric `real_llm_calls_total` does NOT increment), Pydantic schema validation, fixture file load from disk, fixture file missing handling (refuses to start per spec edge case).

### Context engineering service extension

- [X] T015 [W19A] [US1] Modify `apps/control-plane/src/platform/context_engineering/service.py` per plan.md design D1 + research R1: add `async def preview_retrieval(self, profile_id: UUID, query_text: str) -> PreviewResponse` method per FR-667 — invokes `MockLLMProvider` per Rule 50; returns provenance data with sources + scores + classifications; emits `creator.context_profile.preview_executed` audit entry.
- [X] T016 [W19A] [US3] Add `async def get_profile_versions(self, profile_id: UUID, limit: int, cursor: str | None) -> tuple[list[ContextProfileVersion], str | None]` method per FR-669: cursor-based pagination over the NEW `context_engineering_profile_versions` table.
- [X] T017 [W19A] [US3] Add `async def get_version_diff(self, profile_id: UUID, v1_number: int, v2_number: int) -> VersionDiffResponse` method per FR-669: fetches both version snapshots; returns structured diff (added / removed / modified keys with old/new values) computed on-the-fly from JSONB content snapshots.
- [X] T018 [W19A] [US3] Add `async def rollback_to_version(self, profile_id: UUID, target_version_number: int, requester_id: UUID) -> ContextProfileVersion` method per FR-669 + plan.md design D1: validates target version exists; creates a NEW version (e.g., v5 if rolling back from v4 to v3, content_snapshot = v3.content_snapshot); never destructively mutates v3 or v4; emits `creator.context_profile.rolled_back` audit entry per spec correction §10.

### Trust contract service extension

- [X] T019 [W19A] [US5] Modify `apps/control-plane/src/platform/trust/contract_service.py` per plan.md design D5 + research R2: add `async def preview_contract(self, contract_id: UUID, sample_input: dict, use_mock: bool = True, cost_acknowledged: bool = False) -> PreviewResponse` method per FR-671 + Rule 50. When `use_mock=True` (default), invokes `MockLLMProvider`; when `use_mock=False`, validates `cost_acknowledged=True` (raises 400 if false); only when both flags are true, invokes real LLM. Returns clauses-triggered + clauses-satisfied + clauses-violated + final-action. Emits `creator.contract.preview_executed` audit; if real LLM used, also emits `creator.contract.real_llm_preview_used`.
- [X] T020 [W19A] [US6] Add `async def fork_template(self, template_id: UUID, new_name: str, workspace_id: UUID, requester_id: UUID) -> AgentContract` method per FR-672: validates source template exists + is_published=true; creates a NEW `AgentContract` row with `template_content` copied from source + `forked_from_template_id` set + `created_by_user_id=requester_id`. Emits `creator.contract.forked_from_template` audit per spec correction §10.
- [X] T021 [W19A] [US7] Add `async def attach_to_revision(self, contract_id: UUID, revision_id: UUID, requester_id: UUID) -> None` method per FR-673 + spec correction §5: validates contract exists + revision exists + revision belongs to same agent; sets `attached_revision_id = revision_id`; emits `creator.contract.attached_to_revision` audit.

### Pydantic schemas + audit events

- [X] T022 [W19A] [US1, US3] Modify `apps/control-plane/src/platform/context_engineering/schemas.py`: add NEW Pydantic schemas — `PreviewRequest(query_text)`, `PreviewResponse(sources, mock_response, was_fallback)`, `VersionHistoryResponse(versions, next_cursor)`, `VersionDiffResponse(added, removed, modified)`, `RollbackRequest(target_version)`, `ContextProfileVersionResponse`. Each Pydantic model exports JSON Schema via `Model.model_json_schema()` for the NEW schema endpoint per design D4.
- [X] T023 [W19A] [US4, US5, US6, US7] Modify `apps/control-plane/src/platform/trust/contract_schemas.py`: add NEW Pydantic schemas — `PreviewRequest(sample_input, use_mock, cost_acknowledged)`, `PreviewResponse(clauses_triggered, clauses_satisfied, clauses_violated, final_action)`, `ForkRequest(new_name)`, `AttachRevisionRequest(revision_id)`, `ContractTemplateResponse`, `ContractTemplateListResponse`.
- [X] T024 [W19A] [US1, US3, US4, US5, US6, US7] Wire 7 new audit-event types per plan.md Constitutional Anchors row Rule 9: `creator.context_profile.created`, `creator.context_profile.updated`, `creator.context_profile.rolled_back`, `creator.contract.created`, `creator.contract.preview_executed`, `creator.contract.attached_to_revision`, `creator.contract.forked_from_template`. Plus 1 conditional event `creator.contract.real_llm_preview_used` (emitted only when opt-in). Each follows the existing dual-emission pattern per UPD-042/043 research.

### Context engineering router endpoints

- [X] T025 [W19A] [US1] Add `POST /api/v1/context-engineering/profiles/{profile_id}/preview` endpoint per FR-667: handler calls `context_engineering_service.preview_retrieval(profile_id, query_text)`; returns `PreviewResponse`.
- [X] T026 [W19A] [US3] Add `GET /api/v1/context-engineering/profiles/{profile_id}/versions` endpoint per FR-669: cursor-paginated.
- [X] T027 [W19A] [US3] Add `GET /api/v1/context-engineering/profiles/{profile_id}/versions/{v1}/diff/{v2}` endpoint per FR-669: returns `VersionDiffResponse`.
- [X] T028 [W19A] [US3] Add `POST /api/v1/context-engineering/profiles/{profile_id}/rollback/{version}` endpoint per FR-669: requires `WorkspaceRole.member` minimum (workspace-scoped) per existing pattern.
- [X] T029 [W19A] [US1] Add `GET /api/v1/context-engineering/profiles/schema` endpoint per spec correction §14 + design D4: returns Pydantic-generated JSON Schema for the profile body. NO server-side caching.

### Trust contract router endpoints

- [X] T030 [W19A] [US5] Add `POST /api/v1/contracts/{contract_id}/preview` endpoint per FR-671 + design D5: handler calls `contract_service.preview_contract(contract_id, sample_input, use_mock, cost_acknowledged)`; rejects with 400 if `use_mock=False AND cost_acknowledged=False` per design D5.
- [X] T031 [W19A] [US6] Add `GET /api/v1/contracts/templates` endpoint per FR-672: returns `ContractTemplateListResponse` with platform-authored + workspace-creator templates.
- [X] T032 [W19A] [US6] Add `POST /api/v1/contracts/{template_id}/fork` endpoint per FR-672: handler calls `contract_service.fork_template(template_id, new_name, workspace_id, requester_id)`; returns the new contract.
- [X] T033 [W19A] [US7] Add `POST /api/v1/contracts/{contract_id}/attach-revision/{revision_id}` endpoint per FR-673 + spec correction §5.
- [X] T034 [W19A] [US4] Add `GET /api/v1/contracts/schema` endpoint per spec correction §14 + design D4: returns Pydantic JSON Schema for `AgentContractCreate`.
- [X] T035 [W19A] [US4] Add `GET /api/v1/contracts/schema-enums` endpoint per spec correction §15 + design D7: returns `{resource_types, role_types, workspace_constraints, failure_modes}` aggregated from existing platform enums.

### Track A integration tests

- [X] T036 [W19A] [US1, US3] Author `apps/control-plane/tests/context_engineering/test_versioning.py` (NEW pytest file): ~10 cases — version 1 created on first save, monotonic version_number, version diff structure, rollback creates new version (never destructive), unique constraint on `(profile_id, version_number)`, ON DELETE CASCADE on profile deletion.
- [X] T037 [W19A] [US1] Author `apps/control-plane/tests/context_engineering/test_preview.py` (NEW pytest file): ~6 cases — preview invokes MockLLMProvider, returns provenance data, NO real LLM calls (metric verification per Rule 50).
- [X] T038 [W19A] [US5] Author `apps/control-plane/tests/trust/test_contract_preview.py` (NEW pytest file): ~8 cases — mock preview happy path, opt-in real LLM rejected without cost_acknowledged, opt-in real LLM accepted with cost_acknowledged, response structure (clauses + final action), `creator.contract.preview_executed` audit emission, `creator.contract.real_llm_preview_used` audit emission only when real LLM used.
- [X] T039 [W19A] [US6] Author `apps/control-plane/tests/trust/test_contract_templates.py` (NEW pytest file): ~6 cases — list templates returns 5 platform-authored, fork creates editable copy with metadata, `forked_from_template_id` immutable, fork attribution preserved on upstream deletion (ON DELETE SET NULL).
- [X] T040 [W19A] [US7] Author `apps/control-plane/tests/trust/test_attach_to_revision.py` (NEW pytest file): ~5 cases — attach happy path, revision deletion sets FK to NULL (ON DELETE SET NULL), attach validates revision belongs to same agent, audit entry emission, re-attach overwrites previous attachment.

**Checkpoint (end of Phase 2)**: `pytest apps/control-plane/tests/{mock_llm,context_engineering,trust}/` passes (~57 unit tests); 11 new endpoints + 7 service methods + MockLLMProvider wired correctly; migration is reversible; Rule 50 invariants verified (real_llm_calls_total Prometheus metric does NOT increment during preview tests).

---

## Phase 3: Track B — Frontend Pages + Monaco Editors

**Story goal**: 5 NEW Next.js pages + 30 sub-components per FR-667 through FR-674 + Rule 45. Reuses existing Monaco precedent at `MonacoYamlEditor.tsx` per research R6 (NOT CodeMirror per spec correction §10). EXTENDS `CompositionWizard` + `<ExecutionDrilldown>`. ~80 i18n keys × 6 locales = 480 entries. axe-core AA + Monaco keyboard-nav per Rule 41 + SC-019.

### Shared scaffolding

- [X] T041 [W19B] [US1, US4] Create `apps/web/components/features/agents/YamlJsonEditor.tsx` (NEW per plan.md design D9 + research R6): shared Monaco wrapper modeled on existing `apps/web/components/features/workflows/editor/MonacoYamlEditor.tsx`. Supports YAML/JSON toggle (`enableLanguageToggle: boolean`) + JSON Schema validation provider (`schemaUrl: string` parameterized) + auto-completion. Lazy-loaded via `next/dynamic` to avoid bundling Monaco into non-editor pages.
- [X] T042 [W19B] Create `apps/web/components/features/agents/SchemaValidatedEditor.tsx` (NEW): generic wrapper around `<YamlJsonEditor>` providing inline validation + auto-completion from fetched JSON Schema. Used by both profile + contract editors.
- [X] T043 [W19B] Create `apps/web/components/features/agents/ProvenanceViewer.tsx` (NEW per plan.md design D8 + FR-668): reusable component accepting `executionId: string | null` prop. On profile editor's Test tab, prop is null (reads from preview-result-state); on `<ExecutionDrilldown>` Context tab, prop is the execution ID and component fetches via `GET /context-engineering/assembly-records/{record_id}`. Renders sources in descending score with origin/snippet/score/included-flag/classification badges per User Story 2.
- [X] T044 [W19B] [US3] Create `apps/web/components/features/agents/VersionHistory.tsx` (NEW): generic version history component (greenfield primitive per spec correction §13 — no existing precedent in codebase). Reusable for profile versioning today + future use cases. Displays version list + side-by-side diff view + rollback action.

### API + schemas + hooks

- [X] T045 [W19B] Create `apps/web/lib/api/creator-uis.ts` (NEW): fetch wrappers for 11 new endpoints (4 context-engineering + 4 contract + 2 schema + 1 enums).
- [X] T046 [W19B] Create `apps/web/lib/schemas/creator-uis.ts` (NEW): Zod schemas mirroring backend Pydantic schemas. NOTE: the JSON Schema for live Monaco validation is fetched at runtime from the new schema endpoints per design D4.
- [X] T047 [P] [W19B] Create `apps/web/lib/hooks/use-context-profile-versions.ts` (NEW): TanStack Query hook for `GET /profiles/{id}/versions` (cursor-paginated).
- [X] T048 [P] [W19B] Create `apps/web/lib/hooks/use-context-profile-preview.ts` (NEW): mutation hook for `POST /profiles/{id}/preview` invoking MockLLMProvider.
- [X] T049 [P] [W19B] Create `apps/web/lib/hooks/use-contract-preview.ts` (NEW): mutation hook for `POST /contracts/{id}/preview` with `use_mock + cost_acknowledged` params per design D5.
- [X] T050 [P] [W19B] Create `apps/web/lib/hooks/use-contract-templates.ts` (NEW): hooks for list templates + fork template.
- [X] T051 [P] [W19B] Create `apps/web/lib/hooks/use-contract-schema.ts` (NEW): TanStack Query hook fetching JSON Schema from `GET /contracts/schema`; cache stale-time = 1 hour per design D4.
- [X] T052 [P] [W19B] Create `apps/web/lib/hooks/use-profile-schema.ts` (NEW): TanStack Query hook fetching profile JSON Schema.
- [X] T053 [P] [W19B] Create `apps/web/lib/hooks/use-schema-enums.ts` (NEW): TanStack Query hook fetching `GET /contracts/schema-enums` for contract editor auto-complete (resource/role types).

### Context profile editor (US1)

- [X] T054 [W19B] [US1] Create `apps/web/app/(main)/agent-management/[fqn]/context-profile/page.tsx` (NEW ~250 lines per FR-667): server component shell wrapping client editor.
- [X] T055 [W19B] [US1] Create `apps/web/app/(main)/agent-management/[fqn]/context-profile/_components/ContextProfileEditor.tsx` (NEW ~400 lines): top-level editor composing sub-components below; uses `<SchemaValidatedEditor>` from T042.
- [X] T056 [W19B] [US1] Create `apps/web/app/(main)/agent-management/[fqn]/context-profile/_components/SourcePicker.tsx` (NEW ~200 lines): workspace-visibility-filtered source picker per UPD-053; displays excluded sources with tooltip explaining why.
- [X] T057 [P] [W19B] [US1] Create `apps/web/app/(main)/agent-management/[fqn]/context-profile/_components/RetrievalStrategySelector.tsx` (NEW ~120 lines): per-source picker for semantic / graph / FTS / hybrid.
- [X] T058 [P] [W19B] [US1] Create `apps/web/app/(main)/agent-management/[fqn]/context-profile/_components/RerankingRulesEditor.tsx` (NEW ~200 lines): drag-reorderable rules list (by score / by recency / by authority / custom expression).
- [X] T059 [P] [W19B] [US1] Create `apps/web/app/(main)/agent-management/[fqn]/context-profile/_components/ContextBudgetControls.tsx` (NEW ~150 lines): max tokens / max documents / per-source fractions.
- [X] T060 [W19B] [US1, US2] Create `apps/web/app/(main)/agent-management/[fqn]/context-profile/_components/TestQueryPanel.tsx` (NEW ~180 lines): test-with-query panel embedding `<ProvenanceViewer executionId={null}>` per design D8; calls `POST /preview` via T048 hook.

### Context profile history page (US3)

- [X] T061 [W19B] [US3] Create `apps/web/app/(main)/agent-management/[fqn]/context-profile/history/page.tsx` (NEW ~200 lines per FR-669): version history page with `<VersionList>` + `<VersionDiffViewer>`.
- [X] T062 [W19B] [US3] Create `apps/web/app/(main)/agent-management/[fqn]/context-profile/history/_components/VersionList.tsx` (NEW ~150 lines): paginated list with timestamp + author + change summary; "Compare" + "Rollback" actions per row.
- [X] T063 [W19B] [US3] Create `apps/web/app/(main)/agent-management/[fqn]/context-profile/history/_components/VersionDiffViewer.tsx` (NEW ~250 lines): side-by-side JSON diff with green/red highlights per User Story 3 acceptance scenario 2; uses a JSON-diff library (likely `diff` package — verify availability in `package.json` during T063; if absent, add minimal dep).

### Contract editor (US4)

- [X] T064 [W19B] [US4] Create `apps/web/app/(main)/agent-management/[fqn]/contract/page.tsx` (NEW ~250 lines per FR-670).
- [X] T065 [W19B] [US4] Create `apps/web/app/(main)/agent-management/[fqn]/contract/_components/ContractEditor.tsx` (NEW ~400 lines): Monaco YAML/JSON toggle wrapping `<YamlJsonEditor>` from T041 with `enableLanguageToggle=true`. Auto-completion fetches tool FQNs from existing `GET /exposed-tools` per research R11 + resource/role enums from new `GET /schema-enums` per design D7.

### Contract preview + sample inputs (US5)

- [X] T066 [W19B] [US5] Create `apps/web/app/(main)/agent-management/[fqn]/contract/_components/ContractPreviewPanel.tsx` (NEW ~250 lines per FR-671): sample input editor + result inspector. Shows clause status badges; clicking a violated clause scrolls Monaco to the contract line.
- [X] T067 [W19B] [US5] Create `apps/web/app/(main)/agent-management/[fqn]/contract/_components/SampleInputManager.tsx` (NEW ~180 lines): saved samples + load/save actions.
- [X] T068 [W19B] [US5] Create `apps/web/app/(main)/agent-management/[fqn]/contract/_components/RealLLMOptInDialog.tsx` (NEW ~150 lines per design D5 + Rule 50): explicit confirmation dialog showing estimated cost + asks user to type "USE_REAL_LLM" to confirm. On confirm, calls preview endpoint with `use_mock=false, cost_acknowledged=true`.

### Contract attach + history (US7)

- [X] T069 [W19B] [US7] Create `apps/web/app/(main)/agent-management/[fqn]/contract/_components/AttachToRevisionDialog.tsx` (NEW ~150 lines per FR-673 + spec correction §5): revision selector + confirm action; calls `POST /contracts/{id}/attach-revision/{revision_id}`.
- [X] T070 [W19B] [US4] Create `apps/web/app/(main)/agent-management/[fqn]/contract/history/page.tsx` (NEW ~180 lines): contract change history.

### Contract template library (US6)

- [X] T071 [W19B] [US6] Create `apps/web/app/(main)/agent-management/contracts/library/page.tsx` (NEW ~250 lines per FR-672 — workspace-global page, NOT under `[fqn]/`).
- [X] T072 [W19B] [US6] Create `apps/web/app/(main)/agent-management/contracts/library/_components/TemplateCard.tsx` (NEW ~150 lines): renders template name + description + fork count + last updated; "Fork" action.
- [X] T073 [W19B] [US6] Create `apps/web/app/(main)/agent-management/contracts/library/_components/ForkDialog.tsx` (NEW ~180 lines): name input + workspace selector + confirm action; calls `POST /contracts/{template_id}/fork`.
- [ ] T074 [W19B] [US6] Wire UPD-042 notification integration per FR-672 + spec correction §14: subscribe to `creator.contract_template.upstream_updated` events on the user's notification channel; display in notification bell with "View diff" link to compare fork against upstream new version.

### Wizard extension (US7)

- [X] T075 [W19B] [US7] Modify `apps/web/components/features/agent-management/CompositionWizard.tsx` per plan.md design + research R3: extend the existing `STEP_LABELS` array (lines 13-18) with 5 new entries — "Context Profile", "Test Profile", "Contract", "Preview Contract", "Attach Both". Extend the conditional render block (lines 48-67) with 5 NEW branches for the new step components. Existing 4 steps preserved unchanged.
- [X] T076 [P] [W19B] [US7] Create `apps/web/components/features/agent-management/wizard/WizardStepContextProfile.tsx` (NEW ~200 lines): step 5 — embeds `ContextProfileEditor` from T055.
- [X] T077 [P] [W19B] [US7] Create `apps/web/components/features/agent-management/wizard/WizardStepTestProfile.tsx` (NEW ~150 lines): step 6 — embeds `TestQueryPanel` from T060.
- [X] T078 [P] [W19B] [US7] Create `apps/web/components/features/agent-management/wizard/WizardStepContract.tsx` (NEW ~200 lines): step 7 — embeds `ContractEditor` from T065.
- [X] T079 [P] [W19B] [US7] Create `apps/web/components/features/agent-management/wizard/WizardStepPreviewContract.tsx` (NEW ~150 lines): step 8 — embeds `ContractPreviewPanel` from T066.
- [X] T080 [W19B] [US7] Create `apps/web/components/features/agent-management/wizard/WizardStepAttachBoth.tsx` (NEW ~180 lines): step 9 — final review + attach-to-revision action; for high-trust-tier agents, validation gate blocks publish if profile or contract is missing per FR-674.

### ExecutionDrilldown extension (US2)

- [X] T081 [W19B] [US2] Modify `apps/web/components/features/operator/ExecutionDrilldown.tsx` per research R4: extend the `DrilldownTab` union (line 22) with `"context"`; extend `VALID_TABS` set with `"context"`; add NEW `<TabsContent value="context">` block rendering `<ProvenanceViewer executionId={executionId} />` per design D8. Existing 4 tabs (`trajectory`, `checkpoints`, `debate`, `react`) preserved unchanged.

### i18n + accessibility + Playwright

- [ ] T082 [W19B] [US1, US3, US4, US5, US6, US7] Modify `apps/web/messages/en.json` per plan.md research: add ~80 new i18n keys under `creator.{contextProfile,contract,template}.*` namespaces. Reference these in all new TSX components via `useTranslations(...)`.
- [X] T083 [P] [W19B] Modify `apps/web/messages/{de,es,fr,it,zh-CN,ja}.json`: copy English keys with TODO-translation markers per UPD-088's parity check; vendor translates per UPD-039 / FR-620.
- [X] T084 [P] [W19B] Run `pnpm test:i18n-parity` — verify all 6 locale catalogs have all new keys.
- [ ] T085 [W19B] Run axe-core scan on all 5 new pages locally; verify zero AA violations per Rule 41 inheritance from UPD-083. Verify Monaco editor is keyboard-navigable per SC-019 — manual test: tab through editor toolbar, ESC to exit Monaco, screen reader announces "Code editor".
- [X] T086 [W19B] Run `pnpm test`, `pnpm typecheck`, `pnpm lint` to verify all CI gates pass.
- [ ] T087 [W19B] [US1, US2, US3, US4, US5, US6, US7] Author `apps/web/tests/e2e/creator-uis-pages.spec.ts` (NEW Playwright test file): ~20 scenarios covering profile editor + provenance viewer reusable across 2 surfaces + version rollback + contract editor + contract preview + opt-in real LLM dialog + template fork + wizard 5 new steps.

**Checkpoint (end of Phase 3)**: 5 new pages + wizard extension + ExecutionDrilldown extension render correctly; `pnpm test`, `pnpm typecheck`, axe-core scan, i18n parity check all pass; Playwright E2E ~20 scenarios pass; Monaco keyboard-nav verified.

---

## Phase 4: Track C — E2E + Journey Extension

**Story goal**: 7 NEW E2E test files at `tests/e2e/suites/creator_uis/`; J02 EXTENSION with ≥ 25 NEW assertion blocks per FR-674.

### E2E suite scaffolding

- [X] T088 [W19C] [US1, US2, US3, US4, US5, US6, US7] Create `tests/e2e/suites/creator_uis/__init__.py` + `conftest.py` (NEW pytest fixtures): `creator_with_agent` (creator + agent with one revision), `creator_with_profile` (creator + agent + saved profile v1), `creator_with_contract` (creator + agent + draft contract), `mock_llm_responses` (seeded canned responses), `contract_template_seeded` (5 platform templates from migration `072`).

### 7 E2E test files (one per User Story)

- [X] T089 [W19C] [US1] Create `tests/e2e/suites/creator_uis/test_profile_editor.py` (NEW): 5 cases — Monaco loads + JSON Schema validation, source-picker visibility filtering per UPD-053, preview invokes MockLLMProvider (verified by metric), profile saved as version 1, audit entry emitted.
- [X] T090 [P] [W19C] [US3] Create `tests/e2e/suites/creator_uis/test_profile_rollback.py` (NEW): 5 cases — version history pagination, side-by-side diff with green/red highlights, rollback creates new version (never destructive), agent revisions pinned to specific version unaffected per FR-669.
- [X] T091 [P] [W19C] [US2] Create `tests/e2e/suites/creator_uis/test_provenance_viewer.py` (NEW): 4 cases — `<ProvenanceViewer>` reusable on profile Test tab + ExecutionDrilldown Context tab (DRY verification per SC-005), classification badges (PII red, public green), origin deep-inspect navigation.
- [X] T092 [P] [W19C] [US4] Create `tests/e2e/suites/creator_uis/test_contract_editor.py` (NEW): 5 cases — Monaco YAML/JSON toggle, JSON Schema fetched from new endpoint, auto-completion suggests tool FQNs from `GET /exposed-tools`, schema-enums for resource/role types, save creates contract row.
- [X] T093 [P] [W19C] [US5] Create `tests/e2e/suites/creator_uis/test_contract_preview.py` (NEW): 5 cases — mock preview happy path (verified `real_llm_calls_total` did NOT increment per Rule 50), opt-in real-LLM dialog requires "USE_REAL_LLM" typed confirmation, opt-in real-LLM rejected without cost_acknowledged, clause violation links to Monaco line, audit entries for both mock + real-LLM previews.
- [X] T094 [P] [W19C] [US6] Create `tests/e2e/suites/creator_uis/test_template_fork.py` (NEW): 4 cases — template library renders 5 platform templates, fork creates editable copy with `forked_from_template_id`, upstream-update notification via UPD-042 notification center, fork attribution preserved on upstream deletion.
- [X] T095 [P] [W19C] [US7] Create `tests/e2e/suites/creator_uis/test_publish_with_profile_and_contract.py` (NEW): 6 cases — wizard extends with 5 new steps, high-trust-tier agent cannot publish without both profile + contract, low-trust-tier agent can skip steps, attach-to-revision sets `attached_revision_id`, publish snapshots profile version + contract content to revision, audit chain for full flow.

### J02 journey extension

- [ ] T096 [W19C] [US1, US2, US3, US4, US5, US6, US7] Modify `tests/e2e/journeys/test_j02_creator_to_publication.py` per FR-674 + spec correction §9 + research R9: extend the existing single async function `test_j02_creator_to_publication()` at line 154 with ≥ 25 NEW assertion blocks covering the full creator flow. Sections per plan.md Phase 4 day 6: (6-8) NEW context profile create + edit + preview; (9-11) NEW context profile rollback + diff + version pinning; (12-14) NEW contract create + edit + preview; (15-17) NEW contract preview-via-mock + opt-in-real-LLM-rejection-path + violations-link-to-clause; (18-20) NEW template fork + customize + upstream-update-notification; (21-23) NEW attach-profile-to-revision + attach-contract-to-revision + publish-with-both; (24-25) NEW post-publish verification (audit chain entries + revision pinned to profile version + contract attached). Final J02 line count ≈ 750 lines.

### Matrix-CI integration

- [X] T097 [W19C] [US1, US2, US3, US4, US5, US6, US7] Modify `.github/workflows/ci.yml`: add `tests/e2e/suites/creator_uis/` to UPD-040's matrix-CI test path (3 modes: `mock`, `kubernetes`, `vault`). Verify all 7 test files pass in all 3 modes.
- [ ] T098 [W19C] Verify SC-016: J02 (extended) + 7 E2E suite tests pass on the matrix CI for all 3 modes. If any mode fails, debug + fix.
- [ ] T099 [W19C] Run `pytest tests/e2e/suites/creator_uis/ -v` against a kind cluster with the platform running → 7 test files pass.

**Checkpoint (end of Phase 4)**: 7 E2E test files + J02 extension all pass; matrix CI green for all 3 secret modes.

---

## Phase 5: Cross-Cutting Verification (Rule 9 + Rule 41 + Rule 45 + Rule 50)

**Story goal**: Verify Rule 50 invariants (mock LLM provider) + Rule 9 (audit emission) + Rule 41 (Monaco keyboard-nav) + Rule 45 (every backend capability has UI).

- [ ] T100 [W19D] Verify Rule 50 invariants per Constitution + plan.md design D3: synthetic test invokes preview endpoints (profile + contract) 100 times with `use_mock=true` (default); asserts `real_llm_calls_total` Prometheus metric did NOT increment; asserts `mock_llm.preview_executed` audit-log entries emitted; opt-in path with `use_mock=false, cost_acknowledged=false` MUST be rejected with 400; opt-in path with both `true` MUST emit `creator.contract.real_llm_preview_used` audit. Document in `specs/094-creator-context-contracts-ui/contracts/rule50-verification.md` (NEW file).
- [ ] T101 [W19D] Verify all 11 new endpoints emit audit-chain entries per Rule 9: synthetic test hits each state-changing endpoint (preview / rollback / fork / attach-revision); asserts `audit_chain_entries` row count grows by exactly 1 per call (or 2 for opt-in real-LLM path which emits 2 entries). Document in `specs/094-creator-context-contracts-ui/contracts/audit-emission-verification.md` (NEW file).
- [ ] T102 [W19D] Verify Rule 41 + SC-019: axe-core scan on all 5 new pages + manual Monaco keyboard-nav test (tab navigation, ESC to exit editor, screen reader announces editor labels). Document accessibility report at `specs/094-creator-context-contracts-ui/contracts/accessibility-report.md` (NEW file).
- [ ] T103 [W19D] Verify Rule 45 mapping: every Track A endpoint maps to a Track B page per spec.md Key Entities section. Synthetic test enumerates the 11 new Track A endpoints + asserts a corresponding page exists at the documented URL. Failure means a backend capability has no UI surface — escalate.
- [X] T104 [W19D] Run UPD-040's `scripts/check-secret-access.py` against the in-flight code; verify zero direct `os.getenv("*_SECRET")` calls outside `SecretProvider` implementation files (the MockLLMProvider does NOT need any secrets — it uses canned responses).

---

## Phase 6: SC Verification + Documentation Polish

**Story goal**: All 20 spec SCs pass; UPD-039 docs integration; release notes; final review.

- [ ] T105 [W19E] Run the full SC verification sweep per the spec's 20 SCs. For each SC, document the actual measurement (e.g., SC-001's "≤ 2 seconds Monaco load" — measured wall-clock with cold cache). Capture verification record at `specs/094-creator-context-contracts-ui/contracts/sc-verification.md` (NEW file).

### Operator runbooks (UPD-039 integration)

- [X] T106 [W19E] [US1, US5] Create `docs/operator-guide/runbooks/creator-mock-llm-fallback.md` (NEW per plan.md design D10 + Rule 50; deliverable here if UPD-039 has landed; otherwise UPD-039 owns and merges later). Sections: Symptom (creator's preview returns generic-fallback frequently), Diagnosis (check `mock_llm.fallback_used` log rate), Remediation (add new canned-response fixture for the unmatched input pattern), Verification (re-run preview + check fixture coverage).
- [X] T107 [P] [W19E] [US3] Create `docs/operator-guide/runbooks/context-profile-versioning.md`: rollback flow + revision pinning + storage growth.
- [X] T108 [P] [W19E] [US6] Create `docs/operator-guide/runbooks/contract-template-upstream-update.md`: fork notification flow + manual diff resolution.

### Developer guide pages

- [X] T109 [P] [W19E] Create `docs/developer-guide/mock-llm-provider-internals.md`: Rule 50 architectural design + canned-response fixture format (YAML schema) + how to add new fixtures + hash-keying algorithm.
- [X] T110 [P] [W19E] [US1] Create `docs/developer-guide/creator-context-profile-format.md`: JSON Schema + per-source provenance fields (per spec correction §3) + versioning model + rollback semantics.
- [X] T111 [P] [W19E] [US4, US5, US6, US7] Create `docs/developer-guide/contract-template-design.md`: template forking + upstream-update notification flow + revision-attachment FK semantics.

### Auto-doc verification + release notes

- [X] T112 [W19E] If UPD-039 has landed, run `python scripts/check-doc-references.py` against new docs — verify FR-667 through FR-674 references in this feature's docs are valid + linked to section 117.
- [X] T113 [W19E] Modify `docs/release-notes/v1.4.0/creator-side-uis.md` (NEW file or extend the existing v1.4.0 release notes file): document 5 new pages + 11 new endpoints + foundational MockLLMProvider primitive (greenfield per Rule 50 — first production implementation, reusable by future creator-preview flows in evaluation, simulation, etc.) + greenfield versioning + greenfield contract template library + 7 new audit-event types under NEW `creator.{domain}.{action}` namespace. NO breaking changes (purely additive).

### Final review

- [ ] T114 [W19E] Verify all 20 spec SCs pass (re-run T105); verify J02 extension + 7 E2E suites + 20 Playwright scenarios all pass on the matrix CI; verify Rule 50 invariants per T100; verify UPD-006/UPD-042/UPD-043's existing test suites pass unchanged (UPD-044 extends them — SC-020 verifies backward compatibility).
- [ ] T115 [W19E] Run `pytest apps/control-plane/tests/{mock_llm,context_engineering,trust}/`, `pytest tests/e2e/suites/creator_uis/`, `pytest tests/e2e/journeys/test_j02_creator_to_publication.py`, `pnpm test`, `pnpm typecheck`, `pnpm lint`, `pnpm test:i18n-parity` one final time → all pass.
- [X] T116 [W19E] Run `python scripts/check-secret-access.py` (UPD-040), `python scripts/check-admin-role-gates.py` (UPD-040), `python scripts/check-me-endpoint-scope.py` (UPD-042 — informational; UPD-044 endpoints are NOT under `/me/*`) → all pass with zero violations.
- [ ] T117 [W19E] Address PR review feedback; merge. Verify the `094-creator-context-contracts-ui` branch passes all required CI gates (matrix-CI for 3 secret modes, secret-access check, axe-core AA scan, i18n parity); merge to `main`. **This is the FIRST feature of the v1.4.0 cycle.**

---

## Dependencies & Execution Order

### Phase Dependencies

- **W19.0 Setup (T001-T004)**: No blockers; T001 verifies UPD-040+041+042+043 are on `main` (HARD DEPENDENCY).
- **W19A Track A Backend (T005-T040)**: Depends on W19.0 + UPD-040/041/042/043 shipped.
- **W19B Track B UI (T041-T087)**: Depends on Track A T022-T023 (Pydantic schemas) — frontend Zod schemas mirror backend; T041-T053 (shared scaffolding + hooks) can begin once schemas land; T054-T087 depend on full Track A endpoints functional.
- **W19C Track C E2E + journey (T088-T099)**: Depends on Track A (endpoints functional) + Track B (UI for Playwright + journey-step page navigation).
- **W19D Cross-cutting verification (T100-T104)**: Depends on Track A + Track B (full flows must be runnable for log capture + Rule 50 invariant verification).
- **W19E SC verification + docs (T105-T117)**: Depends on ALL OTHER PHASES — convergent.

### User Story Dependencies

- **US1 (P1 — context profile editor)**: T015 (preview method) + T025 (preview endpoint) + T029 (profile schema endpoint) + T054-T060 (editor + 6 sub-components) + T089 (E2E) + T096 (J02).
- **US2 (P2 — provenance viewer)**: T043 (`<ProvenanceViewer>` reusable component) + T060 (TestQueryPanel) + T081 (ExecutionDrilldown extension) + T091 (E2E).
- **US3 (P2 — profile version rollback)**: T005-T007 (migration + model) + T016-T018 (3 versioning service methods) + T026-T028 (3 versioning endpoints) + T044 (`<VersionHistory>`) + T061-T063 (history page + sub-components) + T090 (E2E) + T096 (J02).
- **US4 (P1 — contract editor)**: T034 (contract schema endpoint) + T035 (schema-enums endpoint) + T064-T065 (editor) + T092 (E2E) + T096 (J02).
- **US5 (P1 — contract preview via mock)**: T009-T014 (MockLLMProvider) + T019 (preview method) + T030 (preview endpoint) + T066-T068 (preview panel + sample manager + opt-in dialog) + T093 (E2E) + T100 (Rule 50 verification).
- **US6 (P2 — contract template library)**: T005 (migration with seeds) + T020 (fork method) + T031-T032 (template endpoints) + T071-T074 (library page + cards + fork dialog + UPD-042 integration) + T094 (E2E).
- **US7 (P1 — wizard with profile + contract)**: T021 (attach-to-revision method) + T033 (attach-revision endpoint) + T069 (attach dialog) + T075-T080 (wizard extension + 5 new steps) + T095 (E2E) + T096 (J02).

### Within Each Track

- Track A: T005-T008 (migration + models) → T009-T014 (MockLLMProvider greenfield) → T015-T021 (service method extensions) → T022-T024 (schemas + audit events) → T025-T035 (11 new endpoints) → T036-T040 (5 integration test files).
- Track B: T041-T044 (shared components) → T045-T053 (API + Zod + hooks) → T054-T080 (5 pages + ~30 sub-components + wizard extension — highly parallel by feature) → T081 (ExecutionDrilldown extension) → T082-T087 (i18n + axe + Playwright).
- Track C: T088 (conftest) → T089-T095 (7 E2E files, parallel) → T096 (J02 extension) → T097-T099 (matrix CI).

### Parallel Opportunities

- **Day 1**: T001-T004 (Setup, all parallel) + T005-T008 (Track A migration + models) + T041 (Track B YamlJsonEditor — start with placeholder schemas).
- **Day 2-3**: Track A T009-T024 sequential within sub-clusters; Track B T045-T053 (hooks) parallel; Track B T054-T060 (profile editor) parallel by sub-component.
- **Day 4-5**: Track A T025-T040 (endpoints + tests); Track B T064-T080 (contract editor + library + wizard — highly parallel across 2 devs); Track C T088-T095 (7 E2E files — highly parallel).
- **Day 6**: Track B T082-T087 (i18n + axe + Playwright); Track C T096-T099 (J02 extension + matrix CI).
- **Day 7-9**: Phase 5 verification + Phase 6 polish (mostly parallel — runbooks + dev-guide pages parallel).

---

## Implementation Strategy

### MVP First (US1 + US4 + US5 — Profile Editor + Contract Editor + Mock Preview)

1. Complete Phase 1 (W19.0) Setup.
2. Complete Phase 2 partial (W19A) Track A — migration + MockLLMProvider greenfield (T005-T014) + preview methods (T015, T019) + preview endpoints (T025, T030) + schemas (T029, T034).
3. Complete Phase 3 partial (W19B) Track B — shared scaffolding + hooks + profile editor + contract editor + preview panel (T041-T068).
4. Run T089, T092, T093 (E2E for US1 + US4 + US5).
5. **STOP and VALIDATE**: a creator can author a profile + contract with Monaco editors + run preview via MockLLMProvider per Rule 50 with no real-LLM calls per SC-001 + SC-006 + SC-011.

### Incremental Delivery

1. MVP (US1 + US4 + US5) → demo creator-side editors with mock preview.
2. + US2 (T081, T091) → demo `<ProvenanceViewer>` reusable on ExecutionDrilldown Context tab.
3. + US3 (T016-T018, T026-T028, T061-T063, T090) → demo profile versioning with rollback.
4. + US6 (T020, T031-T032, T071-T074, T094) → demo contract template library + fork.
5. + US7 (T021, T033, T069, T075-T080, T095) → demo wizard publishes agent with profile + contract.
6. Full feature complete after Phase 5 + Phase 6 polish.

### Parallel Team Strategy

With 3 devs:

- **Dev A (Track A backend keystone)**: Days 1-4 Track A entire scope (migration + MockLLMProvider greenfield + service extensions + endpoints + tests); Days 5-6 cross-cutting verification (Phase 5); Days 7-9 Phase 6 SC verification + Rule 50 runbook.
- **Dev B (Track B UI — pages 1-3)**: Day 1 Track B shared scaffolding + hooks; Days 2-4 profile editor + history + contract editor (T054-T070); Days 5-6 i18n + axe-core (T082-T086); Day 7 Playwright (T087).
- **Dev C (Track B UI — pages 4-5 + Track C)**: Days 2-4 contract template library + wizard extension + ExecutionDrilldown extension (T071-T081); Days 5-6 Track C E2E suite + J02 extension + matrix CI (T088-T099); Days 7-9 Phase 6 dev-guide + admin-guide pages.

Wall-clock: **5-6 days for MVP** (US1 + US4 + US5); **8-10 days for full feature** with 3 devs in parallel.

---

## Notes

- [P] tasks = different files, no dependencies; safe to parallelize across devs.
- [Story] label maps task to specific user story for traceability (US1-US7).
- [W19X] label maps task to wave-19 sub-track (W19.0 / W19A-E).
- The plan's effort estimate (11-12 dev-days) supersedes the brownfield's 5-day understatement; tasks below total ~117 entries, consistent with that estimate.
- **Track A's foundational MockLLMProvider per Constitution Rule 50 is the highest-risk piece**; rushing it risks rework + Rule 50 invariant violations. Plan ≥ 1.5 dev-days. T009-T014 + T100 verification are mandatory.
- Rule 50 (mock LLM provider for creator previews) is verified by T100's invariant tests: real_llm_calls_total metric does NOT increment, mock_llm.fallback_used logs emitted for fixture-coverage tracking, opt-in real-LLM rejected without cost_acknowledged.
- Rule 9 (PII operations emit audit) is enforced by T024 wiring 7 new event types + T101 verification.
- Rule 41 (AA accessibility) is verified by T085 axe-core scan + T102 manual Monaco keyboard-nav test.
- Rule 45 (every backend capability has UI) is the canonical anchor — T103 verifies the mapping holistically.
- The 11 new endpoints + 7 service method extensions = 18 net-new backend additions; the existing 16 context-engineering + 8 contract = 24 endpoints + 33 service methods are PRESERVED unchanged.
- The MockLLMProvider greenfield primitive per Rule 50 is REUSABLE by future creator-preview flows (evaluation, simulation, A/B testing) — extensible canned-response fixtures.
- **UPD-044 is the FIRST feature of the v1.4.0 cycle** (after UPD-043 closed v1.3.0 at Wave 18).
