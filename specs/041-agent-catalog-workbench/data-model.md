# Data Model: Agent Catalog and Creator Workbench

**Feature**: 041-agent-catalog-workbench  
**Type**: Frontend TypeScript types and component state model (no new DB tables — data sourced from registry, composition, policy, and trust APIs)

---

## TypeScript Types

### Agent Catalog Entry

```typescript
// Catalog list item (from GET /api/v1/registry/agents)
interface AgentCatalogEntry {
  fqn: string;                    // "namespace:local_name"
  namespace: string;
  local_name: string;
  name: string;                   // Display name
  maturity_level: AgentMaturity;
  status: AgentStatus;
  revision_count: number;
  latest_revision_number: number;
  updated_at: string;             // ISO8601
  workspace_id: string;
}

type AgentMaturity = "experimental" | "beta" | "production" | "deprecated";
type AgentStatus = "draft" | "active" | "archived" | "pending_review";
```

### Agent Detail

```typescript
// Full agent record (from GET /api/v1/registry/agents/{fqn})
interface AgentDetail extends AgentCatalogEntry {
  description: string;
  tags: string[];
  category: string;
  purpose: string;                // min 20 chars
  approach: string | null;
  role_type: AgentRoleType;
  custom_role: string | null;     // only when role_type === "custom"
  reasoning_modes: string[];
  visibility_patterns: VisibilityPattern[];
  model_config: Record<string, unknown>;
  tool_selections: string[];
  connector_suggestions: string[];
  policy_ids: string[];
  context_profile_id: string | null;
  source_revision_id: string | null;
}

type AgentRoleType =
  | "executor"
  | "planner"
  | "orchestrator"
  | "observer"
  | "judge"
  | "enforcer"
  | "custom";

interface VisibilityPattern {
  pattern: string;               // e.g., "finance-ops:*" or exact FQN
  description: string | null;
}
```

### Health Score

```typescript
// (from GET /api/v1/registry/agents/{fqn}/health)
interface AgentHealthScore {
  composite_score: number;        // 0–100
  components: HealthScoreComponent[];
  computed_at: string;
}

interface HealthScoreComponent {
  label: string;                  // e.g., "Evaluation Quality", "Policy Conformance"
  score: number;                  // 0–100
  weight: number;                 // proportion of composite
}
```

### Agent Revision

```typescript
// (from GET /api/v1/registry/agents/{fqn}/revisions)
interface AgentRevision {
  revision_id: string;
  revision_number: number;
  fqn: string;
  status: AgentStatus;
  created_at: string;
  created_by: string;             // user display name
  change_summary: string;
  is_current: boolean;
}

// (from GET /api/v1/registry/agents/{fqn}/revisions/{a}/diff/{b})
interface RevisionDiff {
  base_revision_number: number;
  compare_revision_number: number;
  base_content: string;           // serialized YAML/JSON of base revision config
  compare_content: string;        // serialized YAML/JSON of compare revision config
  changed_fields: string[];       // high-level list of what changed
}
```

### Publication

```typescript
// (from POST /api/v1/registry/agents/{fqn}/validate)
interface ValidationResult {
  passed: boolean;
  checks: ValidationCheck[];
}

interface ValidationCheck {
  name: string;
  passed: boolean;
  message: string | null;
}

// (from POST /api/v1/registry/agents/{fqn}/publish)
interface PublicationSummary {
  fqn: string;
  previous_status: AgentStatus;
  new_status: "active";
  affected_workspaces: string[];  // workspace names
  published_at: string;
}
```

### Composition Blueprint

```typescript
// (from POST /api/v1/composition/agent-blueprint)
interface CompositionBlueprint {
  blueprint_id: string;
  description: string;
  low_confidence: boolean;
  follow_up_questions: string[];
  model_config: BlueprintItem<Record<string, unknown>>;
  tool_selections: BlueprintItem<string[]>;
  connector_suggestions: BlueprintItem<string[]>;
  policy_recommendations: BlueprintItem<string[]>;
  context_profile: BlueprintItem<Record<string, unknown>>;
}

interface BlueprintItem<T> {
  value: T;
  reasoning: string;
  confidence: number;             // 0.0–1.0
}
```

---

## Component State Model

### Composition Wizard Store (Zustand)

```typescript
interface CompositionWizardState {
  step: 1 | 2 | 3 | 4;
  description: string;
  blueprint: CompositionBlueprint | null;
  customizations: Partial<{
    model_config: Record<string, unknown>;
    tool_selections: string[];
    connector_suggestions: string[];
    policy_recommendations: string[];
  }>;
  validation_result: ValidationResult | null;
  is_loading: boolean;
  error: string | null;
  // Actions
  setStep: (step: 1 | 2 | 3 | 4) => void;
  setDescription: (description: string) => void;
  setBlueprint: (blueprint: CompositionBlueprint) => void;
  applyCustomization: (field: string, value: unknown) => void;
  setValidationResult: (result: ValidationResult | null) => void;
  reset: () => void;
}
```

### Metadata Editor Form Schema (Zod)

```typescript
// Zod schema for metadata editor (RHF)
const MetadataFormSchema = z.object({
  namespace: z.string().min(1, "Namespace is required"),
  local_name: z.string().min(1, "Local name is required").regex(/^[a-z0-9-]+$/, "Lowercase alphanumeric and hyphens only"),
  name: z.string().min(1).max(100),
  description: z.string().min(1).max(2000),
  purpose: z.string().min(20, "Purpose must be at least 20 characters"),
  approach: z.string().max(5000).nullable(),
  tags: z.array(z.string()).max(20),
  category: z.string().min(1),
  maturity_level: z.enum(["experimental", "beta", "production", "deprecated"]),
  role_type: z.enum(["executor", "planner", "orchestrator", "observer", "judge", "enforcer", "custom"]),
  custom_role: z.string().min(1).max(50).nullable(),
  reasoning_modes: z.array(z.string()).min(1, "At least one reasoning mode required"),
  visibility_patterns: z.array(z.object({
    pattern: z.string().min(1),
    description: z.string().nullable(),
  })),
});
```

---

## Catalog Filter State

```typescript
// URL search params managed via useSearchParams()
interface AgentCatalogFilters {
  search: string;         // free-text filter (debounced 300ms)
  namespace: string[];    // multi-select
  maturity: AgentMaturity[];
  status: AgentStatus[];
  sort_by: "name" | "updated_at" | "maturity";
  sort_order: "asc" | "desc";
  limit: number;          // default 20
  cursor: string | null;
}
```
