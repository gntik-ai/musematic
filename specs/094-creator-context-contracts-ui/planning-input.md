# UPD-044 — Creator-Side UIs: Context Engineering and Agent Contracts

## Brownfield Context

**Current state (verified in repo):**
- Backend `context_engineering/router.py` and service/repository fully implemented: profiles, provenance tags, retrieval strategies (semantic/graph/FTS/hybrid), context budget, JSON schema validation.
- Backend for Agent Contracts from UPD-006 fully implemented (FR-217, FR-419-421): contract model, `contract_monitor`, attachment to revisions, policy expressions.
- UI `/agent-management/[fqn]/page.tsx` and `/revisions/page.tsx` exist (agent detail, revisions list).
- UI `/agents/create/page.tsx` and `/agent-management/wizard/page.tsx` exist (creation wizards).
- Creator Workbench (FR-293) mentions "configure context engineering profiles" and "set reasoning mode preferences" but these surfaces don't exist in the frontend.

**Gaps:**
1. **No Context Engineering Profile Editor UI**. Creators cannot author or edit context profiles from the frontend. Backend supports it; UI does not expose it.
2. **No Provenance Viewer**. Creators can't see why a given execution retrieved which sources, their scores, their classifications.
3. **No Context Profile Version Management UI**. Profiles are versioned backend-side but users can't diff, rollback, or compare versions.
4. **No Agent Contract Authoring UI**. Contracts are backend-only; creators can't write, preview, or test contracts without API calls.
5. **No Contract Preview / Test**. Simulating a contract against sample inputs (non-destructive) requires API scripting.
6. **No Contract Library / Templates**. Starter templates exist in documentation (UPD-039) but there's no in-product library.

**Extends:**
- FR-148-159 Context Engineering (all backend-implemented).
- FR-217, FR-419-421 Agent Contracts (UPD-006 implemented backend-side).
- FR-293 Creator Workbench (today a documentation concept, not a tangible surface).
- UPD-035 E2E (J02 Creator journey needs extension).

**FRs:** FR-667 through FR-674 (section 117).

---

## Summary

UPD-044 gives the **creator persona** the UI surfaces they need to do their work entirely from the frontend, without scripting against the API:

- Context profile editor with sources, retrieval strategies, budget, schema validation.
- Provenance viewer showing why each source contributed to a context.
- Version management with diff, compare, and rollback.
- Contract authoring editor with YAML / JSON, live schema validation.
- Contract preview / test with mock LLM provider (FR-458).
- Contract library with starter templates.
- Integration into the Creator Workbench (FR-293) as sequential steps in the agent publication flow.

These close a gap in the product's creator-first positioning: today, creators can register agents and publish them, but they cannot author two of the most important configuration artifacts from the UI.

---

## User Scenarios

### User Story 1 — Creator authors a context profile for a new agent (Priority: P1)

A creator is building a customer-support agent and needs it to retrieve from historical tickets + FAQ knowledge base + product documentation, using hybrid retrieval.

**Independent Test:** Navigate to `/agent-management/{fqn}/context-profile`. Create a new profile. Add three sources with specific retrieval strategies. Set context budget. Save. Test with a sample query. Verify provenance.

**Acceptance:**
1. Editor opens for the agent's current revision with an empty profile if none exists.
2. Source picker lists available data sources in the workspace (memory / knowledge graph / execution history / tool outputs / registered external APIs).
3. Per-source retrieval strategy selector: semantic (Qdrant), graph traversal (Neo4j), FTS (OpenSearch), hybrid.
4. Reranking rules: by score, by recency, by authority, custom expression.
5. Context budget controls: max tokens, max documents, per-source fractions.
6. Provenance tagging toggle per source.
7. JSON schema validation inline; save blocked on errors with clear messages.
8. "Test with query" triggers a mock retrieval showing which sources contributed, their scores, and the merged context.

### User Story 2 — Creator inspects provenance after an execution (Priority: P2)

