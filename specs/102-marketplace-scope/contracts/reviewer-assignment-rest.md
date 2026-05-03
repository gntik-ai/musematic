# Contract — Reviewer Assignment REST

**Phase 1 output.** Defines the two new admin REST endpoints introduced by the refresh-pass for assigning and un-assigning marketplace review submissions to a specific platform-staff reviewer.

Both endpoints live under `/api/v1/admin/marketplace-review/*` (rule 29: admin endpoint segregation; rule 30: admin role gates — both depend on `require_superadmin`). Both extend the existing admin router at `apps/control-plane/src/platform/marketplace/admin_router.py`.

---

## `POST /api/v1/admin/marketplace-review/{agent_id}/assign`

Assign a pending-review submission to a specific reviewer.

### Authorization

`require_superadmin` (FastAPI dependency, existing).

### Path parameters

| Name | Type | Notes |
|---|---|---|
| `agent_id` | UUID | The `registry_agent_profiles.id` of the submission. Must currently be in `review_status = 'pending_review'`. |

### Request body

```json
{
  "reviewer_user_id": "f0e4c2b1-..."
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `reviewer_user_id` | UUID | yes | Must be a platform-staff user. Must NOT equal `created_by(agent_id)` (self-review prevention). |

### Response 200

```json
{
  "agent_id": "...",
  "assigned_reviewer_user_id": "f0e4c2b1-...",
  "assigned_reviewer_email": "alice@platform.example",
  "assigner_user_id": "...",
  "assigned_at": "2026-05-03T12:34:56Z",
  "prior_assignee_user_id": null
}
```

### Errors

| Status | Code | When |
|---|---|---|
| 403 | `self_review_not_allowed` | `reviewer_user_id == created_by(agent_id)`. Body: `{ "submitter_user_id": "...", "reviewer_user_id": "..." }`. |
| 403 | `not_authorized` | Caller is not a superadmin. |
| 404 | `agent_not_found` | `agent_id` does not exist OR is invisible to caller's tenant context. (Per FR-741.10, NOT a distinct code from generic not-found.) |
| 409 | `assignment_conflict` | Submission already assigned to a different reviewer. Body: `{ "assigned_reviewer_user_id": "..." }`. Caller must `unassign` first. |
| 409 | `not_in_pending_review` | Submission is not in `pending_review` status. Body: `{ "current_status": "..." }`. |
| 422 | `invalid_reviewer` | `reviewer_user_id` is not a platform-staff user. |

### Audit + Kafka

- Audit-chain entry kind: `marketplace.review.assigned`. Fields: `assigner_user_id`, `assignee_user_id`, `agent_id`, `submitter_user_id`, `prior_assignee_user_id`.
- Kafka event: `marketplace.review.assigned` on topic `marketplace.events`. Same fields.

### Idempotency

Calling `assign` with the same `reviewer_user_id` for an already-assigned-to-that-reviewer submission is a no-op (200, no audit/Kafka). Calling with a different `reviewer_user_id` raises 409.

---

## `DELETE /api/v1/admin/marketplace-review/{agent_id}/assign`

Un-assign a pending-review submission. Idempotent.

### Authorization

`require_superadmin`.

### Path parameters

| Name | Type | Notes |
|---|---|---|
| `agent_id` | UUID | The `registry_agent_profiles.id` of the submission. |

### Request body

None.

### Response 200

```json
{
  "agent_id": "...",
  "prior_assignee_user_id": "f0e4c2b1-...",
  "unassigned_at": "2026-05-03T12:35:10Z",
  "unassigner_user_id": "..."
}
```

If the submission was already unassigned, response is the same shape with `prior_assignee_user_id: null` and no audit/Kafka emitted.

### Errors

| Status | Code | When |
|---|---|---|
| 403 | `not_authorized` | Caller is not a superadmin. |
| 404 | `agent_not_found` | `agent_id` does not exist OR invisible. |
| 409 | `not_in_pending_review` | Submission is not in `pending_review` status. |

### Audit + Kafka

- Audit-chain entry kind: `marketplace.review.unassigned`. Fields: `unassigner_user_id`, `prior_assignee_user_id`, `agent_id`.
- Kafka event: `marketplace.review.unassigned` on topic `marketplace.events`. Same fields.

### Idempotency

Calling `unassign` on an already-unassigned submission is a no-op (200, no audit/Kafka).

---

## Updated `GET /api/v1/admin/marketplace-review` (additive — same endpoint, new query params and response fields)

The existing 099 endpoint at `apps/control-plane/src/platform/marketplace/admin_router.py` (`list_review_queue`) gets two additive query params and two new response fields.

### New query parameters

| Param | Type | Default | Notes |
|---|---|---|---|
| `assigned_to` | UUID | none | Filter by `assigned_reviewer_user_id`. Special value `me` resolves to caller's user_id. Special value `unassigned` filters `assigned_reviewer_user_id IS NULL`. |
| `include_self_authored` | bool | `false` | Include submissions where `created_by == current_user.id`. UI default is `false` so reviewers don't accidentally action their own work; can be flipped to inspect own submissions. |

### New response fields per item

| Field | Type | Notes |
|---|---|---|
| `assigned_reviewer_user_id` | UUID \| null | From the new column. |
| `assigned_reviewer_email` | string \| null | LEFT JOIN `users.email`. |
| `is_self_authored` | bool | computed: `created_by == current_user.id`. |
