# Implementation Plan: UPD-044 — Creator-Side UIs: Context Engineering and Agent Contracts

**Branch**: `094-creator-context-contracts-ui` | **Date**: 2026-04-27 | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

## Summary

UPD-044 is the FIRST feature of the v1.4.0 cycle (Wave 19, after UPD-043 closed v1.3.0 at Wave 18) and a **mostly-UI gap-fill** with one significant greenfield primitive: the `MockLLMProvider` per Constitution Rule 50 (`.specify/memory/constitution.md:282-286` — verified per research R14). The brownfield's framing of UPD-044 as "almost entirely frontend work — the backend is proven" is INCORRECT per spec correction §1+§2+§4+§6+§14: 4 backend gaps require new code (mock LLM provider, profile versioning, contract-to-revision FK, schema endpoints). Three parallelizable tracks converge for journey-test verification:

- **Track A — Backend additions + greenfield mock LLM** (~4 dev-days): Alembic migration `072_creator_context_contracts.py` (next slot per research R12 — UPD-043 owns 071) introducing NEW `context_engineering_profile_versions` table per spec correction §2 (versioning is greenfield) + NEW `attached_revision_id` column on `AgentContract` per spec correction §5 + NEW `contract_templates` table per spec correction §13 (template library is greenfield — no existing pattern). NEW `mock_llm/` BC at `apps/control-plane/src/platform/mock_llm/` with `MockLLMProvider` (Pydantic-based deterministic mock, canned responses keyed on input hashing, 5 fixture responses) + `provider.py` + `service.py` + `fixtures.yaml` per Rule 50 + spec correction §6. EXTENDS the existing `ContextEngineeringService` (verified — 20 existing methods per research R1) with 4 new methods: `preview_retrieval`, `rollback_to_version`, `get_profile_versions`, `get_version_diff`. EXTENDS the existing `ContractService` (verified — 13 existing methods per research R2) with 3 new methods: `preview_contract`, `fork_template`, `attach_to_revision`. 11 net-new endpoints (4 context-engineering + 4 contract + 2 schema + 1 enums per spec correction §1+§4+§14+§15). 7 new audit-event types under the NEW `creator.{domain}.{action}` convention.

- **Track B — Frontend pages + Monaco-based editors** (~5 dev-days): 5 NEW Next.js pages under `/agent-management/[fqn]/{context-profile,contract}/` + library route per spec correction §5 (entire route tree is new — verified). Reuses the existing Monaco precedent at `apps/web/components/features/workflows/editor/MonacoYamlEditor.tsx` per research R6 (canonical pattern: dynamic import + monaco-yaml + schema validation provider). NEW `<YamlJsonEditor>` shared component generalizes the workflow editor for contracts/profiles. NEW `<ProvenanceViewer>` reusable on (a) profile-editor Test tab AND (b) `<ExecutionDrilldown>` Context tab per spec correction §9 — extends the existing 4-tab drilldown (`trajectory`/`checkpoints`/`debate`/`react` per research R4) with a new 5th `context` tab. NEW `<VersionHistory>` component for profile rollback (greenfield per spec correction §2). EXTENDS the existing `CompositionWizard` (4-step today: Describe / Review / Customize / Validate per research R3) with 5 NEW steps (Context Profile / Test Profile / Contract / Preview Contract / Attach Both) per FR-674 + User Story 7. ~30 sub-components; ~80 i18n keys × 6 locales = 480 entries; axe-core AA scan + keyboard-navigable Monaco per Rule 41 + spec SC-019.

- **Track C — E2E + journey extension** (~2 dev-days): EXTENDS the existing 579-line skeleton `tests/e2e/journeys/test_j02_creator_to_publication.py` (verified — single async function at line 154 with ~5 existing assertion points per research R9) with ≥ 25 NEW assertion points per FR-674. NEW `tests/e2e/suites/creator_uis/` with 7 test files (one per User Story 1-7). Matrix-CI inheritance from UPD-040 for 3 secret modes.