A creator investigates why an agent gave an unexpected answer. They want to see what context the agent retrieved.

**Independent Test:** Open any execution detail. Navigate to "Context" tab. See the full provenance: sources consulted, scores, which were included, their classifications.

**Acceptance:**
1. Provenance viewer shows sources in descending relevance score.
2. Each source row: origin (memory entry / graph node / tool output), snippet, score, included/excluded flag with reason, sensitivity classification (PII / PHI / financial / public).
3. Click a source to deep-inspect the origin (e.g., navigate to the memory entry detail).
4. Viewer available both on execution detail pages and on the profile editor's "Test" tab.

### User Story 3 — Creator rolls back a profile to a previous version (Priority: P2)

A creator changed the retrieval strategy and evaluation results got worse. They want to revert.

**Independent Test:** Navigate to the profile editor's "History" tab. See version list. Click "Compare" between current and v3. See side-by-side diff. Click "Rollback to v3".

**Acceptance:**
1. History tab lists versions with timestamp, author, change summary.
2. Compare mode shows side-by-side diff with highlights.
3. Rollback creates a new version (v-current+1) matching v3's content — never destructively mutates older versions.
4. Rollback emits an audit chain entry.
5. Agent revisions pinned to a specific profile version remain unaffected.

### User Story 4 — Creator authors a contract for a high-impact agent (Priority: P1)

A creator is building an agent that can update production databases. They want to formalize its boundaries.

**Independent Test:** Navigate to `/agent-management/{fqn}/contract`. Create a contract: scope (tools allowed, resources allowed, budget), expected outputs (schema, quality thresholds), behavioral constraints, escalation rules. Preview with sample inputs. Verify violations trigger appropriate actions.

**Acceptance:**
1. Contract editor supports YAML and JSON syntax with toggle.
2. Live schema validation with error markers.
3. Auto-completion for known fields (tool FQNs, resource types, role types).
4. Scope section: tools allowed, resources, budget (cost + time), workspace constraints.
5. Expected outputs: schema reference, quality thresholds (per FR-212 metrics).
6. Behavioral constraints: forbidden actions, required approvals (gates per FR-107), attention requests (per FR-432).
7. Escalation: conditions, target, urgency.
8. Failure modes: on violation — warn / throttle / escalate / terminate.
9. Save creates contract record; attaching to revision enforces at runtime.

### User Story 5 — Creator previews contract against sample inputs (Priority: P1)

Before attaching, the creator wants to verify the contract behaves correctly.

**Independent Test:** In the contract editor, click "Preview". Provide a sample input (or use saved samples). Run preview. See which clauses triggered, which were satisfied, which violated, and the resulting action.

**Acceptance:**
1. Preview step uses the mock LLM provider (FR-458) — no real LLM calls unless explicitly opted in.
2. Sample inputs can be saved for re-testing.
3. Preview output shows: clauses triggered, satisfied, violated, final action (continue / warn / throttle / escalate / terminate).
4. Violations link to the exact contract clause in the editor.
5. Saved previews accessible from contract history.

### User Story 6 — Creator starts from a template (Priority: P2)

A creator wants to build a code-review agent and uses a platform-provided template.

**Independent Test:** Navigate to contract library. Select "Code review agent contract" template. Fork. Customize. Attach.

**Acceptance:**
1. Contract library page (`/agent-management/contracts/library`) shows platform-authored and trusted-creator templates.
2. Fork action creates an editable copy with metadata (forked from X v2).
3. Template updates (central version bumped) notify forked users via notification center per UPD-042.
4. Templates are versioned separately.
5. Templates localized in documentation but editor remains English (YAML/JSON).

### User Story 7 — Creator publishes agent with profile + contract (Priority: P1)

The full Creator flow now includes context profile and contract as mandatory steps for high-impact agents.

**Independent Test:** Run through the extended J02 Creator journey. Register agent, create context profile, test it, create contract, preview, attach both, proceed to certification.

