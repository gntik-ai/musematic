# API Contracts Consumed: Trust and Certification Workbench

**Phase**: Phase 1 — Design  
**Feature**: [../spec.md](../spec.md)

## Base URLs

- Trust API: `GET|POST /api/v1/trust/...`
- Policies API: `GET|POST|DELETE /api/v1/policies/...`

---

## TanStack Query Hook Map

| Hook | Method | Endpoint | Used In |
|------|--------|----------|---------|
| `useCertificationQueue(filters)` | GET | `/trust/certifications` | US1 queue DataTable |
| `useCertification(certId)` | GET | `/trust/certifications/{certId}` | US2 detail page |
| `useTrustRadar(agentId)` | GET | `/trust/agents/{agentId}/trust-profile` | US3 radar chart |
| `usePrivacyImpact(agentId)` | GET | `/trust/agents/{agentId}/privacy-impact` | US5 privacy panel |
| `usePolicyCatalog(workspaceId)` | GET | `/policies?workspace_id=...&status=active` | US4 catalog panel |
| `useEffectivePolicies(agentId, workspaceId)` | GET | `/policies/effective/{agentId}?workspace_id=...` | US4 binding list |
| `useApproveCertification()` | POST | `/trust/certifications/{id}/activate` | US2 reviewer form |
| `useRevokeCertification()` | POST | `/trust/certifications/{id}/revoke` | US2 reviewer form |
| `useAddEvidenceRef()` | POST | `/trust/certifications/{id}/evidence` | US2 (approval notes → evidence ref) |
| `useAttachPolicy()` | POST | `/policies/{policyId}/attach` | US4 drag-and-drop |
| `useDetachPolicy()` | DELETE | `/policies/{policyId}/attach/{attachmentId}` | US4 remove binding |

---

## Endpoint Specifications

### GET /api/v1/trust/certifications

**Purpose**: Global certification queue — all certifications across all agents and fleets.

**Query Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | `pending \| active \| expiring \| revoked \| superseded` | Filter by status |
| `search` | `string` | Free-text search on agent name or FQN (contains, case-insensitive) |
| `sort_by` | `expiration \| urgency \| created` | Sort order |
| `page` | `integer` (default: 1) | Page number |
| `page_size` | `integer` (default: 20, max: 100) | Items per page |

**Response** (`200 OK`):

```typescript
{
  items: CertificationListEntry[]  // agentFqn, status, expiresAt, evidenceCount, etc.
  total: number
  page: number
  pageSize: number
}
```

**Notes**: The `expiring` status filter returns `status=active` certs with `expiresAt` within 30 days, sorted by nearest expiration. This filtering is handled backend-side. The `evidenceCount` field is derived from `evidenceRefs.length` in the backend model.

---

### GET /api/v1/trust/certifications/{certificationId}

**Purpose**: Full certification record with evidence items.

**Response** (`200 OK`):

```typescript
{
  id: string
  agentId: string
  agentFqn: string
  agentRevisionId: string
  status: CertificationStatus          // 'pending' | 'active' | 'expired' | 'revoked' | 'superseded'
  issuedBy: string
  createdAt: string
  updatedAt: string
  expiresAt: string | null
  revokedAt: string | null
  revocationReason: string | null
  supersededById: string | null
  evidenceRefs: {
    id: string
    evidenceType: EvidenceType          // 'package_validation' | 'test_results' | 'policy_check' | 'guardrail_outcomes' | 'behavioral_regression' | 'ate_results' | 'manual_review'
    sourceRefType: string
    sourceRefId: string
    summary: string | null
    storageRef: string | null
    createdAt: string
  }[]
}
```

---

### POST /api/v1/trust/certifications/{certificationId}/activate

**Purpose**: Approve a pending certification (transitions status → active).

**Request body**: None

**Response** (`200 OK`): Updated `CertificationDetail`

**Notes**: Called as part of a two-step approval: (1) POST activate, (2) POST evidence ref with reviewer notes as `manual_review` evidence. Both calls use `useMutation` from TanStack Query. If the activate call succeeds but the evidence ref POST fails, the certification is still approved — the notes failure is non-blocking (logged, not surfaced as form error).

---

### POST /api/v1/trust/certifications/{certificationId}/revoke

**Purpose**: Reject a pending certification (transitions status → revoked).

**Request body**:

```typescript
{
  reason: string    // min_length: 1, max_length: 500 — maps to reviewer notes
}
```

**Response** (`200 OK`): Updated `CertificationDetail`

---

### POST /api/v1/trust/certifications/{certificationId}/evidence

**Purpose**: Add a reviewer evidence ref (used to persist approval notes).

**Request body**:

```typescript
{
  evidenceType: 'manual_review'
  sourceRefType: 'reviewer_decision'
  sourceRefId: string               // reviewer user ID (from auth store)
  summary: string                   // reviewer notes text
  storageRef: string | null         // MinIO ref if file was uploaded
}
```

**Response** (`201 Created`): `EvidenceItem`

---

### GET /api/v1/trust/agents/{agentId}/trust-profile

