# Contract — Self-Review Prevention

**Phase 1 output.** Defines the cross-cutting contract that no reviewer may take a review action on a submission they themselves authored. Enforced at two layers (service + API) per R9.

---

## Scope

The guard applies to every action whose semantic effect is "this reviewer is making a decision about this submission":

| Action | Endpoint | Service method | Caller-checks |
|---|---|---|---|
| Assign | `POST /api/v1/admin/marketplace-review/{agent_id}/assign` | `MarketplaceReviewService.assign(agent_id, reviewer, assigner)` | Refuse if `reviewer == created_by(agent_id)` |
| Claim | `POST /api/v1/admin/marketplace-review/{agent_id}/claim` (existing 099) | `MarketplaceReviewService.claim(agent_id, reviewer_id)` | Refuse if `reviewer_id == created_by(agent_id)` |
| Approve | `POST /api/v1/admin/marketplace-review/{agent_id}/approve` (existing 099) | `MarketplaceReviewService.approve(agent_id, reviewer_id, ...)` | Refuse if `reviewer_id == created_by(agent_id)` |
| Reject | `POST /api/v1/admin/marketplace-review/{agent_id}/reject` (existing 099) | `MarketplaceReviewService.reject(agent_id, reviewer_id, ...)` | Refuse if `reviewer_id == created_by(agent_id)` |

The guard does NOT apply to `release` (releasing a claim is reverting, not deciding).

---

## Service-layer enforcement

Each method above gains a private helper at the top of its body:

```python
async def _ensure_not_self_review(
    self,
    agent_id: UUID,
    actor_user_id: UUID,
    *,
    action: Literal["assign", "claim", "approve", "reject"],
) -> None:
    """Raise SelfReviewNotAllowedError if actor is the agent's submitter.

    Caller is responsible for passing the actor (assigner for assign,
    reviewer for claim/approve/reject — never confuse them).
    """
    submitter_user_id = await self._repository.get_submitter(agent_id)
    if submitter_user_id is None:
        # Submitter unknown or agent missing — let the downstream NotFound
        # path surface; do not leak that the agent exists.
        return
    if submitter_user_id == actor_user_id:
        await self._audit.write_chain_entry(
            kind="marketplace.review.self_review_attempted",
            actor_user_id=actor_user_id,
            payload={
                "submitter_user_id": str(submitter_user_id),
                "agent_id": str(agent_id),
                "action": action,
            },
        )
        raise SelfReviewNotAllowedError(
            submitter_user_id=submitter_user_id,
            actor_user_id=actor_user_id,
            action=action,
        )
```

The helper is called as the first I/O step in each public method, before any UPDATE or notification.

---

## API-layer enforcement

A FastAPI dependency at `apps/control-plane/src/platform/marketplace/dependencies.py` reads `agent_id` from the path and `actor_user_id` from the auth context, calls `_ensure_not_self_review` synchronously, and lets the route handler proceed only if the check passes. The dependency is added to all four routes above.

This is duplicative of the service-layer check by design (defense in depth — R9). The API-layer check exists primarily so the queue-page UI can avoid round-tripping a service exception when surfacing toasts.

---

## Error contract

`SelfReviewNotAllowedError` extends `PlatformError`:

| Field | Value |
|---|---|
| HTTP status | 403 |
| Code | `self_review_not_allowed` |
| Message | `"Reviewers cannot act on submissions they authored."` |
| Details | `{ "submitter_user_id": "...", "actor_user_id": "...", "action": "approve" }` |

The `action` field surfaces which verb was attempted so the UI can render the right toast ("You cannot **approve** your own submission" vs. "You cannot **assign** your own submission to yourself").

---

## Audit chain

Every refused self-review attempt emits a `marketplace.review.self_review_attempted` audit-chain entry. The entry is **independent** of the action attempted (no Kafka event, no state change) and is hash-chained per the existing audit-chain machinery. This gives security operators a stable signal for misconfigured frontends or malicious replays.

The audit entry does NOT name the user as "submitter" or "reviewer" — both fields are present, which means a single entry survives whether the actor was attempting assign, claim, approve, or reject.

---

## UI behaviour (informative)

`is_self_authored` (added to the queue projection per the assignment-rest contract) drives:

- The Approve and Reject buttons are disabled with a "you authored this submission" tooltip.
- The Claim button is disabled with the same tooltip.
- An Assign action initiated by a lead toward the submitter is refused at the API; the UI hides the submitter from the assign-target dropdown.

The UI is a convenience layer — the service and API layers are authoritative.

---

## Tests

- Unit (`tests/unit/marketplace/test_self_review_guard.py`): table-driven test for `_ensure_not_self_review` with the four action verbs.
- Integration (`tests/integration/marketplace/test_self_review_prevention.py`): asserts the API returns 403 with the right code for each route, asserts the audit entry exists, asserts no Kafka event is emitted, asserts the row state is unchanged.
- Frontend (Playwright): asserts the Approve/Reject/Claim buttons are disabled on a self-authored row in the queue.
