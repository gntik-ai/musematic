# WebSocket Channel Contracts: Frontend Updates

**Feature**: 070-frontend-updates-cross-cutting
**Date**: 2026-04-20
**Base client**: `apps/web/lib/ws.ts` (existing — extend channel-type union only)

---

## Envelope (Existing)

All inbound messages share the envelope defined by feature 019:

```typescript
interface WsEnvelope<ChannelType extends string, Payload> {
  channel: ChannelType;
  topic: string;              // channel-specific topic key (e.g. "user:abc", "workspace:xyz", "global")
  event: string;              // event name (e.g. "alert.created", "verdict.issued", "warm-pool.updated")
  payload: Payload;
  timestamp: string;          // ISO 8601
  correlationId?: string;
}
```

---

## New Channel: `alerts`

**Topic key**: `user:<userId>`
**Authorization**: User can only subscribe to their own `user:<userId>`; server rejects cross-user subscription.
**Events**:

### `alert.created`

Fired when the backend publishes a new alert matching an enabled AlertRule for the user.

```typescript
interface AlertCreatedPayload {
  alert: Alert;                            // see types/alerts.ts
  unreadCountHint: number;                 // server-side count after this alert
}
```

Client behavior:
- Increment `alertStore.unreadCount` (optimistic — does NOT trust `unreadCountHint` to prevent replay double-count)
- Invalidate `["alert-feed", userId]` query
- Reconcile `unreadCount` against `unreadCountHint` on every 5th message (debounced reconciliation)

### `alert.read`

Fired when the backend or another session marks alerts as read (cross-device sync).

```typescript
interface AlertReadPayload {
  alertIds: string[];
  unreadCount: number;                     // server truth after marking
}
```

Client behavior:
- Call `alertStore.setUnreadCount(unreadCount)` (authoritative)
- Invalidate `["alert-feed", userId]` query

---

## New Channel: `governance-verdicts`

**Topic key**: `workspace:<workspaceId>` (scoped) or `global` (platform-admin only)
**Authorization**: `workspace:*` requires `workspace_member` on the workspace; `global` requires `platform_admin`.
**Events**:

### `verdict.issued`

Fired when an Enforcer agent acts on a Judge's verdict.

```typescript
interface VerdictIssuedPayload {
  verdict: GovernanceVerdict;              // see types/governance.ts
}
```

Client behavior:
- Prepend verdict to verdict-feed React state
- Flash new entry with Tailwind `animate-pulse` for 500 ms
- Announce via `aria-live="polite"` region

### `verdict.superseded`

Fired when a later verdict overrides an earlier one.

```typescript
interface VerdictSupersededPayload {
  supersededId: string;
  supersedingId: string;
}
```

Client behavior:
- Mark the superseded entry with a struck-through style; do not remove from feed

---

## New Channel: `warm-pool`

**Topic key**: `global` (platform-admin only)
**Authorization**: `platform_admin`.
**Events**:

### `warm-pool.updated`

Fired on every warm-pool reconciliation tick that changes state.

```typescript
interface WarmPoolUpdatedPayload {
  profile: WarmPoolProfile;                // see types/operator.ts
}
```

Client behavior:
- Update the matching profile card in place (by `profile.name`)
- If `deltaStatus` transitions to `below_target`, briefly flash the card

### `warm-pool.scaling-event`

Fired when a scale-up or scale-down is enqueued.

```typescript
interface WarmPoolScalingEventPayload {
  profileName: "small" | "medium" | "large";
  event: { at: string; from: number; to: number; reason: string };
}
```

Client behavior:
- Prepend to the "recent scaling events" drawer (max 5 entries per profile)

---

## Connection Lifecycle

- **Connect**: on app mount, after auth succeeds. Client subscribes to `alerts:user:<me>` automatically. Other channels subscribe on page mount (governance-verdicts on operator + workspace pages; warm-pool on operator dashboard only).
- **Reconnect**: existing exponential backoff (1 s → 30 s cap). On each successful reconnect, client fetches:
  - `GET /api/v1/alerts/unread-count?userId=<me>` → `alertStore.setUnreadCount(n)` to reconcile (D-005)
  - `GET /api/v1/governance/verdicts?workspace=<ws>&since=<lastSeenAt>` → backfill missed verdicts (max 20)
  - `GET /api/v1/warm-pool/status` → replace warm-pool panel state
- **Disconnect**: `ConnectionStatusBanner` shows; bell shows disconnected indicator; verdict feed + warm-pool fall back to 30 s polling (FR-013).

---

## Event Naming Conventions

All events follow the existing dotted-namespace convention: `<channel>.<verb>`. Never use backend event type names directly — the frontend receives normalized-payload events.

| Backend Kafka topic | Frontend WS event |
|---|---|
| `attention.alert` | `alerts` channel: `alert.created` |
| `governance.verdict_issued` | `governance-verdicts` channel: `verdict.issued` |
| `runtime.warm_pool_reconciled` | `warm-pool` channel: `warm-pool.updated` |

The backend WebSocket hub (feature 019) is responsible for translating Kafka event types into the frontend's normalized channel/event names.
