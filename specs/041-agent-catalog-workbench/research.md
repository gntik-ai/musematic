# Research: Agent Catalog and Creator Workbench

**Feature**: 041-agent-catalog-workbench  
**Phase**: 0 (Research)  
**Date**: 2026-04-16

---

## Decision 1: Route Structure

**Decision**: Use Next.js 14+ App Router route groups under `app/(main)/agent-management/` with dynamic `[fqn]/` segment for agent detail. The FQN (`namespace:local_name`) is URL-encoded as a single path segment. Sub-pages for revisions (`[fqn]/revisions/`) and the AI wizard (`wizard/`) are separate pages.

```
app/(main)/agent-management/
├── page.tsx                    # Catalog (US1)
├── [fqn]/
│   ├── page.tsx                # Detail + metadata editor (US2, US4, US5)
│   └── revisions/
│       └── page.tsx            # Revision timeline + diff (US6)
└── wizard/
    └── page.tsx                # AI composition wizard (US7)
```

**Rationale**: FQN as a URL segment (encoded) is natural for deep-linking to specific agents. The wizard creates new agents so lives at a separate route rather than under an existing FQN. Upload is a dialog on the catalog page (shadcn Dialog) since it's a brief flow — no separate route needed.

**Alternatives considered**:
- Nested modals for detail — rejected; detail page has too many sections (policies, certifications, evaluations, revisions) to fit in a modal without poor UX.
- Separate routes for metadata editor and publication — rejected; these are sub-sections of the detail page accessible via tabs (shadcn Tabs), not separate routes.

---

## Decision 2: Agent Detail Page Tabs

**Decision**: Agent detail page uses shadcn `Tabs` with URL query param routing (`?tab=overview|metadata|policies|certifications|evaluations|revisions`) — same pattern as Admin Settings Panel (feature 027). Default tab is `overview` showing health score + summary.

**Rationale**: Tabs keep all agent management operations on one URL (deep-linkable per tab) without a page-per-tab route proliferation. Matches established pattern from feature 027 which already validated this UX approach.

---

## Decision 3: Drag-and-Drop Upload Implementation

**Decision**: Implement drag-and-drop using browser-native `dragenter`/`dragleave`/`drop` events on a `<div>` styled with Tailwind. Use `XMLHttpRequest` (not `fetch`) for file upload to get `progress` events for the progress bar. No additional npm packages required.

**Rationale**: The platform already avoids adding packages when native APIs suffice. `XMLHttpRequest.upload.onprogress` provides real-time byte-level progress that `fetch` doesn't expose. The `<input type="file" accept=".tar.gz,.zip">` handles file picker. Dragged file validated client-side by extension + MIME type before upload starts.

**Alternatives considered**:
- `react-dropzone` — rejected; adds ~30KB dependency for browser APIs that are straightforward to wrap directly.
- `fetch` with ReadableStream progress — rejected; upload progress via fetch is not widely supported and complex to implement correctly.

---

## Decision 4: Revision Diff View

**Decision**: Use Monaco Editor's built-in `MonacoDiffEditor` (already in platform stack from feature 015) for side-by-side revision diff. Diff content is serialized as YAML/JSON of the agent configuration. Binary diff for code files is out of scope for v1 (per spec assumption).

**Rationale**: Monaco is already in the stack. `MonacoDiffEditor` provides a production-quality diff UI with syntax highlighting, line numbers, and fold controls. Zero new dependencies.

**Alternatives considered**:
- `react-diff-viewer-continued` — rejected; adds a dependency for a use case Monaco already covers.
- Custom diff rendering — rejected; significantly more work with worse UX.

---

## Decision 5: AI Composition Wizard State

**Decision**: Zustand store (`useCompositionWizardStore`) manages wizard step state (1–4), the natural-language description, the generated blueprint, and the customized blueprint. Store is NOT persisted (session-only). On page navigate-away, the store resets. The 4 steps render as a single-page multi-step form within `wizard/page.tsx` using a step index.

**Rationale**: Multi-step wizard state belongs in a client store (not server state) since it's ephemeral and local to the wizard session. Zustand is the established client state solution. Not persisting prevents stale wizard state from appearing on return visits. Matches the marketplace comparison store pattern (feature 035).

**Alternatives considered**:
- URL-based step state (`?step=2`) — viable but creates a back-button trap. Zustand keeps it clean.
- React `useState` within the wizard page — fine for simple cases but the blueprint object is complex enough to warrant a store for clean cross-step access.

---

## Decision 6: Health Score Gauge Component

**Decision**: Reuse/extend the existing `ScoreGauge` shared component (`apps/web/components/shared/ScoreGauge.ts`) with additional `breakdown` prop showing component scores in a shadcn `Tooltip` on hover. No new chart library needed — ScoreGauge is already implemented as a canvas-based gauge.

**Rationale**: ScoreGauge is already in the shared component library and in use across the platform. Adding a `breakdown` prop (array of `{label, score}`) with a Tooltip is a minimal additive change that avoids creating a new component.

---

## Decision 7: No New npm Packages Required

**Decision**: All implementation uses packages already in the frontend stack. No new installations needed.

Current stack items used by this feature:
- `shadcn/ui` — ALL UI primitives (DataTable building blocks, Tabs, Dialog, Form, Select, Badge, Tooltip, Progress, Accordion)
- `@tanstack/react-table` v8 — DataTable (already in stack via DataTable shared component)
- `TanStack Query v5` — all server state
- `Zustand 5.x` — composition wizard client state
- `React Hook Form 7.x + Zod 3.x` — metadata editor form
- `Monaco Editor 0.50+` — revision diff viewer (MonacoDiffEditor)
- `date-fns 4.x` — timestamp formatting
- `Lucide React` — icons
- `Tailwind CSS 3.4+` — all styling
