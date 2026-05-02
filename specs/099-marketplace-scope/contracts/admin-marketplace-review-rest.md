# Contract — Admin Marketplace-Review REST API

**Prefix**: `/api/v1/admin/marketplace-review/*`
**Owner**: `apps/control-plane/src/platform/marketplace/admin_router.py`
**Authorization**: Super admin or platform-staff role. Cross-tenant reads use the platform-staff session per UPD-046.
**OpenAPI tag**: `admin.marketplace_review`.

## `GET /api/v1/admin/marketplace-review/queue`

List pending submissions cross-tenant.

```jsonc
{
  "items": [
    {
      "agent_id": "uuid",
      "agent_fqn": "namespace:agent",
      "tenant_slug": "default",
      "submitter_user_id": "uuid",
      "submitter_email": "alice@example.test",
      "category": "data-extraction",
      "marketing_description": "...",
      "tags": ["pdf", "extraction"],
      "submitted_at": "2026-05-02T10:30:00Z",
      "claimed_by_user_id": null,                  // or reviewer's user_id when claimed
      "age_minutes": 42
    }
  ],
  "next_cursor": "opaque-token-or-null"
}
```

Query: `claimed_by` (filter on a reviewer), `unclaimed=true`, `cursor`, `limit`. Default sort: oldest first (FIFO).

## `POST /api/v1/admin/marketplace-review/{agent_id}/claim`

Reviewer claims the submission. Idempotent on `(agent_id, reviewer_id)` — re-claiming by the same reviewer is a no-op success. Refused if a different reviewer already claimed (`409 review_already_claimed`).

## `POST /api/v1/admin/marketplace-review/{agent_id}/release`

Reviewer releases the claim. Sets `reviewed_by_user_id = NULL`. Idempotent.

## `POST /api/v1/admin/marketplace-review/{agent_id}/approve`

Body: `{ "notes": "..." }` (optional). Transitions `pending_review → published`. Records audit-chain entry. Publishes `marketplace.approved` and `marketplace.published` events. Sets `reviewed_at = now()`, `reviewed_by_user_id = current_user.id`.

## `POST /api/v1/admin/marketplace-review/{agent_id}/reject`

Body: `{ "reason": "..." }` (required). Transitions `pending_review → rejected`. Records audit-chain entry. Publishes `marketplace.rejected` event. Notification delivered to the submitter via UPD-042's `AlertService.create_admin_alert()` with the rejection reason.

## Error model

| HTTP | `code` |
|---|---|
| 401 | `unauthenticated` |
| 403 | `not_super_admin_or_platform_staff` |
| 404 | `submission_not_found` |
| 409 | `review_already_claimed`, `submission_already_resolved` |
| 422 | `rejection_reason_required` |

## Test contract

`tests/integration/marketplace/test_admin_review_queue.py`: queue listing includes only `pending_review`; claim is idempotent for same reviewer, conflicts for different reviewer; approve transitions correctly; reject delivers notification.
