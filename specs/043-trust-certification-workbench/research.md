# Research: Trust and Certification Workbench

**Phase**: Phase 0 — Research  
**Feature**: [spec.md](spec.md)

## Decision 1: Certification Queue Endpoint

**Decision**: Use `GET /api/v1/trust/certifications` global listing with query params for the queue.

**Rationale**: The backend trust API currently exposes `GET /api/v1/trust/agents/{agent_id}/certifications` (per-agent listing) and `GET /api/v1/trust/certifications/{certification_id}` (single record). A workbench queue requires a global listing across all agents. The pattern is a natural extension: `GET /api/v1/trust/certifications?status=pending&page=1&page_size=20`. The backend already has all the filter fields in the data model (status, expires_at, agent_id, evidence count). This endpoint either exists or is a low-effort addition to the trust certifier runtime profile.

**Query parameters assumed**: `status` (pending | active | expiring | revoked | rejected), `certification_type`, `entity_type` (agent | fleet), `search` (FQN / name contains), `sort_by` (expiration | urgency | created), `page`, `page_size`.

**Alternatives considered**:
- Per-agent polling — not viable for a cross-agent workbench queue
- Client-side aggregation — would require knowing all agent IDs in advance

---

## Decision 2: Route Structure

**Decision**: Two-route structure — queue page + certification detail page.

```
app/(main)/trust-workbench/
  page.tsx                          # Certification queue (US1)
  [certificationId]/
    page.tsx                        # Certification detail with tabbed panels (US2–US5)
```

**Rationale**: The certification detail (US2), trust radar (US3), policy attachment (US4), and privacy impact (US5) all contextualise a single certified entity. Grouping them in a tabbed layout under the certification detail keeps navigation coherent and avoids separate routes for each panel. US3–US5 are rendered as additional tabs within the certification detail page (`?tab=trust-radar`, `?tab=policies`, `?tab=privacy`).

**Alternatives considered**:
- Separate `/trust-workbench/agents/[agentId]` route — US2 is about a certification record, not an agent; the certification ID is the natural primary key
- Nested routes per panel — over-engineered; tab state with URL query param is sufficient and consistent with features 027 and 041

---

## Decision 3: Trust Radar Chart Data Source

**Decision**: Consume `GET /api/v1/trust/agents/{agentId}/trust-profile` — assumed endpoint returning all 7 dimensions scored 0–100.

**Rationale**: The backend trust API exposes `GET /api/v1/trust/agents/{agent_id}/tier` which returns a 3-component score (certification_component, guardrail_component, behavioral_component). The spec assumption explicitly states: "The radar chart data format aligns with the trust service's trust profile endpoint — each dimension provides a score (0–100) and component breakdowns." The 7 trust dimensions defined in the spec (Identity & Authentication, Authorization & Access Control, Behavioral Compliance, Explainability, Evaluation Quality, Privacy & Data Protection, Certification & Audit Trail) map to the platform's trust framework, not the current 3-component tier. A dedicated `/trust-profile` endpoint is assumed to exist or be added to the `trust-certifier` runtime profile.

**Fallback if endpoint unavailable during dev**: Map the 3 tier components + trust signals to the 7 dimensions client-side, using the signals endpoint `GET /api/v1/trust/agents/{agent_id}/signals` as supplemental data.

**Alternatives considered**:
- Consuming the tier endpoint and mapping 3→7 — data loss; tier components are aggregates, not dimension-level scores
- ClickHouse analytics query — trust radar is pre-computed by the trust certifier, not an ad-hoc analytics query

---

## Decision 4: Privacy Impact Analysis Data Source

**Decision**: Consume `GET /api/v1/trust/agents/{agentId}/privacy-impact` — assumed read endpoint returning cached analysis results.

**Rationale**: The backend has `POST /api/v1/trust/privacy/assess` but it is service-account-only and triggers an assessment from a `context_assembly_id`. For the workbench, the officer views pre-computed results. The spec assumption states "Trust profiles and privacy impact analyses are computed on the backend; this feature only displays pre-computed results." A read endpoint returning the most recent cached assessment is the natural complement to the POST trigger, consistent with the backend pattern of persisting assessments in PostgreSQL.

**Re-analysis CTA**: The "Request Re-analysis" button from the edge case (stale data >24h) will call `POST /api/v1/trust/privacy/assess` if the frontend has the required `context_assembly_id`, or show a message directing the user to contact the agent owner.

**Alternatives considered**:
- Deriving from existing trust signals — signals are fine-grained per-execution signals, not a structured privacy category analysis

---

## Decision 5: Approve / Reject Review Form API Mapping

**Decision**: Map the reviewer form to the existing activate/revoke endpoints.