**Purpose**: Pre-computed trust radar data — 7 dimensions scored 0–100.

**Notes**: This endpoint is assumed to exist in the `trust-certifier` runtime profile. If not yet implemented, the hook falls back to the `GET /trust/agents/{agentId}/tier` endpoint with mapped scores (see research.md Decision 3).

**Response** (`200 OK`):

```typescript
{
  agentId: string
  agentFqn: string
  tier: TrustTierName
  overallScore: number               // 0–100
  dimensions: {
    dimension: TrustDimension
    label: string
    score: number                    // 0–100
    components: {
      name: string
      score: number
      anomalyCount?: number
      trend?: 'up' | 'down' | 'stable'
    }[]
  }[]
  lastComputedAt: string
}
```

---

### GET /api/v1/trust/agents/{agentId}/privacy-impact

**Purpose**: Most recent pre-computed privacy impact analysis for an agent.

**Notes**: This endpoint is assumed to exist as a read companion to `POST /trust/privacy/assess`. The assess POST is service-account-only; this GET is for trust officers.

**Response** (`200 OK`):

```typescript
{
  agentId: string
  analysisTimestamp: string
  overallCompliant: boolean
  dataSources: string[]
  categories: {
    name: string
    complianceStatus: 'compliant' | 'warning' | 'violation'
    retentionDuration: string | null
    concerns: {
      description: string
      severity: 'low' | 'medium' | 'high'
    }[]
    recommendations: string[]
  }[]
}
```

---

### GET /api/v1/policies

**Purpose**: Policy catalog — searchable list of active policies for the current workspace.

**Query Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | `UUID` | Required — workspace-scoped results |
| `status` | `active` | Default: active only |
| `search` | `string` | Free-text search on name |
| `scope_type` | `PolicyScopeType` | Optional scope filter |
| `page` | `integer` | Default: 1 |
| `page_size` | `integer` | Default: 20, max: 100 |

**Response** (`200 OK`):

```typescript
{
  items: PolicySummary[]
  total: number
  page: number
  pageSize: number
}
```

---

### GET /api/v1/policies/effective/{agentId}

**Purpose**: Resolved effective policy set for an agent — includes inheritance chain.

**Query Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | `UUID` | Required |

**Response** (`200 OK`):

```typescript
{
  agentId: string
  resolvedRules: {
    rule: Record<string, unknown>
    provenance: {
      ruleId: string
      policyId: string
      versionId: string
      scopeLevel: number
      scopeType: PolicyScopeType
      scopeTargetId: string | null    // workspace/fleet ID for inherited bindings
    }
  }[]
  conflicts: PolicyConflict[]
  sourcePolicies: string[]           // policy UUIDs — used to fetch PolicySummary for display
}
```

**Notes**: The `sourcePolicies` list is used to fetch `PolicySummary` details (name, description) for each unique policy in the binding list. The `scopeTargetId` identifies the source workspace or fleet, which is resolved to a display name via the workspaces/fleets API.

---

### POST /api/v1/policies/{policyId}/attach

**Purpose**: Attach a policy directly to an agent revision.

**Request body**:

```typescript
{
  targetType: 'agent_revision'
  targetId: string                   // agentRevisionId from the certification detail
  policyVersionId: string | null     // null = attach latest version
}
```

**Response** (`201 Created`):

```typescript
{
  id: string                         // attachmentId — stored for DELETE call
  policyId: string
  policyVersionId: string
  targetType: AttachmentTargetType
  targetId: string | null
  isActive: boolean
  createdAt: string
}
```

---

### DELETE /api/v1/policies/{policyId}/attach/{attachmentId}

**Purpose**: Remove a direct policy binding from an agent.

**Response**: `204 No Content`

**Notes**: Only shown for `source === 'direct'` bindings. Inherited bindings show a "Manage" link pointing to the source entity.

---

## Error Handling

| Status | Component | Behavior |
|--------|-----------|----------|
| `404` | `useCertification` | Show "Certification not found" with back button |
| `409` | `useApproveCertification` / `useRevokeCertification` | Show "A decision has already been recorded — please refresh" (concurrent review optimistic locking) |
| `412` | `useApproveCertification` | Show stale data alert with "Refresh" action |
| `422` | `useRevokeCertification` | Inline form validation error |
| `403` | Any mutation | Show "You do not have permission to perform this action" |
| `429` | `useAttachPolicy` | Show "Too many requests — please wait a moment" |

---

## Query Invalidation Strategy

```typescript
// After useApproveCertification or useRevokeCertification:
queryClient.invalidateQueries({ queryKey: ['certification', certificationId] })
queryClient.invalidateQueries({ queryKey: ['certificationQueue'] })

// After useAddEvidenceRef:
queryClient.invalidateQueries({ queryKey: ['certification', certificationId] })

// After useAttachPolicy or useDetachPolicy:
queryClient.invalidateQueries({ queryKey: ['effectivePolicies', agentId] })

// After useDetachPolicy (optimistic update):
// Remove the deleted binding from the local cache immediately
// Rollback on error
```
