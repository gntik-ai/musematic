# Contract — Marketplace Kafka Events (Refresh Pass Additions)

**Phase 1 output.** Defines the two new Kafka event types added to the existing `marketplace.events` topic by this refresh. Both extend the 099 event set; none of the 099 events are modified.

---

## Topic

`marketplace.events` — already established by 099. Producer: `MarketplaceReviewService`. Key: `agent_id`. Existing consumers: audit, notifications, analytics, `MarketplaceFanoutConsumer`.

The 099 baseline event types are documented at `specs/099-marketplace-scope/contracts/marketplace-events-kafka.md`.

---

## New event: `marketplace.review.assigned`

Emitted when a platform-staff lead assigns a pending-review submission to a specific reviewer.

### Envelope

Standard `EventEnvelope` per `apps/control-plane/src/platform/common/events/envelope.py`. The `event_type` field is `marketplace.review.assigned`.

### Payload

```json
{
  "agent_id": "...",
  "agent_fqn": "namespace:local-name",
  "submitter_user_id": "...",
  "assigner_user_id": "...",
  "assignee_user_id": "...",
  "prior_assignee_user_id": null,
  "assigned_at": "2026-05-03T12:34:56Z",
  "review_status": "pending_review"
}
```

### Producer

`MarketplaceReviewService.assign(agent_id, reviewer, assigner)` — `apps/control-plane/src/platform/marketplace/review_service.py` (new method added by this refresh).

### Consumers

- `audit` — records audit-chain entry kind `marketplace.review.assigned`.
- `notifications` — sends an inbox notification to `assignee_user_id` with subject "You have been assigned a marketplace review" and a deep link to `/admin/marketplace-review/{agent_id}`.
- `analytics` — records the assignment in the queue-load dashboard time series.

### Idempotency

The producer is idempotent — re-assigning to the same reviewer does not emit a second event. Re-assigning to a different reviewer requires explicit `unassign` first, so the sequence is `unassigned → assigned`, two distinct events.

---

## New event: `marketplace.review.unassigned`

Emitted when a platform-staff lead clears the assignment of a pending-review submission.

### Envelope

Standard `EventEnvelope`. `event_type` is `marketplace.review.unassigned`.

### Payload

```json
{
  "agent_id": "...",
  "agent_fqn": "namespace:local-name",
  "submitter_user_id": "...",
  "unassigner_user_id": "...",
  "prior_assignee_user_id": "...",
  "unassigned_at": "2026-05-03T12:35:10Z",
  "review_status": "pending_review"
}
```

### Producer

`MarketplaceReviewService.unassign(agent_id, assigner)` — same module as above.

### Consumers

- `audit` — records audit-chain entry kind `marketplace.review.unassigned`.
- `notifications` — sends an inbox notification to `prior_assignee_user_id` with subject "You have been removed from a marketplace review" so the former assignee knows their queue changed.
- `analytics` — records the unassignment in the queue-load dashboard.

### Idempotency

Calling `unassign` on an already-unassigned submission does not emit an event.

---

## Existing events — no changes

| Event type | Status |
|---|---|
| `marketplace.scope.changed` | unchanged |
| `marketplace.review.submitted` | unchanged |
| `marketplace.review.claimed` | unchanged |
| `marketplace.review.released` | unchanged |
| `marketplace.review.approved` | unchanged |
| `marketplace.review.rejected` | unchanged |
| `marketplace.published` | unchanged |
| `marketplace.deprecated` | unchanged |
| `marketplace.forked` | unchanged |
| `marketplace.source_updated` | unchanged (now consumed by the registered `MarketplaceFanoutConsumer` after this refresh) |

---

## Audit-chain-only entries (no Kafka event)

The refresh adds one audit-chain-only entry kind for diagnostic purposes:

| Audit kind | When | Why no Kafka event |
|---|---|---|
| `marketplace.review.self_review_attempted` | A reviewer attempted assign/claim/approve/reject on a submission they authored. | Refusal — no state change. Surfacing this on the bus would create needless consumer noise. The audit chain is the right durable record. |

The audit entry's payload is documented in `data-model.md` (state machine § self-review guard).

---

## Backward compatibility

Existing consumers of `marketplace.events` (audit, notifications, analytics, `MarketplaceFanoutConsumer`) ignore unknown `event_type` values per the existing envelope contract — no breaking change. The new event types are opt-in for any new consumer that explicitly subscribes by `event_type`.