- **Approve** → `POST /api/v1/trust/certifications/{id}/activate` (no body required; notes stored as a synthetic evidence ref)
- **Reject** → `POST /api/v1/trust/certifications/{id}/revoke` with `{ "reason": "<reviewer notes>" }`

**Rationale**: The backend currently has separate `activate` and `revoke` endpoints rather than a unified review decision endpoint. The `revoke` endpoint takes a reason string that directly captures the reviewer's rejection notes. For approval, the spec requires mandatory notes to be recorded; these will be submitted as a `POST /api/v1/trust/certifications/{id}/evidence` call with `evidence_type: "manual_review"` and the notes as the `summary` field, submitted immediately after the activate call (two-step in the mutation).

**Alternatives considered**:
- A new unified `/review` endpoint — not currently in the backend; mapping to existing endpoints avoids backend changes
- Storing approval notes in the activate body — activate currently takes no body; adding review notes as an evidence ref is cleaner and preserves the audit trail

---

## Decision 6: Policy Attachment Drag-and-Drop Implementation

**Decision**: HTML5 native drag events (`draggable`, `onDragStart`, `onDragOver`, `onDrop`). No new npm packages.

**Rationale**: Policy attachment drag-and-drop is a targeted single-surface interaction (policy catalog cards → binding list drop zone). HTML5 native drag events are sufficient. The constitution requires no new npm packages without explicit justification. There is no case for adding `@dnd-kit` or `react-beautiful-dnd` (~50KB) for a single drag target.

**Implementation**: 
- Policy catalog cards: `draggable={true}` + `onDragStart` stores `policyId` in `dataTransfer`
- Binding list drop zone: `onDragOver` + `onDrop` read `policyId` and call attach mutation
- Incompatibility feedback: `onDragOver` sets a `dropError` state in Zustand when incompatible (checked against target type constraints)

**Alternatives considered**:
- `@dnd-kit/core` — no new packages justified; HTML5 drag API covers this use case
- Mouse move event emulation — unnecessary complexity

---

## Decision 7: Policy Inheritance Chain Display

**Decision**: Consume `GET /api/v1/policies/effective/{agentId}?workspace_id=...` for the binding list. Augment with direct attachment list from `GET /api/v1/policies/{policyId}/attachments`.

**Rationale**: The `effective/{agentId}` endpoint returns `source_policies` (list of UUID) and `resolved_rules` with `PolicyRuleProvenance` including `scope_type` (global / workspace / agent / fleet). This directly maps to the "direct / inherited from workspace / inherited from fleet" source labels required by US4. The `target_id` field on the `PolicyAttachResponse` identifies the specific source entity (workspace ID or fleet ID), which can be resolved to a display name via the workspaces/fleets API.

**Source label mapping**:
- `scope_type: agent` + `target_type: agent_revision` → "direct"
- `scope_type: workspace` → "workspace: {workspaceName}"
- `scope_type: fleet` + `target_type: fleet` → "fleet: {fleetName}"
- `scope_type: global` → "platform default"

**Remove action**: Direct bindings show a "Remove" button that calls `DELETE /api/v1/policies/{policyId}/attach/{attachmentId}`. Inherited bindings show only a "Manage" link pointing to the source entity's settings.

**Alternatives considered**:
- Reconstructing inheritance from per-policy attachment lists — requires N+1 requests per policy; the `effective` endpoint gives a pre-resolved result in one request

---

## Decision 8: No New npm Packages

**Decision**: No new npm packages for this feature.

**Rationale**: All required capabilities are already in the frontend stack:
- **DataTable** with search/filter/sort/pagination → shadcn/ui DataTable + TanStack Table v8 (used in features 027, 035, 041, 042)
- **Radar chart** with 7 axes, tooltips, warning highlights → `Recharts RadarChart` (Recharts 2.x already installed)
- **Drag-and-drop** → HTML5 native (Decision 6)
- **Expandable evidence items** → shadcn/ui `Collapsible`
- **File upload input** → HTML5 `<input type="file">` via React Hook Form
- **Status badges, timelines, tooltips** → shadcn/ui Badge, custom Timeline (feature 015 shared component), shadcn Tooltip

**Recharts RadarChart note**: The `RadarChart`, `Radar`, `PolarGrid`, `PolarAngleAxis`, `PolarRadiusAxis`, `ResponsiveContainer`, and `Tooltip` components are all in Recharts 2.x — no separate installation needed.

**Alternatives considered**:
- `react-dnd` / `@dnd-kit` — rejected per Decision 6
- `chart.js` radar — rejected; Recharts already in stack
- `visx` spider chart — rejected; Recharts sufficient
