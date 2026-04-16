# Data Model: Trust and Certification Workbench

**Phase**: Phase 1 — Design  
**Feature**: [spec.md](spec.md)

## TypeScript Types

### Enumerations

```typescript
// CertificationStatus — maps to backend CertificationStatus enum
// Note: 'expiring' is a derived UI-only status (active certs expiring within 30 days)
export type CertificationStatus =
  | 'pending'
  | 'active'
  | 'expired'
  | 'revoked'
  | 'superseded'

export type CertificationQueueStatus =
  | 'pending'
  | 'expiring'   // UI-only: active + expiresAt within 30 days
  | 'revoked'

// EvidenceType — maps to backend EvidenceType enum
export type EvidenceType =
  | 'package_validation'
  | 'test_results'
  | 'policy_check'
  | 'guardrail_outcomes'
  | 'behavioral_regression'
  | 'ate_results'
  | 'manual_review' // used when reviewer notes are stored as evidence

// EvidenceResult — derived from evidence summary / backend evaluation
export type EvidenceResult = 'pass' | 'fail' | 'partial' | 'unknown'

// Trust tier (from backend TrustTierName)
export type TrustTierName = 'certified' | 'provisional' | 'untrusted'

// The 7 fixed trust dimensions (platform trust framework — immutable)
export type TrustDimension =
  | 'identity_auth'
  | 'authorization_access'
  | 'behavioral_compliance'
  | 'explainability'
  | 'evaluation_quality'
  | 'privacy_data'
  | 'certification_audit'

export const TRUST_DIMENSION_LABELS: Record<TrustDimension, string> = {
  identity_auth: 'Identity & Authentication',
  authorization_access: 'Authorization & Access Control',
  behavioral_compliance: 'Behavioral Compliance',
  explainability: 'Explainability',
  evaluation_quality: 'Evaluation Quality',
  privacy_data: 'Privacy & Data Protection',
  certification_audit: 'Certification & Audit Trail',
}

// Policy scope and attachment types (from backend enums)
export type PolicyScopeType = 'global' | 'deployment' | 'workspace' | 'agent' | 'execution'
export type AttachmentTargetType = 'global' | 'deployment' | 'workspace' | 'agent_revision' | 'fleet' | 'execution'

// Policy binding source — derived from scope_type for display
export type PolicyBindingSource = 'direct' | 'workspace' | 'fleet' | 'global' | 'deployment'

// Privacy compliance status
export type PrivacyComplianceStatus = 'compliant' | 'warning' | 'violation'
```

---

### Certification Entities

```typescript
// CertificationListEntry — used in queue DataTable (US1)
export interface CertificationListEntry {
  id: string                            // UUID
  agentId: string
  agentFqn: string                      // namespace:local_name
  agentRevisionId: string
  status: CertificationStatus
  issuedBy: string
  createdAt: string                     // ISO 8601
  updatedAt: string
  expiresAt: string | null
  revokedAt: string | null
  revocationReason: string | null
  evidenceCount: number                 // derived from evidenceRefs.length
  // Fleet association (if certification covers a fleet)
  fleetId?: string
  fleetName?: string
}

// CertificationDetail — full record for detail page (US2)
export interface CertificationDetail extends CertificationListEntry {
  supersededById: string | null
  evidenceItems: EvidenceItem[]
  statusHistory: CertificationStatusEvent[] // derived from audit trail
}

// CertificationStatusEvent — for timeline display (US2)
export interface CertificationStatusEvent {
  status: CertificationStatus
  timestamp: string
  actor: string
  notes: string | null
}

// EvidenceItem — single evidence entry (US2)
export interface EvidenceItem {
  id: string
  evidenceType: EvidenceType
  sourceRefType: string
  sourceRefId: string
  summary: string | null
  storageRef: string | null
  createdAt: string
  result: EvidenceResult               // derived from summary content
}
```

---

### Trust Radar Entities

```typescript
// TrustDimensionScore — single axis of the radar chart
export interface TrustDimensionScore {
  dimension: TrustDimension
  label: string                         // human-readable label
  score: number                         // 0–100
  components: TrustDimensionComponent[]
  isWeak: boolean                       // score < 30 — triggers warning highlight
}

// TrustDimensionComponent — breakdown shown in hover tooltip
export interface TrustDimensionComponent {
  name: string
  score: number
  anomalyCount?: number
  trend?: 'up' | 'down' | 'stable'
}

// TrustRadarProfile — consumed from GET /trust/agents/{agentId}/trust-profile (US3)
// Falls back to GET /trust/agents/{agentId}/tier if extended endpoint unavailable
export interface TrustRadarProfile {
  agentId: string
  agentFqn: string
  tier: TrustTierName
  overallScore: number                  // 0–100 composite
  dimensions: TrustDimensionScore[]    // exactly 7 entries
  lastComputedAt: string
  // Fleet-level aggregation (US3 fleet scenario)
  isFleetAggregate?: boolean
  memberCount?: number
}

// TrustRadarChartDataPoint — reshaped for Recharts RadarChart
// Recharts expects: { subject: string, score: number, fullMark: number }
export interface TrustRadarChartDataPoint {
  subject: string                       // dimension label
  score: number
  fullMark: 100
  dimension: TrustDimension            // for tooltip lookup
}
```

---

### Policy Binding Entities

