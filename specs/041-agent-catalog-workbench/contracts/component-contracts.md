# Component Contracts: Agent Catalog and Creator Workbench

Documents key component prop interfaces and rendering contracts.

---

## AgentDataTable

```typescript
interface AgentDataTableProps {
  workspace_id: string;
}
// Internal: uses useAgents() hook with useSearchParams() for filter state
// Renders: shadcn DataTable + SearchInput + FilterBar + pagination
// Navigation: onClick row → router.push(`/agent-management/${encodeURIComponent(fqn)}`)
```

---

## AgentMaturityBadge

```typescript
interface AgentMaturityBadgeProps {
  maturity: AgentMaturity;
  size?: "sm" | "md";
}
// Colors: experimental=gray, beta=blue, production=green, deprecated=red
// Uses shadcn Badge with variant mapping
```

---

## AgentHealthScoreGauge

```typescript
interface AgentHealthScoreGaugeProps {
  fqn: string;           // drives useAgentHealth() hook internally
  showBreakdown?: boolean; // default true — shows component scores in Tooltip
  size?: "sm" | "lg";    // sm for card, lg for detail page
}
// Extends ScoreGauge shared component with breakdown Tooltip
// Colors: < 40 = red (destructive), 40–70 = yellow (warning), > 70 = green (success)
```

---

## AgentMetadataEditor

```typescript
interface AgentMetadataEditorProps {
  fqn: string;             // pre-fills form with current agent data
  onSaved?: () => void;
}
// Uses useAgent(fqn) to pre-fill, useUpdateAgentMetadata() to save
// React Hook Form + Zod (MetadataFormSchema)
// Shows FQNInput, VisibilityPatternPanel, RoleTypeSelector
// Last-Modified header tracked for 412 conflict detection
```

---

## FQNInput

```typescript
interface FQNInputProps {
  namespace: string;
  localName: string;
  onNamespaceChange: (ns: string) => void;
  onLocalNameChange: (name: string) => void;
  disabled?: boolean;
}
// Preview: renders "{namespace}:{local_name}" live
// Namespace: shadcn Select populated by useNamespaces()
// local_name: shadcn Input with regex validation
```

---

## VisibilityPatternPanel

```typescript
interface VisibilityPatternPanelProps {
  patterns: VisibilityPattern[];
  onChange: (patterns: VisibilityPattern[]) => void;
  disabled?: boolean;
}
// Add/remove FQN patterns
// Shows preview of which agents/tools each pattern matches (informational tooltip)
```

---

## RoleTypeSelector

```typescript
interface RoleTypeSelectorProps {
  value: AgentRoleType;
  customRole?: string;
  onValueChange: (type: AgentRoleType, customRole?: string) => void;
  disabled?: boolean;
}
// shadcn Select with 7 options
// When "custom" selected: reveals shadcn Input for custom role name
```

---

## AgentUploadZone

```typescript
interface AgentUploadZoneProps {
  workspace_id: string;
  onUploadComplete: (fqn: string) => void;
}
// Accepts .tar.gz and .zip only (client-side validation before XHR)
// Shows shadcn Progress bar during upload
// Cancel button during active upload
// Displays validation errors as shadcn Alert after upload
```

---

## AgentPublicationPanel

```typescript
interface AgentPublicationPanelProps {
  fqn: string;
  currentStatus: AgentStatus;
  onPublished: () => void;
}
// "Validate" button → useValidateAgent() → shows ValidationResultDisplay
// "Publish" button (disabled until validation passes) → opens PublicationConfirmDialog
// Uses useValidateAgent(), usePublishAgent()
```

---

## PublicationConfirmDialog

```typescript
interface PublicationConfirmDialogProps {
  open: boolean;
  fqn: string;
  summary: PublicationSummary | null;   // pre-fetched summary to show
  onConfirm: () => void;
  onCancel: () => void;
}
// shadcn AlertDialog with summary of: affected workspaces, status change, visibility impact
```

---

## AgentRevisionTimeline

```typescript
interface AgentRevisionTimelineProps {
  fqn: string;
  onSelectForDiff?: (revisions: [number, number]) => void;
  onRollback?: (revisionNumber: number) => void;
}
// Uses useAgentRevisions(fqn)
// Checkbox multi-select for diff (exactly 2)
// "Compare selected" button → calls onSelectForDiff
// "Rollback" button per revision → shadcn AlertDialog confirmation
```

---

## RevisionDiffViewer

```typescript
interface RevisionDiffViewerProps {
  fqn: string;
  baseRevision: number;
  compareRevision: number;
}
// Uses useRevisionDiff(fqn, base, compare)
// Renders Monaco MonacoDiffEditor (readOnly, language: "yaml")
// Language: YAML serialization of revision config
```

---

## CompositionWizard

```typescript
// No props — reads/writes from useCompositionWizardStore()
// Renders step 1–4 based on store.step
// Navigation: "Next" advances step, "Back" regresses, "Cancel" resets store
```

### WizardStepReviewBlueprint

```typescript
interface WizardStepReviewBlueprintProps {
  blueprint: CompositionBlueprint;
}
// For each BlueprintItem: shows value, confidence badge, reasoning in shadcn Accordion
// Low confidence (< 0.5) items highlighted with shadcn Alert (warning variant)
```
