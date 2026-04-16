# Component Contracts: Trust and Certification Workbench

**Phase**: Phase 1 — Design  
**Feature**: [../spec.md](../spec.md)

---

## CertificationDataTable

```typescript
// apps/web/components/features/trust-workbench/CertificationDataTable.tsx
interface CertificationDataTableProps {
  data: CertificationListEntry[]
  totalCount: number
  filters: CertificationQueueFilters
  isLoading: boolean
  onFiltersChange: (filters: Partial<CertificationQueueFilters>) => void
  onRowClick: (certificationId: string) => void
}
```

**Behavior**: Renders a TanStack Table DataTable with columns: entity name/FQN, certification type, status badge, expiration date, evidence count. Search input debounced at 300ms. Tab bar for pending/expiring/revoked/all status categories. Sort by expiration date or urgency. Pagination with page size selector.

---

## CertificationStatusBadge

```typescript
// apps/web/components/features/trust-workbench/CertificationStatusBadge.tsx
interface CertificationStatusBadgeProps {
  status: CertificationStatus | 'expiring'
  expiresAt?: string | null           // used to show "X days" countdown for expiring
  size?: 'sm' | 'md'
}
```

**Behavior**: shadcn/ui `Badge` with status-appropriate variant:
- `pending` → yellow/warning
- `active` → green
- `expiring` → orange (active certs nearing expiry)
- `expired` → gray
- `revoked` → red/destructive
- `superseded` → muted

---

## CertificationDetailView

```typescript
// apps/web/components/features/trust-workbench/CertificationDetailView.tsx
interface CertificationDetailViewProps {
  certification: CertificationDetail
  agentId: string
  agentRevisionId: string
  workspaceId: string
}
```

**Behavior**: Top-level container for the certification detail page. Renders entity info header (name, FQN, certification type, current status). Contains a `StatusTimeline` below the header. Below the timeline: `EvidenceList` (US2) + `ReviewerForm` (US2). Additional panels for `TrustRadarChart` (US3), `PolicyAttachmentPanel` (US4), `PrivacyImpactPanel` (US5) via shadcn/ui Tabs with URL `?tab=` routing.

---

## StatusTimeline

```typescript
// apps/web/components/features/trust-workbench/StatusTimeline.tsx
interface StatusTimelineProps {
  events: CertificationStatusEvent[]
  currentStatus: CertificationStatus
}
```

**Behavior**: Renders a vertical timeline (shared `Timeline` component from feature 015). Each event shows status label, actor, timestamp, and optional notes. Current status is highlighted. Events sorted newest-first.

---

## EvidenceList

```typescript
// apps/web/components/features/trust-workbench/EvidenceList.tsx
interface EvidenceListProps {
  items: EvidenceItem[]
  isLoading?: boolean
}
```

**Behavior**: Renders a list of `EvidenceItemCard` components. Shows empty state "No evidence collected yet" when `items.length === 0`. Each item is collapsible.

---

## EvidenceItemCard

```typescript
// apps/web/components/features/trust-workbench/EvidenceItemCard.tsx
interface EvidenceItemCardProps {
  item: EvidenceItem
}
```

**Behavior**: shadcn/ui `Collapsible`. Collapsed state shows: evidence type label, result badge (green pass / red fail / yellow partial / gray unknown), and collection timestamp. Expanded state shows full supporting data (summary text + JSON payload via `JsonViewer` shared component if `storageRef` is present). The `result` is derived from the summary string (contains "pass"/"fail"/"partial" keywords) or from the `evidenceType` + `sourceRefType` combination.

**Result badge colors**:
- `pass` → green
- `fail` → red/destructive
- `partial` → yellow/warning
- `unknown` → muted/gray

---

## ReviewerForm

```typescript
// apps/web/components/features/trust-workbench/ReviewerForm.tsx
interface ReviewerFormProps {
  certificationId: string
  agentId: string
  currentStatus: CertificationStatus
  isExpired: boolean                  // true when certification expired during review
  onDecisionSubmitted: () => void
}
```

**Behavior**: React Hook Form + Zod. Fields:
- **Decision** (required): Radio group or segmented control — "Approve" / "Reject"
- **Notes** (required): Textarea, min 10 chars validation, shows "Review notes are required." on empty submit
- **Supporting files** (optional): File input, accepts PDF/PNG/JPG, max 10MB each, max 5 files

When `isExpired` is true: Decision options change to "Renew" / "Reject" (edge case from spec).

On submit:
1. `useRevokeCertification()` mutation if decision === 'reject' (notes → reason)
2. `useApproveCertification()` + `useAddEvidenceRef()` if decision === 'approve'
3. File upload to evidence ref if files attached

Shows inline validation error "Review notes are required." when notes field is empty on submit. Shows server error via toast notification on mutation failure.

---

## TrustRadarChart

