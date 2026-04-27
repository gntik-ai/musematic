# WebSocket API

The WebSocket gateway is served by the `ws-hub` runtime profile at `/ws`. Clients authenticate during the upgrade using `Authorization: Bearer <token>` or a `token` query parameter. Missing or invalid credentials receive a denial response with `websocket_denied`.

## Client Messages

```json
{"type":"subscribe","channel":"execution","resource_id":"<uuid>"}
```

```json
{"type":"unsubscribe","channel":"execution","resource_id":"<uuid>"}
```

```json
{"type":"list_subscriptions"}
```

The gateway accepts JSON only. Malformed messages produce `protocol_violation`; repeated violations close the socket with code `4400`.

## Channels

| Channel | Scope | Kafka Topics | Typical Use |
| --- | --- | --- | --- |
| `execution` | Workspace | `execution.events`, `workflow.runtime`, `runtime.lifecycle` | Execution status, step progress, task lifecycle. |
| `interaction` | Workspace | `interaction.events` | Conversation and message-level activity. |
| `conversation` | Workspace | `interaction.events` | Conversation-focused updates. |
| `workspace` | Workspace | `workspaces.events` | Workspace membership, settings, and goals. |
| `fleet` | Workspace | `runtime.lifecycle` | Fleet membership and runtime health. |
| `reasoning` | Workspace | `runtime.reasoning` | Reasoning traces and branch summaries. |
| `correction` | Workspace | `runtime.selfcorrection` | Self-correction events. |
| `simulation` | Workspace | `simulation.events` | Simulation run updates. |
| `testing` | Workspace | `testing.results` | Evaluation and test result streams. |
| `alerts` | User | `monitor.alerts`, `notifications.alerts` | User-visible alerts; auto-subscription may apply. |
| `attention` | User | `interaction.attention` | Attention requests; auto-subscribed on connect. |

Workspace channels require the user to have visibility into the resource. User-scoped channels filter by the authenticated user ID.

## Server Messages

Server messages are JSON objects with a `type` field. Common types are `welcome`, `subscribed`, `unsubscribed`, `subscriptions`, `event`, `snapshot`, `events_dropped`, `heartbeat`, and `error`.

The gateway sends heartbeat messages based on `WS_HEARTBEAT_INTERVAL_SECONDS` and closes idle connections after `WS_HEARTBEAT_TIMEOUT_SECONDS`. Clients should reconnect with exponential backoff and resubscribe after `welcome`.