The three tracks converge at Phase 7 for SC verification + auto-doc verification. **Effort estimate: 11-12 dev-days** (the brownfield's "5 days (5 points)" understates by ~50% — consistent with v1.3.0 cohort pattern; brownfield understates because: (a) does NOT account for the foundational `MockLLMProvider` greenfield primitive — Constitution Rule 50 + spec correction §6 — adds ~1.5 dev-days; (b) misses the greenfield profile versioning per spec correction §2 — adds ~1 dev-day; (c) misses the greenfield template library per spec correction §13 — adds ~0.5 day; (d) misses the contract-to-revision FK migration + endpoint per spec correction §5 — adds ~0.5 day; (e) the 7 audit-event types + 11 new endpoints + Pydantic schema generation + JSON-Schema-export endpoints add ~1 day; (f) J02 needs major extension (existing is 579-line skeleton with only 1 async function per research R9) — adds ~1 day vs the brownfield's "extend journey" implicit 0.5 day. Wall-clock with 3 devs in parallel: **~5-6 days**.

## Constitutional Anchors

This plan is bounded by the following Constitution articles + FRs. Each implementation step below cites the article it serves.

| Anchor | Citation | Implementation tie |
|---|---|---|
| **UPD-044 declared** | Audit-pass roster (Wave 19, first of v1.4.0 cycle) | The whole feature |
| **Rule 9 — Every PII operation emits an audit chain entry** | `.specify/memory/constitution.md` (verified existing) | Track A's 7 new audit-event types under `creator.{domain}.{action}` convention |
| **Rule 41 — Accessibility AA** | `.specify/memory/constitution.md` | Track B's Monaco editor MUST be keyboard-navigable per spec SC-019; axe-core CI gate per UPD-083 inheritance |
| **Rule 45 — Every user-facing backend capability has UI** | `.specify/memory/constitution.md:258-262` | THE canonical anchor — the existing 16 context-engineering + 8 contract endpoints have NO creator UI today |
| **Rule 50 — Mock LLM provider for creator previews** | `.specify/memory/constitution.md:282-286` (verified verbatim per research R14) | Track A's foundational `MockLLMProvider` greenfield primitive per spec correction §6 — first production implementation of Rule 50. Real-LLM preview is opt-in with explicit cost confirmation per User Story 5 acceptance scenario 5. |
| **FR-667 — Context Engineering Profile Editor** | FR doc lines 3568+ (verified per spec correction §11) | Track B's `/agent-management/{fqn}/context-profile/page.tsx` |
| **FR-668 — Context Profile Provenance Viewer** | FR doc | Track B's `<ProvenanceViewer>` reusable on profile Test tab + `<ExecutionDrilldown>` Context tab |
| **FR-669 — Context Profile Version Management** | FR doc | Track A's `context_engineering_profile_versions` table + 4 endpoints + Track B's `<VersionHistory>` component |
| **FR-670 — Agent Contract Authoring Page** | FR doc | Track B's `/agent-management/{fqn}/contract/page.tsx` with Monaco YAML/JSON toggle |
| **FR-671 — Contract Preview and Test** | FR doc | Track A's `MockLLMProvider` + `POST /contracts/{id}/preview` endpoint |
| **FR-672 — Contract Library and Templates** | FR doc | Track A's `contract_templates` table + 2 endpoints + Track B's `/contracts/library/page.tsx` |
| **FR-673 — Contract Attachment and Enforcement** | FR doc | Track A's NEW `attached_revision_id` FK + endpoint per spec correction §5 |
| **FR-674 — Creator-Side UI E2E Coverage** | FR doc | Track C's J02 extension to ≥ 25 assertion points + 7 suite tests |

**Verdict: gate passes. No declared variances.** UPD-044 satisfies all four constitutional rules + the FR-667-FR-674 contract.

## Technical Context

| Item | Value |
|---|---|
| **Languages** | Python 3.12 (control plane — extension of `context_engineering/service.py` + `trust/contract_service.py` + new `mock_llm/` BC + Alembic migration); TypeScript 5.x (Next.js 14 — 5 new pages + 30 sub-components + wizard extension); YAML (mock LLM canned-response fixtures). NO Go changes. NO Helm changes. |
| **Primary Dependencies (existing — reused)** | `FastAPI 0.115+`, `pydantic-settings 2.x`, `SQLAlchemy 2.x async`, `aiokafka 0.11+` (audit-event emission), `react 18+`, `next 14`, `shadcn/ui` (existing primitives), `@monaco-editor/react ^4.7.0` + `monaco-yaml ^5.4.1` (verified per spec correction §10 + research R6 — ALREADY in package.json; no new editor library), `@xyflow/react ^12.10.2` + `@dagrejs/dagre ^3.0.0` (existing graph stack — NOT used by UPD-044; provenance viewer is list-based, not graph-based). |
| **Primary Dependencies (NEW in 094)** | NO new runtime dependencies. The MockLLMProvider uses Pydantic + standard library (no LLM SDK calls). Profile-versioning uses existing `SQLAlchemy 2.x async`. The contract-template library uses existing infrastructure. |
| **Storage** | PostgreSQL — Alembic migration `072_creator_context_contracts.py` (next slot per research R12 — UPD-043 owns 071): (a) NEW table `context_engineering_profile_versions` per spec correction §2 + design D1 (columns: `id` UUID PK, `profile_id` FK, `version_number` int, `content_snapshot` JSONB, `change_summary` text, `created_by` FK users, `created_at` timestamptz; UNIQUE constraint on `(profile_id, version_number)`); (b) NEW column `attached_revision_id: UUID | None` on `agent_contracts` per spec correction §5 (FK to `registry_agent_revisions.id` per research R7 ON DELETE SET NULL); (c) NEW table `contract_templates` per spec correction §13 + design D6 (columns: `id` UUID PK, `name` String(255) UNIQUE, `description` text, `category` String(64), `template_content` JSONB, `version_number` int, `forked_from_template_id` UUID FK NULL, `created_by_user_id` UUID FK users NULL — NULL for platform-authored, populated for creator-authored, `is_platform_authored` bool DEFAULT false, `is_published` bool DEFAULT false). NO new Redis keys. NO Vault paths. NO MinIO buckets. |
| **Testing** | `pytest 8.x` + `pytest-asyncio` (control plane unit tests for 11 new endpoints + 7 service methods + `MockLLMProvider` — ~50+ test cases); Playwright (Next.js page E2E for 5 pages + wizard extension — ~20+ scenarios); axe-core CI gate per Rule 41; pytest E2E suite at `tests/e2e/suites/creator_uis/` — 7 test files. J02 extension (~25+ NEW assertion blocks added to existing 579-line skeleton per spec correction §9 + research R9). Matrix-CI inheritance from UPD-040: `secret_mode: [mock, kubernetes, vault]` × `creator_uis` suite. |
| **Target Platform** | Linux x86_64 Kubernetes 1.28+ (control plane); Next.js 14 server + browser (web app); modern browsers supporting Monaco Editor (Chrome 90+, Firefox 90+, Safari 14+). |
| **Project Type** | Cross-stack feature: (a) Python control plane (`apps/control-plane/` — 2 BC extensions + 1 NEW `mock_llm/` BC); (b) Next.js frontend (`apps/web/` — 5 new pages + 30 sub-components + wizard extension + Monaco-based editors); (c) E2E test scaffolding. NO Helm/Go changes. |
| **Performance Goals** | Profile editor Monaco load ≤ 2 seconds with JSON Schema fetched + validation provider configured per SC-001; profile preview via `MockLLMProvider` ≤ 2 seconds (canned-response lookup + minimal mock processing) per SC-003; provenance viewer renders ≤ 50 source rows in ≤ 500ms per User Story 2 + Rule 41 (60fps virtualization for large lists); version diff renders in ≤ 1 second for typical profile JSONB (< 100KB) per SC-007; contract preview via `MockLLMProvider` ≤ 3 seconds (mock + clause evaluation) per SC-011. |
| **Constraints** | Rule 45 — every backend capability has UI (verified by mapping each Track A endpoint to a Track B page); Rule 50 — mock LLM provider is the default; real-LLM preview is opt-in with explicit cost confirmation per User Story 5 acceptance scenario 5; Rule 41 — Monaco MUST be keyboard-navigable + screen-reader-accessible (Monaco's built-in keyboard support + accessible labels on toolbar buttons); FR-672 — fork attribution is immutable (`forked_from_template_id` cannot be modified after creation). |
| **Scale / Scope** | Track A: ~7 NEW Python service methods (4 context-engineering + 3 contract) + 11 NEW endpoints + 1 NEW `mock_llm/` BC (~400 lines including provider + service + fixtures) + 1 Alembic migration (~120 lines) + ~150 lines of Pydantic schemas + 7 NEW audit-event payload classes + ~50 unit tests. Track B: 5 NEW pages (~250 lines × 5 = ~1250 lines) + ~30 NEW shared sub-components (~80 lines × 30 = ~2400 lines including `<YamlJsonEditor>`, `<ProvenanceViewer>`, `<VersionHistory>`, source picker, retrieval strategy selector, reranking rules editor, context budget controls, contract preview panel, contract template card, etc.) + wizard extension (~200 lines net diff to `CompositionWizard.tsx`) + ExecutionDrilldown extension (~50 lines net diff to add Context tab) + 6 i18n catalogs × ~80 strings each = ~480 i18n entries + ~20 Playwright scenarios. Track C: 7 NEW E2E test files (~80 lines each = ~560 lines) + J02 extension (~25 NEW assertion blocks ≈ ~150 net lines added to existing 579-line file). **Total: ~5400 lines of new Python + TypeScript + YAML + ~480 i18n entries; ~50 NEW files + ~10 MODIFIED files.** |

## Constitution Check

> **GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.**

| Check | Verdict | Rationale |
|---|---|---|
| Brownfield rule — modifications respect existing repo discipline | ✅ Pass | UPD-044 (a) EXTENDS the existing 20-method `ContextEngineeringService` (verified per research R1) with 4 new methods; (b) EXTENDS the existing 13-method `ContractService` (verified per research R2) with 3 new methods; (c) EXTENDS the existing 4-step `CompositionWizard` (verified per research R3) with 5 new steps; (d) EXTENDS the existing 4-tab `<ExecutionDrilldown>` (verified per research R4) with 1 new "Context" tab; (e) PRESERVES the existing 16 context-engineering endpoints + 8 contract endpoints + 4 wizard steps + 4 drilldown tabs unchanged; (f) ADDS the new `mock_llm/` BC as a foundational greenfield primitive per Constitution Rule 50. |
| Rule 9 — every PII operation emits audit chain entry | ✅ Pass | All 7 new audit-event types follow the existing dual-emission pattern (`repository.create_audit_entry` + `publish_auth_event` per UPD-040 / UPD-042 / UPD-043 research). |
| Rule 41 — Accessibility AA | ✅ Pass | Track B's Monaco editor inherits the existing `MonacoYamlEditor.tsx` accessibility patterns (keyboard nav, screen reader labels) per research R6; axe-core CI gate per UPD-083 inheritance; all 5 new pages MUST pass AA. |
| Rule 45 — every user-facing backend capability has UI | ✅ Pass | THE canonical anchor — UPD-044 IS the Rule 45 gap-fill for the context-engineering + contract backends. Every Track A endpoint maps to a Track B page (verified by spec Key Entities section). |
| Rule 50 — Mock LLM provider for creator previews | ✅ Pass (FOUNDATIONAL — first implementation) | Track A's `MockLLMProvider` is the FIRST production implementation of Rule 50. Greenfield per spec correction §6 — does not exist today (zero matches for `mock_llm`, `MockProvider`, `MockModel` in the codebase). The canned-response fixture file ensures deterministic outputs; real-LLM preview is opt-in with explicit cost confirmation per User Story 5 acceptance scenario 5. |

**Verdict: gate passes. No declared variances. UPD-044 satisfies Rules 9, 41, 45, 50.**

## Project Structure

### Documentation (this feature)

```text
specs/094-creator-context-contracts-ui/
├── plan.md                # this file
├── spec.md
├── planning-input.md
└── tasks.md               # produced by /speckit.tasks (next phase)
```

### Source Code (repository root) — files this feature creates or modifies

```text
# === Track A — Backend additions + greenfield mock LLM ===
apps/control-plane/migrations/versions/072_creator_context_contracts.py  # NEW — Alembic migration adding 1 NEW table (context_engineering_profile_versions) + 1 NEW column (attached_revision_id on agent_contracts) + 1 NEW table (contract_templates)
apps/control-plane/src/platform/context_engineering/models.py            # MODIFY — adds NEW ContextProfileVersion model per spec correction §2
apps/control-plane/src/platform/context_engineering/service.py           # MODIFY — adds 4 new public methods (preview_retrieval per FR-667, rollback_to_version + get_profile_versions + get_version_diff per FR-669); preserves the existing 20 methods unchanged per research R1
apps/control-plane/src/platform/context_engineering/router.py            # MODIFY — adds 4 new endpoints + 1 schema endpoint
apps/control-plane/src/platform/context_engineering/schemas.py           # MODIFY — adds NEW Pydantic schemas (PreviewRequest, PreviewResponse, VersionHistoryResponse, VersionDiffResponse, RollbackRequest)
apps/control-plane/src/platform/trust/models.py                          # MODIFY — adds NEW attached_revision_id column on AgentContract (lines 163-191 per research R7) + NEW ContractTemplate model per spec correction §13
apps/control-plane/src/platform/trust/contract_service.py                # MODIFY — adds 3 new public methods (preview_contract per FR-671, fork_template per FR-672, attach_to_revision per FR-673); preserves the existing 13 methods unchanged per research R2
apps/control-plane/src/platform/trust/router.py                          # MODIFY — adds 4 new endpoints (1 preview + 2 template + 1 attach-revision) + 1 schema endpoint + 1 enums endpoint
apps/control-plane/src/platform/trust/contract_schemas.py                # MODIFY — adds NEW Pydantic schemas (PreviewRequest, PreviewResponse, ForkRequest, AttachRevisionRequest, ContractTemplateResponse)
apps/control-plane/src/platform/mock_llm/__init__.py                     # NEW — module marker
apps/control-plane/src/platform/mock_llm/provider.py                     # NEW (~150 lines) — MockLLMProvider Pydantic-based deterministic mock per Constitution Rule 50; canned responses keyed on input hashing; implements same Protocol as real providers per research R5
apps/control-plane/src/platform/mock_llm/service.py                      # NEW (~120 lines) — MockLLMService drop-in replacement for the real LLM service when invoked from preview endpoints
apps/control-plane/src/platform/mock_llm/fixtures.yaml                   # NEW — canned response fixtures (5 default scenarios: customer-support, code-review, data-analysis, content-generation, generic-fallback)
apps/control-plane/src/platform/mock_llm/schemas.py                      # NEW (~80 lines) — Pydantic schemas for canned responses
apps/control-plane/tests/mock_llm/test_provider.py                       # NEW — pytest tests for MockLLMProvider (~12 cases covering deterministic responses + fallback + Rule 50 invariants)
apps/control-plane/tests/context_engineering/test_versioning.py          # NEW — pytest tests for greenfield versioning (~10 cases)
apps/control-plane/tests/context_engineering/test_preview.py             # NEW — pytest tests for preview endpoint (~6 cases)
apps/control-plane/tests/trust/test_contract_preview.py                  # NEW — pytest tests for contract preview via MockLLMProvider (~8 cases)
apps/control-plane/tests/trust/test_contract_templates.py                # NEW — pytest tests for template fork + upstream-update (~6 cases)
apps/control-plane/tests/trust/test_attach_to_revision.py                # NEW — pytest tests for new revision attachment (~5 cases)

# === Track B — Frontend pages + Monaco-based editors ===
apps/web/app/(main)/agent-management/[fqn]/context-profile/page.tsx      # NEW (~250 lines) — context profile editor per FR-667
apps/web/app/(main)/agent-management/[fqn]/context-profile/_components/ContextProfileEditor.tsx  # NEW (~400 lines) — top-level editor composing sub-components
apps/web/app/(main)/agent-management/[fqn]/context-profile/_components/SourcePicker.tsx  # NEW (~200 lines) — workspace-visibility-filtered source picker
apps/web/app/(main)/agent-management/[fqn]/context-profile/_components/RetrievalStrategySelector.tsx  # NEW (~120 lines) — per-source strategy picker (semantic/graph/FTS/hybrid)
apps/web/app/(main)/agent-management/[fqn]/context-profile/_components/RerankingRulesEditor.tsx  # NEW (~200 lines) — drag-reorderable rules list
apps/web/app/(main)/agent-management/[fqn]/context-profile/_components/ContextBudgetControls.tsx  # NEW (~150 lines) — max tokens / docs / per-source fractions
apps/web/app/(main)/agent-management/[fqn]/context-profile/_components/TestQueryPanel.tsx  # NEW (~180 lines) — test-with-query panel embedding `<ProvenanceViewer>`
apps/web/app/(main)/agent-management/[fqn]/context-profile/history/page.tsx  # NEW (~200 lines) — version history page per FR-669
apps/web/app/(main)/agent-management/[fqn]/context-profile/history/_components/VersionList.tsx  # NEW (~150 lines)
apps/web/app/(main)/agent-management/[fqn]/context-profile/history/_components/VersionDiffViewer.tsx  # NEW (~250 lines) — side-by-side JSON diff with green/red highlights
apps/web/app/(main)/agent-management/[fqn]/contract/page.tsx             # NEW (~250 lines) — contract authoring editor per FR-670
apps/web/app/(main)/agent-management/[fqn]/contract/_components/ContractEditor.tsx  # NEW (~400 lines) — Monaco YAML/JSON toggle wrapping `<YamlJsonEditor>`
apps/web/app/(main)/agent-management/[fqn]/contract/_components/ContractPreviewPanel.tsx  # NEW (~250 lines) — sample input + result inspector
apps/web/app/(main)/agent-management/[fqn]/contract/_components/SampleInputManager.tsx  # NEW (~180 lines) — saved samples + load/save
apps/web/app/(main)/agent-management/[fqn]/contract/_components/RealLLMOptInDialog.tsx  # NEW (~150 lines) — explicit confirmation per Rule 50 + User Story 5 acceptance scenario 5
apps/web/app/(main)/agent-management/[fqn]/contract/_components/AttachToRevisionDialog.tsx  # NEW (~150 lines) — per FR-673 + spec correction §5
apps/web/app/(main)/agent-management/[fqn]/contract/history/page.tsx     # NEW (~180 lines) — contract change history
apps/web/app/(main)/agent-management/contracts/library/page.tsx          # NEW (~250 lines) — template library per FR-672
apps/web/app/(main)/agent-management/contracts/library/_components/TemplateCard.tsx  # NEW (~150 lines)
apps/web/app/(main)/agent-management/contracts/library/_components/ForkDialog.tsx  # NEW (~180 lines)
apps/web/components/features/agents/YamlJsonEditor.tsx                   # NEW (~250 lines) — shared Monaco wrapper modeled on existing `MonacoYamlEditor.tsx` per research R6; supports YAML/JSON toggle + JSON Schema validation provider + auto-completion
apps/web/components/features/agents/ProvenanceViewer.tsx                 # NEW (~300 lines) — reusable component for profile Test tab + ExecutionDrilldown Context tab; renders sources in descending score with origin/snippet/score/included-flag/classification badges
apps/web/components/features/agents/VersionHistory.tsx                   # NEW (~200 lines) — generic version history component (greenfield primitive — no existing precedent per research R13)
apps/web/components/features/agents/SchemaValidatedEditor.tsx            # NEW (~200 lines) — generic wrapper around `<YamlJsonEditor>` providing inline validation + auto-completion
apps/web/components/features/agent-management/CompositionWizard.tsx      # MODIFY — extends existing 4-step array (lines 13-18 per research R3) with 5 NEW steps; the existing 4 steps preserved unchanged
apps/web/components/features/agent-management/wizard/WizardStepContextProfile.tsx  # NEW (~200 lines) — step 5
apps/web/components/features/agent-management/wizard/WizardStepTestProfile.tsx  # NEW (~150 lines) — step 6
apps/web/components/features/agent-management/wizard/WizardStepContract.tsx  # NEW (~200 lines) — step 7
apps/web/components/features/agent-management/wizard/WizardStepPreviewContract.tsx  # NEW (~150 lines) — step 8
apps/web/components/features/agent-management/wizard/WizardStepAttachBoth.tsx  # NEW (~180 lines) — step 9
apps/web/components/features/operator/ExecutionDrilldown.tsx             # MODIFY — adds NEW "context" tab to the existing 4-tab structure per research R4; renders `<ProvenanceViewer>`. The existing 4 tabs (trajectory/checkpoints/debate/react) preserved unchanged.
apps/web/lib/api/creator-uis.ts                                          # NEW — fetch wrappers for 11 new endpoints
apps/web/lib/schemas/creator-uis.ts                                      # NEW — Zod schemas (or runtime fetched from new schema endpoints)
apps/web/lib/hooks/use-context-profile-versions.ts                       # NEW — TanStack Query hook
apps/web/lib/hooks/use-context-profile-preview.ts                        # NEW
apps/web/lib/hooks/use-contract-preview.ts                               # NEW
apps/web/lib/hooks/use-contract-templates.ts                             # NEW
apps/web/lib/hooks/use-contract-schema.ts                                # NEW — fetches JSON Schema for live Monaco validation
apps/web/lib/hooks/use-profile-schema.ts                                 # NEW — fetches profile JSON Schema
apps/web/lib/hooks/use-schema-enums.ts                                   # NEW — fetches resource/role enums for contract auto-complete
apps/web/messages/en.json                                                # MODIFY — adds ~80 new i18n keys under `creator.{contextProfile,contract,template}.*` namespaces
apps/web/messages/{de,es,fr,it,zh-CN,ja}.json                            # MODIFY — translated catalogs (vendor-handled per UPD-039)
apps/web/tests/e2e/creator-uis-pages.spec.ts                             # NEW — Playwright tests (~20 scenarios)

# === Track C — E2E + journey extension ===
tests/e2e/suites/creator_uis/__init__.py                                 # NEW
tests/e2e/suites/creator_uis/conftest.py                                 # NEW — shared fixtures (creator_with_agent, creator_with_profile, creator_with_contract, mock_llm_responses, contract_template_seeded)
tests/e2e/suites/creator_uis/test_profile_editor.py                      # NEW — User Story 1 (~5 cases)
tests/e2e/suites/creator_uis/test_profile_rollback.py                    # NEW — User Story 3 (~5 cases)
tests/e2e/suites/creator_uis/test_provenance_viewer.py                   # NEW — User Story 2 (~4 cases)
tests/e2e/suites/creator_uis/test_contract_editor.py                     # NEW — User Story 4 (~5 cases)
tests/e2e/suites/creator_uis/test_contract_preview.py                    # NEW — User Story 5 (~5 cases — verifies MockLLMProvider invocation per Rule 50)
tests/e2e/suites/creator_uis/test_template_fork.py                       # NEW — User Story 6 (~4 cases)
tests/e2e/suites/creator_uis/test_publish_with_profile_and_contract.py   # NEW — User Story 7 (~6 cases)
tests/e2e/journeys/test_j02_creator_to_publication.py                    # MODIFY — extends existing single async function at line 154 (per research R9) with ≥ 25 NEW assertion blocks per FR-674
.github/workflows/ci.yml                                                 # MODIFY — adds tests/e2e/suites/creator_uis/ to UPD-040's matrix-CI test path
```

**Structure decision**: UPD-044 follows the brownfield repo discipline. The new `/agent-management/[fqn]/context-profile/*` and `/contract/*` UI route trees are colocated with the existing `[fqn]/` route group (verified per research R10 — sibling routes to existing `page.tsx` + `revisions/`). The new `/agent-management/contracts/library/` is at a separate level (not under `[fqn]/` because the library is workspace-global, not agent-specific). The 5 NEW pages each have `_components/` subdirectories for page-scoped sub-components per the UPD-042/043 precedent. The new `mock_llm/` BC at `apps/control-plane/src/platform/mock_llm/` follows the existing BC pattern (models + provider + service + schemas + fixtures + tests). NO new BCs introduced beyond `mock_llm/`; existing BCs (context_engineering, trust) are extended.

## Phase 0 — Research

> Research notes captured during plan authoring. Each item resolves a specific design question.

- **R1 — Context engineering service surface [RESEARCH-COMPLETE]**: Verified at `context_engineering/service.py:103-1031` per research R1. 20 existing public methods. **Resolution**: Track A adds 4 new methods AFTER existing methods to keep the service file's logical grouping intact: `preview_retrieval(profile_id, query_text)` (FR-667), `get_profile_versions(profile_id, limit, cursor)` (FR-669), `get_version_diff(profile_id, v1_number, v2_number)` (FR-669), `rollback_to_version(profile_id, target_version_number, requester_id)` (FR-669).

- **R2 — Contract service surface [RESEARCH-COMPLETE]**: Verified at `trust/contract_service.py:32-392` per research R2. 13 existing public methods. **Resolution**: Track A adds 3 new methods: `preview_contract(contract_id, sample_input, use_mock=True)` (FR-671 + Rule 50), `fork_template(template_id, new_name, workspace_id, requester_id)` (FR-672), `attach_to_revision(contract_id, revision_id, requester_id)` (FR-673).

- **R3 — `CompositionWizard` extension pattern [RESEARCH-COMPLETE]**: Verified at `apps/web/components/features/agent-management/CompositionWizard.tsx:13-67` per research R3. Existing 4 steps with named labels in `STEP_LABELS` array + conditional rendering at lines 48-67. **Resolution**: Track B EXTENDS the array with 5 new entries (Context Profile / Test Profile / Contract / Preview Contract / Attach Both) + adds 5 new conditional render branches. Each new step is a separate component per the existing pattern. Backward compatibility: low-trust-tier agents skip steps 5-9 by default; high-trust-tier agents have validation gates.

- **R4 — `<ExecutionDrilldown>` extension pattern [RESEARCH-COMPLETE]**: Verified at `apps/web/components/features/operator/ExecutionDrilldown.tsx:22-29` per research R4. Existing 4 tabs (`trajectory`, `checkpoints`, `debate`, `react`). **Resolution**: Track B EXTENDS the `DrilldownTab` union + `VALID_TABS` set with `"context"`. Adds NEW `<TabsContent value="context">` block rendering `<ProvenanceViewer executionId={executionId} />`. The existing 4 tabs preserved unchanged.

- **R5 — Mock LLM provider integration [RESEARCH-COMPLETE]**: Verified at `apps/control-plane/src/platform/common/clients/model_router.py:37-100` per research R5. Existing Protocol-based provider abstraction with `ProviderCall` type alias + `SecretProvider` Protocol + `RedisStickyCache` Protocol. **Resolution**: NEW `MockLLMProvider` at `mock_llm/provider.py` implements the SAME Protocol surface (async response generation matching `ProviderCall` signature). Canned responses keyed on `hashlib.sha256(input).hexdigest()[:16]` for determinism. Fallback: if hash not in fixtures, return generic-fallback response with audit-log marker. Drop-in replacement: `ContextEngineeringService.preview_retrieval` + `ContractService.preview_contract` accept `mock_llm_provider` as injected dependency.

- **R6 — Existing Monaco precedent [RESEARCH-COMPLETE]**: Verified at `apps/web/components/features/workflows/editor/MonacoYamlEditor.tsx` per research R6. Pattern: dynamic import via `next/dynamic` + `monaco-yaml` configuration via `configureMonacoYaml()` + schema validation provider. **Resolution**: NEW `<YamlJsonEditor>` at `apps/web/components/features/agents/YamlJsonEditor.tsx` reuses the EXISTING pattern. Differences: (a) supports YAML/JSON toggle (not YAML-only); (b) fetches JSON Schema from configurable endpoint URL (parameterized); (c) renders error markers + auto-completion suggestions from schema enum values. The brownfield's "Monaco Editor or CodeMirror 6" framing is corrected to "Monaco-only" per spec correction §10.

- **R7 — `AgentRevision` model FK target [RESEARCH-COMPLETE]**: Verified at `apps/control-plane/src/platform/registry/models.py:185-215` per research R7. Table name: `registry_agent_revisions`. Columns: `id` (UUID PK), `workspace_id`, `agent_profile_id` (FK), `version`, `sha256_digest`, `storage_key`, `manifest_snapshot` (JSONB), `uploaded_by`. **Resolution**: NEW FK `attached_revision_id: UUID | None` on `agent_contracts` references `registry_agent_revisions.id` with `ON DELETE SET NULL` per spec correction §5 + design D2 (the brownfield does not specify ON DELETE behavior; SET NULL preserves the contract record + breaks the link if the revision is deleted, audit-friendly).

- **R8 — JSON Schema export from Pydantic [RESEARCH-COMPLETE]**: Verified per research R8 — Pydantic v2 `Model.model_json_schema()` returns dict at runtime. **Resolution**: 2 NEW endpoints: `GET /api/v1/contracts/schema` calls `AgentContractCreate.model_json_schema()`; `GET /api/v1/context-engineering/profiles/schema` calls `ContextProfileCreate.model_json_schema()`. Both endpoints have NO server-side caching (Pydantic schema-export is fast); frontend caches via TanStack Query stale-time = 1 hour. Plus 1 NEW `GET /api/v1/contracts/schema-enums` returning the platform's enumeration sets per spec correction §15 + design D7.

- **R9 — J02 journey extension pattern [RESEARCH-COMPLETE]**: Verified at `tests/e2e/journeys/test_j02_creator_to_publication.py:154` per research R9. Single async function `test_j02_creator_to_publication()` chaining ~5 existing assertion blocks. **Resolution**: Track C EXTENDS the existing function (does NOT add new test functions) with ≥ 25 NEW assertion blocks per FR-674: (1-5) existing register + create-revision + upload + certify + publish; (6-8) NEW context profile create + edit + preview; (9-11) NEW context profile rollback + diff + version pinning; (12-14) NEW contract create + edit + preview; (15-17) NEW contract preview-via-mock + opt-in-real-LLM-rejection-path + violations-link-to-clause; (18-20) NEW template fork + customize + upstream-update-notification; (21-23) NEW attach-profile-to-revision + attach-contract-to-revision + publish-with-both; (24-25) NEW post-publish verification (audit chain entries + revision pinned to profile version + contract attached). Final J02 line count ≈ 750 lines.

- **R10 — `/agent-management/[fqn]/` route group sibling pattern [RESEARCH-COMPLETE]**: Verified per research R10. Existing siblings: `page.tsx` (detail) + `revisions/page.tsx` (revisions list). **Resolution**: Track B adds 2 new sibling subdirectories: `context-profile/` (with `page.tsx` + `history/page.tsx` + `_components/`) and `contract/` (with `page.tsx` + `history/page.tsx` + `_components/`). The agent detail page (`page.tsx`) gets a navigation link / tab to the new pages — exact UI pattern decided in T035 of tasks (modify `page.tsx` to add nav link).

- **R11 — Tool registry endpoint for auto-complete [RESEARCH-COMPLETE]**: Verified at `mcp/router.py:113-127` per research R11. `GET /exposed-tools` accepts `is_exposed`, `page`, `page_size` query params + returns paginated tool list with FQNs + metadata. **Resolution**: Contract editor's auto-complete consumes this endpoint via the new `useExposedTools()` hook (TanStack Query). The hook fetches all tools (paginated transparently) for the workspace; Monaco's `provideCompletionItems` callback returns FQNs as suggestions when the cursor is on the `task_scope.tools.allowed` field path.

- **R12 — Migration sequence [RESEARCH-COMPLETE]**: Verified per research R12. UPD-043 owns `071_workspace_owner_workbench.py`. **Resolution**: UPD-044's migration is `072_creator_context_contracts.py`. Revision chain: `revises = "071_workspace_owner_workbench"`. The migration adds 2 new tables (`context_engineering_profile_versions`, `contract_templates`) + 1 new column (`attached_revision_id` on `agent_contracts`).

- **R13 — Template library greenfield [RESEARCH-COMPLETE]**: Verified per research R13. Zero existing template patterns in the codebase. **Resolution**: NEW `ContractTemplate` model + 2 endpoints + library page are GREENFIELD per spec correction §13. The 5 platform-authored templates (customer-support / code-review / data-analysis / db-write / external-api-call) are seeded by the migration's `op.execute(...)` data-migration step OR via a separate `platform-cli admin contract-templates seed` command — the plan phase decides per design D6 (default: data-migration in the same Alembic file).

- **R14 — Constitution Rule 50 verbatim [RESEARCH-COMPLETE]**: Quoted at `.specify/memory/constitution.md:282-286` per research R14: "Mock LLM provider for creator previews. Context profile previews, contract previews, and any test-time execution that could otherwise cost money or produce side effects MUST default to the mock LLM provider. Real-LLM preview is an explicit opt-in with a clear cost indicator." **Resolution**: This is the canonical anchor for Track A's `MockLLMProvider`. Real-LLM preview is implemented as an opt-in with explicit confirmation dialog per User Story 5 acceptance scenario 5 + design D5.

## Phase 1 — Design Decisions

> Implementation tasks (in tasks.md) MUST honour these decisions or escalate via spec amendment.

### D1 — Context profile versioning: NEW dedicated `_versions` table

Per spec correction §2 + research R1. NEW `context_engineering_profile_versions` table with `(profile_id, version_number)` UNIQUE constraint. Each save creates a new row; `version_number` is monotonically increasing per profile. The existing `ContextEngineeringProfile` row remains the "current" pointer (via the latest version_number); rollback creates a new version with the rolled-back content (NEVER destructive). Diff is computed on-the-fly from the JSONB `content_snapshot` columns.

### D2 — Contract-revision attachment: NEW FK with ON DELETE SET NULL

Per spec correction §5 + research R7. NEW `attached_revision_id: UUID | None` column on `agent_contracts` with FK to `registry_agent_revisions.id` and `ON DELETE SET NULL`. Reasoning: SET NULL preserves the contract record (auditable) but breaks the link if the revision is deleted; this is consistent with the existing UPD-006 pattern of contracts being workspace-scoped + agent-scoped (FQN string) without revision binding at runtime.

### D3 — `MockLLMProvider`: deterministic canned responses keyed on input hashing

Per Constitution Rule 50 + spec correction §6 + research R5. The provider hashes the input via `hashlib.sha256(input).hexdigest()[:16]` and looks up in `fixtures.yaml`. Fixture format: `{hash: response_dict}`. 5 default scenarios for the most-common preview inputs (customer-support, code-review, data-analysis, content-generation, generic-fallback). Fallback to generic-fallback for unknown hashes (with structured-log entry `mock_llm.fallback_used` for fixture-coverage tracking).

### D4 — Schema endpoints serve Pydantic-generated JSON Schema at runtime

Per spec correction §14 + research R8. `GET /contracts/schema` calls `AgentContractCreate.model_json_schema()`; `GET /context-engineering/profiles/schema` calls `ContextProfileCreate.model_json_schema()`. NO server-side caching (Pydantic export is microsecond-scale); frontend caches via TanStack Query stale-time = 1 hour. The schemas include enum values inline; the auto-complete UI extracts them via Monaco's schema validation provider hooks.

### D5 — Real-LLM preview opt-in with explicit confirmation

Per Rule 50 + User Story 5 acceptance scenario 5. The `POST /contracts/{id}/preview` endpoint accepts `use_mock: bool = True` (default true). When `use_mock=false`, the endpoint requires an additional `cost_acknowledged: bool = false` parameter; the backend rejects the request with HTTP 400 if `cost_acknowledged != true`. The frontend's `<RealLLMOptInDialog>` component renders a confirmation dialog showing estimated cost + asks the user to type "USE_REAL_LLM" to confirm; on confirm, it calls the endpoint with both params set to true. Audit entry `creator.contract.real_llm_preview_used` emitted.

### D6 — Contract templates seeded via Alembic data-migration

Per spec correction §13 + research R13. The same Alembic migration `072_creator_context_contracts.py` includes an `op.execute(...)` step inserting 5 platform-authored templates into `contract_templates` with `is_platform_authored=true, is_published=true`. The 5 templates (customer-support / code-review / data-analysis / db-write / external-api-call) ship with curated content authored during this feature's plan phase. The migration's downgrade step truncates the seeded rows.

### D7 — `GET /contracts/schema-enums` aggregates platform enumerations

Per spec correction §15. NEW endpoint returns `{resource_types: list[str], role_types: list[str], workspace_constraints: list[str], failure_modes: list[str]}`. Sources: `resource_types` from `policies/models.py` ResourceType enum; `role_types` from `auth/models.py` Role enum; `workspace_constraints` from `workspaces/schemas.py` WorkspaceConstraint enum; `failure_modes` from `trust/contract_schemas.py` FailureMode enum. The endpoint is read-only; no caching needed (small response).

### D8 — `<ProvenanceViewer>` reusable on Test tab AND Context tab

Per spec correction §9 + FR-668 + research R4. The component accepts an `executionId: string | null` prop. On profile editor's Test tab, the prop is null (component reads from preview-result-state); on `<ExecutionDrilldown>` Context tab, the prop is the execution ID and the component fetches via `GET /context-engineering/assembly-records/{record_id}`. Both render identical UI per SC-005 (DRY).

### D9 — `<YamlJsonEditor>` reuses existing Monaco precedent

Per spec correction §10 + research R6. The new component models on the existing `MonacoYamlEditor.tsx` (workflows BC). Generalizes by accepting: `schemaUrl: string` (the JSON Schema fetch URL), `defaultLanguage: "yaml" | "json"`, `enableLanguageToggle: boolean`. The contract editor uses `enableLanguageToggle=true` (per FR-670); the profile editor uses `defaultLanguage="json"` + `enableLanguageToggle=false` (profiles are always JSON per FR-667).

### D10 — UPD-039 documentation integration is BEST-EFFORT

Mirrors UPD-040 / UPD-041 / UPD-042 / UPD-043 design pattern. If UPD-039 has landed, runbooks + admin-guide updates live in `docs/`; if delayed, they live in `specs/094-creator-context-contracts-ui/contracts/` and merge into UPD-039 later.

## Phase 2 — Track A Build Order (Backend additions + greenfield mock LLM)

**Days 1-4 (1 dev). Depends on UPD-040 + UPD-041 + UPD-042 + UPD-043 being on `main`.**

1. **Day 1 morning** — Pre-flight: confirm UPD-040+041+042+043 are merged on `main`; confirm migration sequence at `071_workspace_owner_workbench.py` so `072` is the next slot per research R12.
2. **Day 1 morning** — Author Alembic migration `072_creator_context_contracts.py` per design D1 + D2 + D6: 2 NEW tables (`context_engineering_profile_versions`, `contract_templates`) + 1 NEW column (`attached_revision_id` on `agent_contracts`). Seed 5 platform-authored contract templates via `op.execute(...)`. Reversible downgrade.
3. **Day 1 afternoon** — Run migration locally; verify both upgrade + downgrade work cleanly.
4. **Day 1 afternoon** — Modify `context_engineering/models.py`: add NEW `ContextProfileVersion` model. Modify `trust/models.py`: add NEW `attached_revision_id` column on `AgentContract` (line 163-191 per research R7) + NEW `ContractTemplate` model.
5. **Day 2 morning** — Create NEW `mock_llm/` BC per design D3 + Rule 50: `__init__.py`, `provider.py` (MockLLMProvider with `hashlib.sha256` keying), `service.py` (drop-in service replacement), `fixtures.yaml` (5 canned scenarios), `schemas.py` (Pydantic schemas).
6. **Day 2 afternoon** — Author `apps/control-plane/tests/mock_llm/test_provider.py` (~12 cases) covering deterministic responses, fallback, Rule 50 invariants (real LLM never called).
7. **Day 3 morning** — Modify `context_engineering/service.py` per research R1: add 4 new methods (`preview_retrieval` invoking MockLLMProvider per Rule 50, `get_profile_versions`, `get_version_diff`, `rollback_to_version` per FR-669).
8. **Day 3 morning** — Modify `context_engineering/router.py`: add 5 new endpoints (4 versioning + preview + 1 schema endpoint per design D4).
9. **Day 3 afternoon** — Modify `trust/contract_service.py` per research R2: add 3 new methods (`preview_contract` per Rule 50 + design D5, `fork_template` per FR-672, `attach_to_revision` per FR-673).
10. **Day 3 afternoon** — Modify `trust/router.py`: add 6 new endpoints (1 preview + 2 template + 1 attach-revision + 1 schema + 1 enums per design D7).
11. **Day 4 morning** — Modify `context_engineering/schemas.py` + `trust/contract_schemas.py`: add Pydantic schemas for new endpoints. Verify JSON Schema export via `Model.model_json_schema()` produces valid output.
12. **Day 4 morning** — Wire 7 new audit-event types per spec Key Entities: `creator.context_profile.created`, `creator.context_profile.updated`, `creator.context_profile.rolled_back`, `creator.contract.created`, `creator.contract.preview_executed`, `creator.contract.attached_to_revision`, `creator.contract.forked_from_template`. Each follows the existing dual-emission pattern per UPD-040/042/043 research.
13. **Day 4 afternoon** — Author 5 new pytest test files (~50 unit tests total): `test_versioning.py`, `test_preview.py`, `test_contract_preview.py`, `test_contract_templates.py`, `test_attach_to_revision.py`.

Day-4 acceptance: `pytest apps/control-plane/tests/{mock_llm,context_engineering,trust}/` passes (~62 unit tests); the 11 new endpoints + 7 service methods + MockLLMProvider are wired correctly; the migration is reversible; the MockLLMProvider returns deterministic responses; Rule 50 invariants hold (verified via metric `real_llm_calls_total` does NOT increment during preview tests).

## Phase 3 — Track B Build Order (Frontend pages + Monaco editors)

**Days 1-6 (1-2 devs in parallel; can start day 1 with placeholder Zod schemas).**

14. **Day 1 morning** — Create `apps/web/components/features/agents/YamlJsonEditor.tsx` per design D9 + research R6: shared Monaco wrapper modeled on existing `MonacoYamlEditor.tsx`. Supports YAML/JSON toggle + JSON Schema validation provider + auto-completion. Lazy-loaded via `next/dynamic` to avoid bundling Monaco into non-editor pages.
15. **Day 1 afternoon** — Create `apps/web/components/features/agents/SchemaValidatedEditor.tsx`: generic wrapper around `<YamlJsonEditor>` providing inline validation + auto-completion from fetched schema.
16. **Day 1 afternoon** — Create `lib/hooks/use-{contract,profile}-schema.ts` + `use-schema-enums.ts`: TanStack Query hooks fetching JSON Schema from new endpoints; cache stale-time = 1 hour per design D4.
17. **Day 2 morning** — Create context profile editor + 5 sub-components: `ContextProfileEditor.tsx`, `SourcePicker.tsx` (visibility-filtered per UPD-053), `RetrievalStrategySelector.tsx` (semantic/graph/FTS/hybrid), `RerankingRulesEditor.tsx` (drag-reorder), `ContextBudgetControls.tsx`.
18. **Day 2 afternoon** — Create `<TestQueryPanel>` + `<ProvenanceViewer>` per design D8 + FR-668: provenance viewer accepts `executionId` prop (null on profile Test tab; populated on ExecutionDrilldown Context tab); same component reused on both surfaces per SC-005 (DRY).
19. **Day 3 morning** — Create context profile history page + 2 sub-components: `VersionList.tsx`, `VersionDiffViewer.tsx` (side-by-side JSON diff with green/red highlights per User Story 3).
20. **Day 3 afternoon** — Modify `ExecutionDrilldown.tsx` per research R4: extend `DrilldownTab` union + `VALID_TABS` set with `"context"`. Add NEW `<TabsContent value="context">` block rendering `<ProvenanceViewer executionId={executionId} />`.
21. **Day 4 morning** — Create contract editor + 5 sub-components: `ContractEditor.tsx` (Monaco YAML/JSON toggle wrapping `<YamlJsonEditor>`), `ContractPreviewPanel.tsx`, `SampleInputManager.tsx`, `RealLLMOptInDialog.tsx` per design D5, `AttachToRevisionDialog.tsx` per FR-673.
22. **Day 4 afternoon** — Create contract history page (~180 lines).
23. **Day 5 morning** — Create contract template library page + 2 sub-components: `TemplateCard.tsx`, `ForkDialog.tsx`.
24. **Day 5 morning** — Wire UPD-042 notification integration per FR-672 + spec correction §14: subscribe to `creator.contract_template.upstream_updated` events on the user's notification channel; display in notification bell.
25. **Day 5 afternoon** — Modify `CompositionWizard.tsx` per research R3: extend the `STEP_LABELS` array with 5 new entries; add 5 NEW conditional render branches for the new step components; preserve existing 4 steps unchanged.
26. **Day 5 afternoon** — Create 5 new wizard step components: `WizardStepContextProfile.tsx`, `WizardStepTestProfile.tsx`, `WizardStepContract.tsx`, `WizardStepPreviewContract.tsx`, `WizardStepAttachBoth.tsx`.
27. **Day 6 morning** — i18n integration: extract ~80 new strings to `apps/web/messages/en.json` under `creator.{contextProfile,contract,template}.*` namespaces. Commit with TODO markers for the 5 other locales (vendor-translated per UPD-039 / FR-620).
28. **Day 6 morning** — Run `pnpm test:i18n-parity` — verify all 6 locale catalogs have all new keys.
29. **Day 6 afternoon** — Run axe-core scan on all 5 new pages locally; verify zero AA violations per Rule 41 inheritance from UPD-083. Verify Monaco editor is keyboard-navigable per SC-019.
30. **Day 6 afternoon** — Run `pnpm test`, `pnpm typecheck`, `pnpm lint` to verify all CI gates pass.
31. **Day 6 afternoon** — Author Playwright E2E `apps/web/tests/e2e/creator-uis-pages.spec.ts` with ~20 scenarios.

Day-6 acceptance: 5 new pages render correctly against the live Track A backend; `pnpm test`, `pnpm typecheck`, axe-core scan, i18n parity check all pass; Playwright E2E ~20 scenarios pass.

## Phase 4 — Track C Build Order (E2E + journey extension)

**Days 4-6 (1 dev — depends on Track A endpoints functional + Track B pages reachable).**

32. **Day 4 afternoon** — Create `tests/e2e/suites/creator_uis/__init__.py` + `conftest.py` (NEW pytest fixtures): `creator_with_agent`, `creator_with_profile`, `creator_with_contract`, `mock_llm_responses`, `contract_template_seeded`.
33. **Day 5** — Author 7 E2E test files (one per User Story 1-7). Each ~80 lines. Total ~560 lines. Each verifies the corresponding User Story's acceptance scenarios.
34. **Day 6 morning** — Modify `tests/e2e/journeys/test_j02_creator_to_publication.py` per FR-674 + spec correction §9 + research R9: extend the existing single async function `test_j02_creator_to_publication()` at line 154 with ≥ 25 NEW assertion blocks covering the full creator flow (register → context profile → preview → contract → preview → fork-template → attach-both → certify → publish). Final J02 line count ≈ 750 lines.
35. **Day 6 afternoon** — Modify `.github/workflows/ci.yml`: add `tests/e2e/suites/creator_uis/` to UPD-040's matrix-CI test path (3 modes: mock / kubernetes / vault).
36. **Day 6 afternoon** — Verify SC-016: J02 (extended) + 7 E2E suite tests pass on the matrix CI for all 3 modes.

Day-6 acceptance: 7 E2E test files + J02 extension all pass; matrix CI green for all 3 secret modes.

## Phase 5 — Cross-Cutting Verification

**Day 7 (1 dev).**

37. **Day 7 morning** — Run UPD-040's `scripts/check-secret-access.py`: verify zero new direct `os.getenv("*_SECRET")` calls outside `SecretProvider` implementation files.
38. **Day 7 morning** — Verify Rule 50 invariants per Constitution + design D3: synthetic test invokes `POST /contracts/{id}/preview` with `use_mock=true` (default); asserts `real_llm_calls_total` Prometheus metric did NOT increment; asserts MockLLMProvider's audit-log entry `mock_llm.preview_executed` was emitted; opt-in path with `use_mock=false, cost_acknowledged=false` MUST be rejected with 400; opt-in path with both `true` MUST emit `creator.contract.real_llm_preview_used` audit.
39. **Day 7 afternoon** — Verify all 11 new endpoints emit audit-chain entries per Rule 9: synthetic test asserts `audit_chain_entries` row count grows by exactly 1 per state-changing call (rollback / fork / attach-revision / preview).
40. **Day 7 afternoon** — Verify Rule 45 mapping: every Track A endpoint maps to a Track B page per spec.md Key Entities section. Synthetic test enumerates Track A endpoints + asserts a corresponding page exists at the documented URL.
41. **Day 7 afternoon** — Verify Rule 41: axe-core scan + Monaco keyboard-navigation manual test on all 5 new pages.

## Phase 6 — SC verification + documentation polish

**Days 7-9 (1 dev — overlaps Phase 5).**

42. **Day 7-8** — Run the full SC verification sweep per the spec's 20 SCs. Capture verification record at `specs/094-creator-context-contracts-ui/contracts/sc-verification.md` (NEW file).
43. **Day 8 morning** — If UPD-039 has landed, author 3 NEW operator runbooks under `docs/operator-guide/runbooks/`: `creator-mock-llm-fallback.md` (when MockLLMProvider falls back to generic-fallback), `context-profile-versioning.md` (rollback flow), `contract-template-upstream-update.md` (fork notification flow). If UPD-039 has not landed, runbooks live in feature `contracts/` per design D10.
44. **Day 8 afternoon** — Author 3 NEW developer-guide pages: `mock-llm-provider-internals.md` (Rule 50 architectural design + canned-response fixture format + how to add new fixtures), `creator-context-profile-format.md` (JSON Schema + per-source provenance fields + versioning), `contract-template-design.md` (template forking + upstream-update notifications).
45. **Day 9** — Modify release notes: add UPD-044 entry covering 5 new pages + 11 new endpoints + foundational MockLLMProvider primitive (reusable by future creator-preview flows) + greenfield versioning + greenfield template library. NO breaking changes (purely additive).
46. **Day 9** — Final review pass; address PR feedback; merge.

## Effort & Wave

**Total estimated effort: 11-12 dev-days** (5-6 wall-clock days with 3 devs in parallel: 1 on Track A, 1-2 on Track B, 1 on Track C; convergent on Days 7-9).

The brownfield's "5 days (5 points)" understates by ~50% (consistent with v1.3.0 cohort pattern):
- The greenfield `MockLLMProvider` per Rule 50 + spec correction §6 adds ~1.5 dev-days the brownfield doesn't account for.
- The greenfield context profile versioning (NEW table + 4 endpoints + UI history page) per spec correction §2 adds ~1 dev-day.
- The greenfield contract template library (NEW table + 2 endpoints + UI library page + seed migration) per spec correction §13 adds ~0.5 day.
- The contract-to-revision FK migration + endpoint per spec correction §5 adds ~0.5 day.
- The 7 audit-event types + 11 new endpoints + JSON Schema export endpoints add ~1 day.
- J02 extension to ≥ 25 assertion points per FR-674 (existing is 579-line skeleton with 1 async function per research R9) adds ~1 day vs the brownfield's implicit 0.5 day.

**Wave: Wave 19 — first feature of v1.4.0 cycle.** Position in execution order:
- Wave 18 — UPD-043 Workspace Owner Workbench (last in v1.3.0)
- **Wave 19 — UPD-044 Creator-Side UIs** (this feature; first in v1.4.0)

**Cross-feature dependency map**:
- UPD-044 INTEGRATES with UPD-042 (notification center for upstream-update notifications per FR-672 + spec correction §14).
- UPD-044 INHERITS UPD-040's matrix-CI for 3 secret modes.
- UPD-044 INTRODUCES the foundational MockLLMProvider per Rule 50 (reusable by future creator-preview flows in evaluation, simulation, etc.).
- UPD-044 EXTENDS UPD-006 (agent contracts backend) with the design-time revision attachment per FR-673.
- UPD-044 EXTENDS context_engineering BC (existing 16 endpoints) with versioning + preview.

## Risk Assessment

**Medium risk overall.** UPD-044 has the largest feature scope in the v1.4.0 opening + introduces foundational MockLLMProvider infrastructure. Risks:

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **R1: MockLLMProvider canned responses too narrow** | Medium | Medium (creators see fallback frequently) | Per design D3 — 5 default scenarios cover most-common preview inputs; fallback emits `mock_llm.fallback_used` audit-log for fixture-coverage tracking; ops team adds new fixtures based on telemetry. |
| **R2: Real-LLM preview cost surprise** | Low | High (creator hits unexpected billing) | Per design D5 + Rule 50 — explicit confirmation dialog with cost estimate; user types "USE_REAL_LLM" to confirm; audit entry emitted. |
| **R3: Profile versioning storage growth** | Medium | Low (storage cost) | Each profile save creates a new row in `context_engineering_profile_versions` (~10KB/version); 100 active creators × 100 versions/profile = 100MB — negligible. Future archival policy (age-based pruning of v < latest - 50) is out of scope. |
| **R4: Monaco bundle size** | Medium | Low (initial JS payload) | Per research R6 — Monaco is lazy-loaded via `next/dynamic`; non-editor pages don't bundle it. Existing `MonacoYamlEditor.tsx` precedent confirmed bundle-budget compliance. |
| **R5: Schema endpoint cache staleness** | Low | Low (UI shows old validation rules briefly) | Per design D4 — frontend stale-time = 1 hour; UI hot-reload picks up new schema on tab refresh. Schema changes are rare (Pydantic model migrations). |
| **R6: Contract template upstream conflicts** | Medium | Low (forked content diverges) | Per FR-672 — fork records `forked_from_template_id`; upstream updates trigger UPD-042 notification; creator opens diff view to manually merge. No auto-merge. |
| **R7: Contract-revision FK on revision deletion** | Low | Low (broken link) | Per design D2 — `ON DELETE SET NULL` preserves contract; UI shows "revision deleted" state with re-attach option. |
| **R8: J02 extension introduces flakiness** | Medium | Medium (CI burn) | Per research R9 — extend the existing single async function; reuse existing fixtures; add ~25 assertion blocks incrementally with isolated mock data. |
| **R9: i18n catalog drift across 6 locales** | Medium | Low (untranslated strings) | UPD-088's parity check catches drift; 7-day grace window applies. |

## Plan-correction notes (vs. brownfield input)

1. **Effort estimate corrected from 5 days to 11-12 dev-days** (consistent with v1.3.0 cohort pattern).
2. **Wave 19 reaffirmed** (first of v1.4.0).
3. **MockLLMProvider is GREENFIELD** per Constitution Rule 50 + spec correction §6 + research R5 — does NOT exist today; brownfield treats it as an existing primitive.
4. **Profile versioning is GREENFIELD** per spec correction §2 — `ContextEngineeringProfile` has NO versioning columns today; the brownfield's "Profiles are versioned backend-side" claim is INCORRECT.
5. **Contract template library is GREENFIELD** per spec correction §13 + research R13 — no existing template pattern in the codebase.
6. **Contract-to-revision FK is NEW** per spec correction §5 — `AgentContract` has only `agent_id: str` today; the brownfield's "attaching to revision" assumption is implementation-required.
7. **Monaco is ALREADY in package.json** per spec correction §10 + research R6 — `@monaco-editor/react ^4.7.0` + `monaco-yaml ^5.4.1`. The brownfield's "Monaco Editor or CodeMirror 6" framing is corrected to "Monaco-only" with the existing precedent at `MonacoYamlEditor.tsx`.
8. **Execution detail page is at `/operator/executions/[executionId]/`** per spec correction §9 — NOT `/executions/[id]/` as the brownfield writes.
9. **`<ExecutionDrilldown>` has 4 tabs today** per research R4; UPD-044 adds a 5th `context` tab.
10. **`CompositionWizard` has 4 steps today** per research R3; UPD-044 adds 5 new steps (steps 5-9).
11. **J02 is a 579-line skeleton with 1 async function** per spec correction §9 + research R9; extension adds ≥ 25 assertion blocks.
12. **11 net-new endpoints (NOT 5 as brownfield's "Backend Additions" lists)**: 4 context-engineering + 4 contract + 2 schema + 1 enums.
13. **Migration `072_creator_context_contracts.py`** per research R12 (UPD-043 owns 071).
14. **7 new audit-event types** following `creator.{domain}.{action}` convention (NEW namespace — distinct from existing `auth.*`, `privacy.*`, `notifications.*` per UPD-040/042/043 patterns).
15. **Real-LLM preview opt-in requires explicit confirmation** per design D5 + Rule 50 — NOT a silent flag.

## Complexity Tracking

| Area | Complexity | Why |
|---|---|---|
| Alembic migration (1 column + 2 tables + seed) | Medium | 2 new tables + 1 new column + data migration for 5 templates; reversible. |
| Context profile versioning | Medium | Greenfield primitive; UNIQUE constraint + monotonic version_number; rollback creates new version (never destructive). |
| MockLLMProvider greenfield primitive | High | Foundational per Rule 50; deterministic canned responses + fallback; reusable by future creator-preview flows. |
| 11 new backend endpoints | Medium | Most are wrappers over service methods; schema endpoints serve Pydantic-generated JSON Schema. |
| 5 new Next.js pages + 30 sub-components | High | ~1250 lines of TSX + ~2400 lines of components + Monaco integration + i18n × 6 locales + Playwright × 20 scenarios. |
| `<YamlJsonEditor>` + `<ProvenanceViewer>` reusable components | Medium | Modeled on existing precedents (Monaco workflows editor + reusable across 2 surfaces per DRY). |
| `CompositionWizard` extension with 5 new steps | Medium | Modify existing wizard array + add 5 new step components; preserve existing 4 steps unchanged. |
| 7 E2E test files + J02 extension (≥25 assertions) | Medium | One per User Story; J02 extension reuses existing single async function structure. |
| i18n + axe-core sweep | Medium | 480 entries × 6 locales + AA scan on 5 surfaces + Monaco keyboard-nav manual test. |

**Net complexity: medium-high.** The MockLLMProvider greenfield primitive + the greenfield versioning + the greenfield template library are the highest-risk pieces; once they ship, the rest is mechanical.
