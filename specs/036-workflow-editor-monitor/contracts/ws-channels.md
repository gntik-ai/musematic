# WebSocket Channels: Workflow Editor and Execution Monitor

Uses the existing `WebSocketClient` from `lib/ws.ts`.  
Channel subscription: `wsClient.subscribe<T>(channel, handler): WsUnsubscribeFn`

---

## Channels

### Execution Channel
**Channel format**: `execution:{executionId}`  
**Subscribe when**: The execution monitor mounts for a live execution.  
**Unsubscribe when**: The monitor unmounts or execution reaches terminal state.

#### Event Types

| event_type | payload shape | UI action |
|-----------|---------------|-----------|
| `step.state_changed` | `{ step_id, new_status: StepStatus, occurred_at }` | Update step node color in store |
| `execution.status_changed` | `{ new_status: ExecutionStatus, occurred_at }` | Update execution header status |
| `event.appended` | `{ event: ExecutionEvent }` | Prepend to timeline |
| `budget.threshold` | `{ step_id, dimension, current_value, max_value, threshold_pct }` | Update cost tracker |
| `correction.iteration` | `{ step_id, loop_id, iteration_number, quality_score, delta, status }` | Update self-correction chart if step is selected |
| `approval.requested` | `{ step_id, approver_role, requested_at }` | Show approval badge on step node |
| `hot_change.applied` | `{ variable_name, new_value, applied_at }` | Append to timeline |

#### Connection Status Events (from wsClient)
The `wsClient` exposes a `connectionStatus` observable. Map to store:
- `connected` → `wsConnectionStatus: 'connected'`
- `reconnecting` → `wsConnectionStatus: 'reconnecting'`
- `disconnected` → `wsConnectionStatus: 'disconnected'`

On reconnect: re-fetch `GET /executions/{id}/state` and `GET /executions/{id}/journal?since_sequence={lastSeen}` to reconcile missed events.

---

## MSW Mock Handlers (for tests)

The following MSW WebSocket handlers are used in Vitest / Playwright tests:

```typescript
// Simulate step state change
mockWsEvent(`execution:${executionId}`, {
  event_type: 'step.state_changed',
  payload: { step_id: 'step-1', new_status: 'completed', occurred_at: new Date().toISOString() }
});

// Simulate self-correction iteration
mockWsEvent(`execution:${executionId}`, {
  event_type: 'correction.iteration',
  payload: { step_id: 'step-2', loop_id: 'loop-1', iteration_number: 3, quality_score: 0.87, delta: 0.12, status: 'continue' }
});
```