```typescript
// PolicySummary — catalog item shown in left panel (US4)
export interface PolicySummary {
  id: string
  name: string
  description: string | null
  scopeType: PolicyScopeType
  status: 'active' | 'archived'
  workspaceId: string | null
  currentVersionId: string | null
}

// PolicyBinding — effective binding shown in right panel (US4)
export interface PolicyBinding {
  attachmentId: string                  // used for DELETE /policies/{id}/attach/{attachmentId}
  policyId: string
  policyVersionId: string
  policyName: string
  policyDescription: string | null
  scopeType: PolicyScopeType
  targetType: AttachmentTargetType
  targetId: string | null
  isActive: boolean
  createdAt: string
  // Derived display fields
  source: PolicyBindingSource           // 'direct' | 'workspace' | 'fleet' | 'global'
  sourceLabel: string | null           // e.g. "Marketing" (workspace name), "Fraud Detection Fleet"
  sourceEntityUrl: string | null       // link to source entity where inherited binding can be managed
  canRemove: boolean                   // true only for source === 'direct'
}

// EffectivePolicyResolution — raw response from GET /policies/effective/{agentId}
export interface EffectivePolicyResolution {
  agentId: string
  resolvedRules: ResolvedRule[]
  conflicts: PolicyConflict[]
  sourcePolicies: string[]             // policy UUIDs
}

export interface ResolvedRule {
  rule: Record<string, unknown>
  provenance: PolicyRuleProvenance
}

export interface PolicyRuleProvenance {
  ruleId: string
  policyId: string
  versionId: string
  scopeLevel: number
  scopeType: PolicyScopeType
  scopeTargetId: string | null
}

export interface PolicyConflict {
  ruleId: string
  winnerScope: PolicyScopeType
  loserScope: PolicyScopeType
  resolution: 'more_specific_scope_wins' | 'deny_wins'
}
```

---

### Privacy Impact Entities

```typescript
// PrivacyImpactAnalysis — consumed from GET /trust/agents/{agentId}/privacy-impact (US5)
export interface PrivacyImpactAnalysis {
  agentId: string
  analysisTimestamp: string            // ISO 8601 — used to detect stale (>24h)
  overallCompliant: boolean
  dataSources: string[]                // e.g. ["evaluation_results", "behavioral_logs"]
  categories: PrivacyDataCategory[]
}

export interface PrivacyDataCategory {
  name: string                         // e.g. "User PII", "Financial Data"
  complianceStatus: PrivacyComplianceStatus
  retentionDuration: string | null    // e.g. "30 days", "Until session end"
  concerns: PrivacyConcern[]
  recommendations: string[]
}

export interface PrivacyConcern {
  description: string                  // e.g. "Agent retains user email beyond 30-day policy limit"
  severity: 'low' | 'medium' | 'high'
}
```

---

### Form Types

```typescript
// ReviewDecisionFormValues — React Hook Form + Zod (US2 reviewer form)
export interface ReviewDecisionFormValues {
  decision: 'approve' | 'reject'
  notes: string                        // mandatory, min 10 chars
  supportingFiles?: File[]             // optional file upload (PDF/PNG/JPG, max 10MB each)
}

// CertificationQueueFilters — URL-sync state for queue (US1)
export interface CertificationQueueFilters {
  status: CertificationQueueStatus | 'all'
  certType: string | null
  entityType: 'agent' | 'fleet' | null
  search: string
  sortBy: 'expiration' | 'urgency' | 'created'
  page: number
  pageSize: 20 | 50 | 100
}
```

---

### Zustand State

```typescript
// PolicyAttachmentStore — drag-and-drop interaction state (US4)
// Stored in lib/stores/use-policy-attachment-store.ts
// NOT persisted (session-only)
export interface PolicyAttachmentStore {
  isDragging: boolean
  draggedPolicyId: string | null
  draggedPolicyName: string | null
  dropError: string | null
  // Actions
  startDrag: (policyId: string, policyName: string) => void
  endDrag: () => void
  setDropError: (error: string | null) => void
  clearDropError: () => void
}
```

---

## Entity Relationships

```text
CertificationListEntry
  └─ has many → EvidenceItem (evidenceItems[])
  └─ has many → CertificationStatusEvent (statusHistory[])
  └─ belongs to agent → agentId / agentFqn

TrustRadarProfile
  └─ belongs to agent → agentId / agentFqn
  └─ has 7 → TrustDimensionScore (dimensions[])
  └─ each dimension has many → TrustDimensionComponent (components[])

PolicyBinding (from EffectivePolicyResolution)
  └─ belongs to agent (target) → targetId
  └─ belongs to policy → policyId
  └─ has source derivation → PolicyRuleProvenance

PrivacyImpactAnalysis
  └─ belongs to agent → agentId
  └─ has many → PrivacyDataCategory (categories[])
  └─ each category has many → PrivacyConcern
```

---

## State Transitions

```text
Certification Status Lifecycle (from spec):
  pending → active (on Approve — POST /activate)
  pending → rejected (on Reject — POST /revoke)
  active → expired (automated, on expiresAt)
  active → revoked (POST /revoke)
  active → superseded (when new certification created for same agent)

Queue Tab Mapping:
  "Pending" tab → status=pending
  "Expiring" tab → status=active + expires_at within 30 days (backend sorts by nearest expiration)
  "Revoked" tab → status=revoked
```