**Acceptance:**
1. Creator wizard (FR-293) includes context-profile + contract steps.
2. Steps are skippable for low-trust-tier agents, required for high-trust-tier per platform policy.
3. Validation errors block step progression.
4. Revisions publish with profile + contract metadata snapshotted.

---

### Edge Cases

- **Profile references a source the workspace doesn't have visibility on**: source picker excludes it with a tooltip explaining why.
- **Contract references a tool not in the workspace's allowed tools**: validation fails with clear message.
- **Profile schema version mismatch**: migration path offered; old profile auto-upgraded with a review step.
- **Contract preview against malformed sample input**: preview surfaces parse errors without running.
- **Template forked, original later deleted**: forks remain functional; notification explains upstream removal.
- **Multi-language contract text**: editor remains English-only (YAML / JSON); descriptions in natural language fields are not auto-translated.

---

## UI Routes (Next.js)

```
apps/web/app/(main)/
├── agent-management/
│   ├── [fqn]/
│   │   ├── page.tsx                           # existing: detail
│   │   ├── revisions/page.tsx                 # existing
│   │   ├── context-profile/
│   │   │   ├── page.tsx                       # NEW: editor
│   │   │   └── history/page.tsx               # NEW: versions / diff / rollback
│   │   └── contract/
│   │       ├── page.tsx                       # NEW: editor
│   │       └── history/page.tsx               # NEW: history
│   └── contracts/
│       └── library/page.tsx                   # NEW: templates
```

## Shared Components

- `<ContextProfileEditor>` — full editor with sources, strategies, budget, validation
- `<SourcePicker>` — picker for retrievable sources with visibility filtering
- `<RetrievalStrategySelector>` — picker per source
- `<RerankingRulesEditor>` — rules list with drag-reorder
- `<ContextBudgetControls>` — max tokens / docs, fractions per source
- `<ProvenanceViewer>` — reusable viewer embedded on execution detail pages and test mode
- `<ContextProfileVersionHistory>` — versions list with diff and rollback
- `<YamlJsonEditor>` — shared editor for contracts (wraps Monaco Editor or CodeMirror 6 with schema validation)
- `<ContractPreview>` — preview panel with sample input + result inspection
- `<ContractTemplateLibrary>` — cards / filters / fork action
- `<ContractAttachmentStatus>` — shows attached contracts with enforcement status
- `<SchemaValidatedEditor>` — generic wrapper providing inline validation + auto-completion

## Backend Additions

Most endpoints already exist per FR-148-159 and FR-217, FR-419-421. Minor additions:
- `POST /api/v1/context-profiles/{id}/preview` — mock retrieval for test queries.
- `POST /api/v1/context-profiles/{id}/rollback/{version}` — explicit rollback creating a new version.
- `GET /api/v1/context-profiles/{id}/versions` + `GET /api/v1/context-profiles/{id}/versions/{v1}/diff/{v2}`.
- `POST /api/v1/contracts/{id}/preview` — mock execution against sample input.
- `GET /api/v1/contracts/templates` / `POST /api/v1/contracts/{template_id}/fork`.

## Acceptance Criteria

- [ ] Context profile editor fully functional with sources, strategies, budget
- [ ] Source picker respects workspace visibility
- [ ] Retrieval strategies selectable per source
- [ ] Reranking rules editable
- [ ] JSON schema validation works inline
- [ ] Test with sample query shows provenance panel
- [ ] Profile version history with diff + rollback
- [ ] Provenance viewer reusable on execution detail pages
- [ ] Contract authoring editor with YAML and JSON toggle
- [ ] Live schema validation and auto-completion
- [ ] Contract preview using mock LLM provider
- [ ] Sample inputs savable and reusable
- [ ] Contract template library with fork action
- [ ] Template forks receive upstream-update notifications
- [ ] J02 Creator journey extended to cover context + contract steps
- [ ] All new pages pass axe-core AA
- [ ] Editor UI fully keyboard-navigable (important for power users)
- [ ] Localization: surrounding UI in 6 languages; editor content (YAML/JSON) remains English
