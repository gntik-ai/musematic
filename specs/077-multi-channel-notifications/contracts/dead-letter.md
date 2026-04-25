# Dead-Letter Contract

**Feature**: 077-multi-channel-notifications
**Modules**:
- `apps/control-plane/src/platform/notifications/routers/deadletter_router.py`
- `apps/control-plane/src/platform/notifications/workers/deadletter_threshold_worker.py`

## REST endpoints

Under `/api/v1/notifications/dead-letter/*`:

| Method + path | Purpose | Role |
|---|---|---|
| `GET /api/v1/notifications/dead-letter?workspace_id=&webhook_id=&since=&until=&reason=&limit=` | List dead-letter entries scoped to the operator's authorisation. | `workspace_admin` (own workspace only), `auditor`, `superadmin` |
| `GET /api/v1/notifications/dead-letter/{delivery_id}` | Inspect a single entry: full payload, attempts log, response statuses, residency/DLP context. | same |
| `POST /api/v1/notifications/dead-letter/{delivery_id}/replay` | Replay a single entry. Creates a new `webhook_deliveries` row linking back via `replayed_from`; reuses the original `idempotency_key`. | `workspace_admin`, `superadmin` |
| `POST /api/v1/notifications/dead-letter/replay-batch` | Replay a filter set (by webhook, by reason, by time range). Returns a job id; replay proceeds asynchronously and emits per-row outcomes via `monitor.alerts`. | `workspace_admin`, `superadmin` |
| `POST /api/v1/notifications/dead-letter/{delivery_id}/resolve` | Mark as resolved without replay; stores a resolution reason. | `workspace_admin`, `superadmin` |

Cross-workspace access (workspace_admin trying to read another workspace's DLQ) returns 403 (rule 47 — workspace-vs-platform scope distinction).

## Replay semantics

`POST /api/v1/notifications/dead-letter/{delivery_id}/replay`:

```python
async def replay_dead_letter(
    delivery_id: UUID, *, actor: User
) -> WebhookDelivery:
    original = await repo.get_delivery(delivery_id)
    if original.status != "dead_letter":
        raise InvalidStateError("only dead_letter rows can be replayed")
    new_row = WebhookDelivery(
        webhook_id=original.webhook_id,
        idempotency_key=original.idempotency_key,           # REUSED
        event_id=original.event_id,
        event_type=original.event_type,
        payload=original.payload,
        status="pending",
        attempts=0,
        next_attempt_at=now_utc(),
        replayed_from=original.id,
        replayed_by=actor.id,
    )
    await repo.insert_delivery(new_row)
    await audit_chain.append(...)                           # operator action
    return new_row
```

The replay row is dispatched by the next retry-worker tick. The original dead-letter row is preserved unchanged (audit trail).

## Threshold worker

`deadletter_threshold_worker.py` runs every 60s:

```python
async def check_thresholds() -> None:
    rows = await repo.aggregate_dead_letter_depth_by_workspace()
    for workspace_id, depth in rows:
        if depth >= settings.notifications.dead_letter_warning_threshold:
            if not await redis.has_recent_alert(workspace_id, ttl=3600):
                await producer.publish(
                    topic="monitor.alerts",
                    event_type="notifications.dlq.depth.threshold_reached",
                    payload={"workspace_id": str(workspace_id), "depth": depth},
                )
                await redis.mark_recent_alert(workspace_id, ttl=3600)
```

The 1-hour cooldown prevents alert flooding while the underlying issue persists. The operator alert lands on the standard `monitor.alerts` topic, which the existing notifications path consumes.

## Retention worker

A new branch in the existing `notifications.run_retention_gc` task:

```python
async def run_dead_letter_retention_gc() -> int:
    cutoff = datetime.now(UTC) - timedelta(days=settings.notifications.dead_letter_retention_days)
    return await repo.delete_dead_letter_older_than(cutoff)
```

Runs daily. Deletes only `webhook_deliveries` rows with `status = 'dead_letter'` AND `dead_lettered_at < cutoff`. Successful and pending rows are not affected.

## Authorization

- `workspace_admin` → only sees rows where `webhook_id` belongs to a workspace they admin.
- `auditor` and `superadmin` → see all.
- Listing + replay always cross-checks workspace ownership at the row level (defense-in-depth: don't rely on filter-only).

## Unit-test contract

- **DL1** — list filtered by `workspace_id` returns only rows for webhooks in that workspace.
- **DL2** — list cross-workspace by a `workspace_admin` returns 403.
- **DL3** — replay creates a new row with same `idempotency_key`, `replayed_from` set, original row unchanged.
- **DL4** — replay of a non-dead-letter row returns 409 conflict.
- **DL5** — batch replay accepts a filter and returns a job id; rows are dispatched on the next retry tick.
- **DL6** — resolve sets resolution reason and emits an audit chain entry; row is excluded from list views by default.
- **DL7** — threshold worker emits `notifications.dlq.depth.threshold_reached` exactly once per cooldown window per workspace.
- **DL8** — retention GC deletes only `dead_letter` rows older than the configured window; pending and delivered rows untouched.
- **DL9** — Audit chain entry on replay includes both the actor and the original `dead_lettered_at` reference (rule 32 + critical reminder #30 for durability).
