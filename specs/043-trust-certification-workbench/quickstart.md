# Quickstart: Trust and Certification Workbench

## Prerequisites

- Node.js 20+, pnpm 9+
- Backend APIs operational: trust service (032), policy governance (028)
- Development server for `apps/web` running

## New Dependencies

**None.** All required libraries are already installed:

- `shadcn/ui` — DataTable, Tabs, Badge, Collapsible, Tooltip, Dialog, Form, AlertDialog, Sheet
- `Recharts 2.x` — RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip
- `TanStack Query v5` — all server state (12 hooks across 7 query hooks and 5 mutations)
- `Zustand 5.x` — policy drag-and-drop panel state
- `React Hook Form 7.x + Zod 3.x` — reviewer decision form
- `date-fns 4.x` — timestamp formatting + stale analysis detection
- `Lucide React` — icons

**No new npm packages** — this feature uses only libraries already in the frontend stack.

## Running the Dev Server

```bash
cd apps/web
pnpm dev
```

Navigate to:
- `http://localhost:3000/trust-workbench` — Certification queue (US1)
- `http://localhost:3000/trust-workbench/{certificationId}` — Certification detail (US2, default: evidence + reviewer form)
- `http://localhost:3000/trust-workbench/{certificationId}?tab=trust-radar` — Trust radar chart (US3)
- `http://localhost:3000/trust-workbench/{certificationId}?tab=policies` — Policy attachment panel (US4)
- `http://localhost:3000/trust-workbench/{certificationId}?tab=privacy` — Privacy impact panel (US5)

## Running Tests

```bash
cd apps/web
pnpm exec vitest run __tests__/features/trust-workbench
PLAYWRIGHT_BASE_URL=http://localhost:3000 pnpm exec playwright test \
  e2e/trust-workbench-queue.spec.ts \
  e2e/trust-workbench-review.spec.ts \
  e2e/trust-workbench-policy.spec.ts
```

Test setup:
- Vitest + RTL for component tests
- `vi.mock` fixtures for component hooks + local E2E route stubs in `e2e/trust-workbench/helpers.ts`
- Playwright for E2E flows (certification queue browse, evidence review, policy attach)

## Project Structure

```text
apps/web/
├── app/(main)/trust-workbench/
│   ├── page.tsx                                  # Certification queue (US1)
│   └── [certificationId]/
│       └── page.tsx                              # Certification detail (US2–US5, tabbed)
│
├── components/features/trust-workbench/
│   ├── CertificationDataTable.tsx                # Queue DataTable with filters (US1)
│   ├── CertificationStatusBadge.tsx              # Status color-coded badge
│   ├── CertificationDetailView.tsx               # Tabbed detail container (US2–US5)
│   ├── StatusTimeline.tsx                        # Status history timeline (US2)
│   ├── EvidenceList.tsx                          # Evidence items list (US2)
│   ├── EvidenceItemCard.tsx                      # Collapsible evidence card (US2)
│   ├── ReviewerForm.tsx                          # Approve/reject + notes + upload (US2)
│   ├── TrustRadarChart.tsx                       # Recharts RadarChart 7 dimensions (US3)
│   ├── TrustDimensionTooltip.tsx                 # Custom Recharts tooltip (US3)
│   ├── PolicyAttachmentPanel.tsx                 # Split catalog + binding panel (US4)
│   ├── PolicyCatalog.tsx                         # Left panel: draggable policy cards (US4)
│   ├── PolicyBindingList.tsx                     # Right panel: binding drop zone (US4)
│   ├── PolicyBindingCard.tsx                     # Single binding with remove/manage (US4)
│   ├── PrivacyImpactPanel.tsx                    # Privacy analysis display (US5)
│   └── PrivacyDataCategoryRow.tsx                # Single data category row (US5)
│
├── lib/
│   ├── hooks/
│   │   ├── use-certifications.ts                 # useCertificationQueue, useCertification
│   │   ├── use-certification-actions.ts          # useApproveCertification, useRevokeCertification, useAddEvidenceRef
│   │   ├── use-trust-radar.ts                    # useTrustRadar
│   │   ├── use-privacy-impact.ts                 # usePrivacyImpact
│   │   ├── use-policy-catalog.ts                 # usePolicyCatalog
│   │   ├── use-effective-policies.ts             # useEffectivePolicies
│   │   └── use-policy-actions.ts                 # useAttachPolicy, useDetachPolicy
│   ├── stores/
│   │   └── use-policy-attachment-store.ts        # Zustand drag-and-drop state
│   └── types/
│       └── trust-workbench.ts                    # All TypeScript types for this feature
│
├── __tests__/
│   └── features/trust-workbench/
│       ├── CertificationDataTable.test.tsx
│       ├── CertificationDetailView.test.tsx
│       ├── ReviewerForm.test.tsx
│       ├── TrustRadarChart.test.tsx
│       ├── PolicyAttachmentPanel.test.tsx
│       └── PrivacyImpactPanel.test.tsx
│
└── e2e/
    ├── trust-workbench-queue.spec.ts
    ├── trust-workbench-review.spec.ts
    └── trust-workbench-policy.spec.ts
```

## Key Configuration

No new environment variables required. The feature uses the existing `NEXT_PUBLIC_API_BASE_URL` and auth token from the existing auth store.

**Sidebar entry**: Add "Trust Workbench" entry in `apps/web/components/layout/sidebar/nav-config.ts` with `requiredRoles: ['trust_certifier', 'platform_admin', 'superadmin']`.

**Drag-and-drop notes**: Uses HTML5 native drag events. No `@dnd-kit` or similar library needed. The `PolicyCatalog` cards are `draggable={true}`; the `PolicyBindingList` is the drop target. Incompatible policy warnings use `usePolicyAttachmentStore` Zustand store.

## API Assumptions

The implementation assumes these trust endpoints exist:

1. `GET /api/v1/trust/certifications` — global certification queue listing
2. `GET /api/v1/trust/agents/{agentId}/trust-profile` — 7-dimension radar data
3. `GET /api/v1/trust/agents/{agentId}/privacy-impact` — privacy analysis payload
4. `GET /api/v1/policies?workspace_id=...` — active policy catalog
5. `GET /api/v1/policies/effective/{agentId}?workspace_id=...` — effective policy bindings
6. `POST /api/v1/policies/{policyId}/attach` and `DELETE /api/v1/policies/{policyId}/attach/{attachmentId}` — direct binding mutations
7. `POST /api/v1/trust/certifications/{certId}/activate`, `POST /api/v1/trust/certifications/{certId}/revoke`, `POST /api/v1/trust/certifications/{certId}/evidence` — reviewer actions

Radar fallback is implemented only for trust posture:
1. `GET /api/v1/trust/agents/{agentId}/trust-profile` → preferred
2. `GET /api/v1/trust/agents/{agentId}/tier` → fallback mapped into the 7-dimension chart

Component tests use local fixtures, and the E2E specs stub these API responses through `e2e/trust-workbench/helpers.ts`.