```typescript
// apps/web/components/features/trust-workbench/TrustRadarChart.tsx
interface TrustRadarChartProps {
  profile: TrustRadarProfile
  className?: string
}
```

**Behavior**: Recharts `RadarChart` + `Radar` + `PolarGrid` + `PolarAngleAxis` + `PolarRadiusAxis` + `ResponsiveContainer`. 7 axes, each 0–100. Custom `TrustDimensionTooltip` on hover. Weak dimensions (score < 30) render with a distinct warning fill color (`fill-amber-400/40` dark: `fill-amber-600/40`). Renders correctly in both light and dark mode via Tailwind dark: classes and Recharts `stroke` props.

---

## TrustDimensionTooltip

```typescript
// apps/web/components/features/trust-workbench/TrustDimensionTooltip.tsx
// Used as Recharts custom tooltip
interface TrustDimensionTooltipProps {
  active?: boolean
  payload?: Array<{ name: string; value: number; payload: TrustRadarChartDataPoint }>
  dimensionScores: TrustDimensionScore[]  // full dimension detail for component breakdown
}
```

**Behavior**: When `active` and `payload` exist, shows a shadcn/ui `Card` tooltip with: dimension label, overall score, and a list of component scores with trend indicators. Shows anomaly count for behavioral compliance dimension.

---

## PolicyAttachmentPanel

```typescript
// apps/web/components/features/trust-workbench/PolicyAttachmentPanel.tsx
interface PolicyAttachmentPanelProps {
  agentId: string
  agentRevisionId: string
  workspaceId: string
}
```

**Behavior**: Two-column layout. Left: `PolicyCatalog` (searchable list of available policies). Right: `PolicyBindingList` (current effective bindings). Drop zone occupies the right panel area. Uses `usePolicyAttachmentStore` Zustand store to track drag state.

---

## PolicyCatalog

```typescript
// apps/web/components/features/trust-workbench/PolicyCatalog.tsx
interface PolicyCatalogProps {
  workspaceId: string
  onPolicyDragStart: (policyId: string, policyName: string) => void
  onPolicyDragEnd: () => void
}
```

**Behavior**: Searchable list of active policies from `usePolicyCatalog`. Each policy card is `draggable={true}` with `onDragStart` that sets `dataTransfer.setData('policyId', id)` and calls `onPolicyDragStart`. Visual drag affordance (cursor: grab). Search input at top of panel with 300ms debounce.

---

## PolicyBindingList

```typescript
// apps/web/components/features/trust-workbench/PolicyBindingList.tsx
interface PolicyBindingListProps {
  bindings: PolicyBinding[]
  isLoading: boolean
  agentId: string
  agentRevisionId: string
  workspaceId: string
  isDragOver: boolean
  dropError: string | null
  onDrop: (policyId: string) => void
  onDragOver: (e: React.DragEvent) => void
  onDragLeave: () => void
}
```

**Behavior**: Renders a `PolicyBindingCard` for each binding. Drop zone: `onDrop` calls the attach mutation. `isDragOver` shows a highlighted drop target (dashed border + background tint). `dropError` shows a red outline with tooltip explaining incompatibility. Empty state: "No policies attached. Drag a policy here to attach it."

---

## PolicyBindingCard

```typescript
// apps/web/components/features/trust-workbench/PolicyBindingCard.tsx
interface PolicyBindingCardProps {
  binding: PolicyBinding
  onRemove?: (attachmentId: string) => void   // undefined for inherited bindings
}
```

**Behavior**: Shows policy name, type, enforcement status badge (active/suspended), and source label (e.g. "direct", "workspace: Marketing", "fleet: Fraud Detection Fleet"). Direct bindings: shows "Remove" button that triggers `ConfirmDialog`. Inherited bindings: shows source label + "Manage →" link to source entity URL instead of Remove button.

---

## PrivacyImpactPanel

```typescript
// apps/web/components/features/trust-workbench/PrivacyImpactPanel.tsx
interface PrivacyImpactPanelProps {
  agentId: string
}
```

**Behavior**: Consumes `usePrivacyImpact(agentId)`. Shows analysis metadata header (timestamp, data sources). Shows stale data warning banner if `analysisTimestamp` is older than 24 hours, with "Request Re-analysis" button. Shows overall compliance summary badge. Lists `PrivacyDataCategoryRow` for each category. Shows "No privacy concerns identified." summary for fully compliant agents.

---

## PrivacyDataCategoryRow

```typescript
// apps/web/components/features/trust-workbench/PrivacyDataCategoryRow.tsx
interface PrivacyDataCategoryRowProps {
  category: PrivacyDataCategory
}
```

**Behavior**: Shows category name, compliance status badge (green compliant / yellow warning / red violation), retention duration, and concerns list. Violations are highlighted in red with the concern description and recommendations. Compliant categories show only the green badge — concerns list is not shown.
