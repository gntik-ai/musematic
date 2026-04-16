# Quickstart: Agent Catalog and Creator Workbench

## Prerequisites

- Node.js 20+, pnpm 9+
- Backend APIs operational: registry (021), composition (038), policy (028)
- Development server for `apps/web` running

## New Dependencies

No new npm packages required. All dependencies already in the frontend stack (from feature 015):
- `shadcn/ui` — DataTable building blocks, Tabs, Dialog, Form, Select, Badge, Tooltip, Progress, AlertDialog
- `@tanstack/react-table v8` — DataTable column/filter configuration (via existing DataTable shared component)
- `TanStack Query v5` — all server state (`useQuery`, `useInfiniteQuery`, `useMutation`)
- `Zustand 5.x` — composition wizard client state
- `React Hook Form 7.x + Zod 3.x` — metadata editor form
- `Monaco Editor 0.50+` — revision diff viewer (`MonacoDiffEditor`)
- `date-fns 4.x` — timestamp formatting
- `Lucide React` — icons throughout
- `Tailwind CSS 3.4+` — all styling, dark mode via CSS custom properties

## Running the Dev Server

```bash
cd apps/web
pnpm dev
```

Navigate to:
- `http://localhost:3000/agent-management` — Agent catalog
- `http://localhost:3000/agent-management/{encoded-fqn}` — Agent detail
- `http://localhost:3000/agent-management/{encoded-fqn}/revisions` — Revision timeline
- `http://localhost:3000/agent-management/wizard` — AI composition wizard

## Running Tests

```bash
cd apps/web
pnpm test                  # Vitest unit tests
pnpm test:e2e              # Playwright E2E tests
```

Test setup:
- Vitest + RTL for component tests
- MSW (Mock Service Worker) for API mocking
- Playwright for E2E flows (catalog browse, metadata edit, upload)

## Project Structure

```text
apps/web/
├── app/(main)/agent-management/
│   ├── page.tsx                           # Agent catalog (US1)
│   ├── [fqn]/
│   │   ├── page.tsx                       # Agent detail (US2, US4, US5)
│   │   └── revisions/
│   │       └── page.tsx                   # Revision timeline + diff (US6)
│   └── wizard/
│       └── page.tsx                       # AI composition wizard (US7)
│
├── components/features/agent-management/
│   ├── AgentDataTable.tsx                 # DataTable with search/filter (US1)
│   ├── AgentMaturityBadge.tsx             # Maturity level badge
│   ├── AgentStatusBadge.tsx               # Status indicator
│   ├── AgentDetailView.tsx                # Tabbed detail layout (US2)
│   ├── AgentHealthScoreGauge.tsx          # Composite health gauge (US2)
│   ├── AgentMetadataEditor.tsx            # RHF+Zod form (US4)
│   ├── FQNInput.tsx                       # Namespace selector + local name + preview
│   ├── VisibilityPatternPanel.tsx         # FQN patterns management
│   ├── RoleTypeSelector.tsx               # Role type dropdown (7 options)
│   ├── AgentUploadZone.tsx                # Drag-and-drop upload (US3)
│   ├── AgentPublicationPanel.tsx          # Validate/publish panel (US5)
│   ├── PublicationConfirmDialog.tsx       # Publication confirmation (US5)
│   ├── AgentRevisionTimeline.tsx          # Revision list + selection (US6)
│   ├── RevisionDiffViewer.tsx             # Monaco diff editor (US6)
│   ├── CompositionWizard.tsx              # 4-step wizard container (US7)
│   ├── WizardStepDescribe.tsx             # Step 1: description input
│   ├── WizardStepReviewBlueprint.tsx      # Step 2: blueprint review with reasoning
│   ├── WizardStepCustomize.tsx            # Step 3: blueprint customization
│   └── WizardStepValidate.tsx             # Step 4: validate and create
│
├── lib/
│   ├── hooks/
│   │   ├── use-agents.ts                  # useAgents (infinite), useAgent
│   │   ├── use-agent-mutations.ts         # useUpdateAgentMetadata, useValidateAgent, usePublishAgent, useRollbackRevision
│   │   ├── use-agent-upload.ts            # useUploadAgentPackage (XHR + progress)
│   │   ├── use-agent-revisions.ts         # useAgentRevisions, useRevisionDiff
│   │   ├── use-agent-health.ts            # useAgentHealth
│   │   └── use-composition.ts             # useGenerateBlueprint, useCreateFromBlueprint
│   ├── agent-management/
│   │   └── navigation.ts                  # Hard navigation helpers for detail routes
│   └── stores/
│       └── use-composition-wizard-store.ts # Zustand wizard state
│
├── __tests__/
│   └── features/agent-management/
│       ├── AgentDataTable.test.tsx
│       ├── AgentMetadataEditor.test.tsx
│       ├── AgentUploadZone.test.tsx
│       ├── AgentPublicationPanel.test.tsx
│       ├── AgentRevisionTimeline.test.tsx
│       ├── RevisionDiffViewer.test.tsx
│       └── CompositionWizard.test.tsx
└── e2e/
    ├── agent-catalog.spec.ts
    ├── agent-metadata-edit.spec.ts
    └── agent-upload.spec.ts
```

## Key Configuration

No new environment variables required. The feature uses the existing `NEXT_PUBLIC_API_BASE_URL` and auth token from the existing auth store.
