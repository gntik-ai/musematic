# REST API Contracts: Attention Pattern and Configurable User Alerts (Feature 060)

**Router prefix**: `/api/v1/me` (user-scoped, requires authenticated user)  
**Auth**: JWT bearer token (existing `get_current_user` dependency)  
**Error types**: `NotFoundError` (404), `AuthorizationError` (403), `ValidationError` (422)

---

## 1. GET /api/v1/me/alert-settings

Retrieve the authenticated user's alert preference record. Returns defaults if no record exists yet.

**Response 200**:
```json
{
  "id": "uuid",
  "user_id": "uuid",
  "state_transitions": ["working_to_pending", "any_to_complete", "any_to_failed"],
  "delivery_method": "in_app",
  "webhook_url": null,
  "created_at": "2026-04-18T10:00:00Z",
  "updated_at": "2026-04-18T10:00:00Z"
}
```

**Notes**: If no record exists, returns the default preferences (not persisted until PUT is called). `webhook_url` is `null` unless `delivery_method` is `webhook`.

---

## 2. PUT /api/v1/me/alert-settings

Create or replace the authenticated user's alert preferences.

**Request body**:
```json
{
  "state_transitions": ["any_to_failed", "any_to_complete"],
  "delivery_method": "webhook",
  "webhook_url": "https://example.com/hooks/alerts"
}
```

**Validation rules**:
- `state_transitions`: non-empty list of strings; unknown patterns are accepted (ignored at evaluation)
- `delivery_method`: one of `in_app`, `email`, `webhook`
- `webhook_url`: required (non-null, valid URL) when `delivery_method` is `webhook`; rejected with 422 if missing

**Response 200**: Same schema as GET.

**Response 422**: `{"detail": "webhook_url is required when delivery_method is webhook"}`

---

## 3. GET /api/v1/me/alerts

List the authenticated user's alerts, ordered by `created_at` descending.

**Query parameters**:
| Param | Type | Default | Description |
|---|---|---|---|
| `read` | `all` \| `read` \| `unread` | `all` | Filter by read state |
| `limit` | integer 1–100 | `20` | Page size |
| `cursor` | string (opaque) | — | Pagination cursor (from previous `next_cursor`) |

**Response 200**:
```json
{
  "items": [
    {
      "id": "uuid",
      "alert_type": "attention_request",
      "title": "Agent requests human input",
      "body": "Context summary from the agent",
      "urgency": "high",
      "read": false,
      "interaction_id": "uuid",
      "source_reference": {"type": "attention_request", "id": "uuid"},
      "created_at": "2026-04-18T10:00:00Z"
    }
  ],
  "next_cursor": "opaque-cursor-string",
  "total_unread": 3
}
```

**Notes**: `urgency` is one of `low`, `medium`, `high`, `critical`. `interaction_id` may be `null`. `source_reference` may be `null`.

---

## 4. GET /api/v1/me/alerts/unread-count

Lightweight endpoint returning only the authenticated user's unread alert count.

**Response 200**:
```json
{
  "count": 7
}
```

**Notes**: Designed for polling by UI header badge. No pagination.

---

## 5. PATCH /api/v1/me/alerts/{alert_id}/read

Mark a single alert as read. Idempotent — calling again on an already-read alert returns 200 without error.

**Response 200**:
```json
{
  "id": "uuid",
  "read": true,
  "updated_at": "2026-04-18T10:05:00Z"
}
```

**Response 403**: If `alert_id` belongs to a different user.

**Response 404**: If `alert_id` does not exist.

**Side effect**: Triggers a `notifications.read_propagated` event on the `notifications.alerts` Kafka topic (or an in-process WebSocket push) so all of the user's active sessions update their unread count.

---

## 6. GET /api/v1/me/alerts/{alert_id}

Retrieve a single alert with delivery outcome detail.

**Response 200**:
```json
{
  "id": "uuid",
  "alert_type": "state_change",
  "title": "Interaction transitioned to failed",
  "body": null,
  "urgency": "medium",
  "read": false,
  "interaction_id": "uuid",
  "source_reference": {"type": "state_change", "event_id": "uuid"},
  "delivery_outcome": {
    "delivery_method": "webhook",
    "attempt_count": 3,
    "outcome": "failed",
    "error_detail": "connection timeout",
    "next_retry_at": null,
    "delivered_at": null
  },
  "created_at": "2026-04-18T10:00:00Z"
}
```

**Response 403**: If alert belongs to a different user.

**Response 404**: If alert does not exist.

---

## WebSocket Channel

Alerts are pushed to connected clients on the existing `alerts` channel (channel type string: `"alerts"`, resource_id = `user_id`). The ws_hub auto-subscribes users to this channel on connect (same pattern as the `attention` channel).

**Pushed message shape**:
```json
{
  "channel": "alerts",
  "event_type": "notifications.alert_created",
  "payload": {
    "id": "uuid",
    "alert_type": "attention_request",
    "title": "...",
    "urgency": "high",
    "read": false,
    "created_at": "..."
  }
}
```

**Read-propagation push** (on PATCH /read):
```json
{
  "channel": "alerts",
  "event_type": "notifications.alert_read",
  "payload": {
    "alert_id": "uuid",
    "unread_count": 6
  }
}
```
