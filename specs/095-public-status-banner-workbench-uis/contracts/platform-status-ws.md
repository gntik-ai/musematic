# WebSocket Channel Contract: `platform-status`

A new channel on the existing WebSocket gateway (feature 019, `apps/control-plane/src/platform/ws_hub/`). Powers the in-shell `<PlatformStatusBanner>` real-time refresh per spec FR-695-17 / SC-002.

## Channel registration

Add to `apps/control-plane/src/platform/ws_hub/subscription.py`:

```python
class ChannelType(StrEnum):
    EXECUTION = "execution"
    INTERACTION = "interaction"
    CONVERSATION = "conversation"
    WORKSPACE = "workspace"
    FLEET = "fleet"
    REASONING = "reasoning"
    CORRECTION = "correction"
    SIMULATION = "simulation"
    TESTING = "testing"
    ALERTS = "alerts"
    ATTENTION = "attention"
    PLATFORM_STATUS = "platform-status"   # NEW

CHANNEL_TOPIC_MAP[ChannelType.PLATFORM_STATUS] = [
    "multi_region_ops.events",
    "incident_response.events",
    "platform.status.derived",   # internal topic for component-health derivations
]
```

The channel is **user-scoped**, not workspace-scoped — every authenticated session subscribes on connect (auto-subscribe like `ATTENTION` and `ALERTS`).

## Frontend channel union

Add to `apps/web/types/websocket.ts`:

```ts
export type WsChannel =
  | "alerts"
  | "governance-verdicts"
  | "warm-pool"
  | "platform-status"   // NEW
  | string;
```

## Event envelope

Reuses the canonical `EventEnvelope` shape from `apps/control-plane/src/platform/common/events/`. Channel-specific payload types:

### `platform.status.changed`

Emitted on every snapshot regeneration where `overall_state` differs from the previous snapshot, OR a new active incident appears, OR a new active maintenance window starts/ends.

```jsonc
{
  "channel": "platform-status",
  "event_type": "platform.status.changed",
  "occurred_at": "2026-04-28T13:45:02Z",
  "trace_id": "trace-uuid",
  "correlation_id": "corr-uuid",
  "payload": {
    "snapshot_id": "snapshot-uuid",
    "overall_state": "degraded",
    "delta": {
      "previous_overall_state": "operational",
      "added_active_incidents": ["incident-uuid"],
      "removed_active_incidents": [],
      "added_active_maintenance": null,
      "removed_active_maintenance": null,
      "components_changed_state": [
        { "id": "control-plane-api", "from": "operational", "to": "degraded" }
      ]
    }
  }
}
```

### `platform.maintenance.scheduled` / `.started` / `.ended`

Emitted on consumption of `multi_region_ops.events` lifecycle events — re-broadcast on the WS channel for client-side banner state machine. Payload mirrors the upstream Kafka payload.

### `platform.incident.created` / `.updated` / `.resolved`

Emitted on consumption of `incident_response.events`. Payload mirrors the upstream.

## Frontend hook contract

```ts
// apps/web/lib/hooks/use-platform-status.ts
export function usePlatformStatus(): {
  data: MyPlatformStatus | undefined;
  isLoading: boolean;
  isConnected: boolean;
  lastUpdatedAt: Date | undefined;
} {
  // 1. Mounts a TanStack Query hook against /api/v1/me/platform-status
  // 2. Subscribes to wsClient.subscribe('platform-status', onMessage)
  // 3. On WS message, invalidates the TanStack query (refetch)
  // 4. On WS disconnect, falls back to 30s polling
  // 5. Returns isConnected from the WS state
}
```

## Backpressure / dropped events

Reuses the existing `events_dropped` notification pattern (feature 019 — per-client `asyncio.Queue` + bounded buffer). On dropped status events, the banner refreshes via the polling fallback automatically — there is no user-visible degradation.

## Auth and visibility

`platform-status` events are visible to every authenticated user — they describe the platform itself, not workspace data. There is **no workspace-scoped filtering** on this channel (unlike `EXECUTION` or `WORKSPACE` channels). The channel is added to a new `USER_SCOPED_GLOBAL_CHANNELS` set in `subscription.py` (alongside `ALERTS` and `ATTENTION`).
