# API Contracts: Connector Plugin Framework

**Branch**: `025-connector-plugin-framework` | **Date**: 2026-04-11 | **Phase**: 1

## Overview

All endpoints are under `/api/v1/workspaces/{workspace_id}/connectors/` prefix. All require JWT authentication and workspace membership. Workspace isolation is enforced — cross-workspace access returns 404.

---

## Connector Types

### GET /api/v1/connectors/types
List all available connector types (global, not workspace-scoped).

**Response 200**:
```json
{
  "items": [
    {
      "id": "uuid",
      "slug": "slack",
      "display_name": "Slack",
      "description": "Connect Slack workspaces via Events API",
      "config_schema": { "$schema": "...", "type": "object", "properties": {...} },
      "is_deprecated": false,
      "created_at": "2026-04-11T00:00:00Z"
    }
  ]
}
```

### GET /api/v1/connectors/types/{slug}
Get a specific connector type by slug.

**Response 200**: Single `ConnectorTypeResponse`
**Response 404**: Type not found

---

## Connector Instances

### POST /api/v1/workspaces/{workspace_id}/connectors
Create a connector instance.

**Request**:
```json
{
  "connector_type_slug": "slack",
  "name": "Support Slack",
  "config": {
    "team_id": "T12345",
    "default_channel": "C98765",
    "bot_token": {"$ref": "bot_token"},
    "signing_secret": {"$ref": "signing_secret"}
  },
  "credential_refs": {
    "bot_token": "workspaces/ws-uuid/connectors/c-uuid/bot_token",
    "signing_secret": "workspaces/ws-uuid/connectors/c-uuid/signing_secret"
  }
}
```

**Response 201**: `ConnectorInstanceResponse`
**Response 400**: Config validation failed (missing required field)
**Response 409**: Name already exists in workspace
**Response 422**: Type is deprecated (cannot create new instances)

### GET /api/v1/workspaces/{workspace_id}/connectors
List connector instances in the workspace.

**Query params**: `type_slug` (filter by type), `status` (enabled/disabled), `cursor`, `limit`

**Response 200**:
```json
{
  "items": [ /* ConnectorInstanceResponse[] */ ],
  "next_cursor": "...",
  "total": 12
}
```

### GET /api/v1/workspaces/{workspace_id}/connectors/{connector_id}
Get a connector instance.

**Response 200**: `ConnectorInstanceResponse`
**Response 404**: Not found or not in workspace

### PUT /api/v1/workspaces/{workspace_id}/connectors/{connector_id}
Update a connector instance.

**Request**: `ConnectorInstanceUpdate` (all fields optional)
**Response 200**: Updated `ConnectorInstanceResponse`
**Response 400**: Config validation failed

### DELETE /api/v1/workspaces/{workspace_id}/connectors/{connector_id}
Delete (soft-delete) a connector instance. Deletes associated routes and pending deliveries.

**Response 204**: Deleted
**Response 404**: Not found

### POST /api/v1/workspaces/{workspace_id}/connectors/{connector_id}/health-check
Run a health check on the connector.

**Response 200**:
```json
{
  "connector_instance_id": "uuid",
  "status": "healthy",
  "latency_ms": 142.5,
  "error": null,
  "checked_at": "2026-04-11T10:00:00Z"
}
```

---

## Connector Routes

### POST /api/v1/workspaces/{workspace_id}/connectors/{connector_id}/routes
Create a routing rule.

**Request**:
```json
{
  "name": "Support channel → triage agent",
  "connector_instance_id": "uuid",
  "channel_pattern": "#support*",
  "sender_pattern": null,
  "conditions": {},
  "target_agent_fqn": "support-ops:triage-agent",
  "target_workflow_id": null,
  "priority": 10,
  "is_enabled": true
}
```

**Response 201**: `ConnectorRouteResponse`
**Response 400**: Missing target (neither agent_fqn nor workflow_id)
**Response 404**: Connector instance not found in workspace

### GET /api/v1/workspaces/{workspace_id}/connectors/{connector_id}/routes
List routing rules for a connector instance.

**Response 200**:
```json
{
  "items": [ /* ConnectorRouteResponse[] */ ],
  "total": 3
}
```

### GET /api/v1/workspaces/{workspace_id}/routes/{route_id}
Get a specific routing rule.

**Response 200**: `ConnectorRouteResponse`
**Response 404**: Not found

### PUT /api/v1/workspaces/{workspace_id}/routes/{route_id}
Update a routing rule.

**Request**: `ConnectorRouteUpdate` (all fields optional)
**Response 200**: Updated `ConnectorRouteResponse`

**Side effect**: Invalidates Redis route cache for this connector instance.

### DELETE /api/v1/workspaces/{workspace_id}/routes/{route_id}
Delete a routing rule.

**Response 204**: Deleted
**Side effect**: Invalidates Redis route cache for this connector instance.

---

## Inbound Webhooks (Public Endpoints — No JWT Auth)

These endpoints receive inbound messages from external systems. Authentication is via webhook signature verification.

### POST /api/v1/inbound/slack/{connector_instance_id}
Receive a Slack Events API payload.

**Headers required**: `X-Slack-Signature`, `X-Slack-Request-Timestamp`
**Response 200**: `{"ok": true}` (Slack requires 200 within 3s)
**Response 401**: Signature verification failed
**Response 400**: Connector disabled or not found

**Processing**: Normalizes → matches route → publishes to `connector.ingress`

### POST /api/v1/inbound/telegram/{connector_instance_id}
Receive a Telegram Bot API webhook update.

**Headers required**: None (Telegram does not sign webhooks; secret token in URL)
**Response 200**: `{}`
**Response 401**: Token mismatch

### POST /api/v1/inbound/webhook/{connector_instance_id}
Receive a generic webhook POST.

**Headers required**: `X-Hub-Signature-256` (or `X-Signature`)
**Response 200**: `{"received": true}`
**Response 401**: Signature verification failed

### (Email — No HTTP endpoint)
Email inbound is polled by APScheduler in the worker profile.

---

## Outbound Deliveries

### POST /api/v1/workspaces/{workspace_id}/deliveries
Create and enqueue an outbound delivery.

**Request**:
```json
{
  "connector_instance_id": "uuid",
  "destination": "C98765",
  "content_text": "Your request has been processed.",
  "content_structured": { "blocks": [...] },
  "priority": 50,
  "source_interaction_id": "uuid",
  "source_execution_id": "uuid"
}
```

**Response 201**: `OutboundDeliveryResponse` with `status: "pending"`
**Response 400**: Connector instance disabled
**Response 404**: Connector instance not found in workspace

**Side effect**: Publishes `ConnectorDeliveryRequestPayload` to `connector.delivery` topic.

### GET /api/v1/workspaces/{workspace_id}/deliveries
List outbound deliveries.

**Query params**: `connector_id`, `status`, `cursor`, `limit`

**Response 200**:
```json
{
  "items": [ /* OutboundDeliveryResponse[] */ ],
  "next_cursor": "...",
  "total": 48
}
```

### GET /api/v1/workspaces/{workspace_id}/deliveries/{delivery_id}
Get a specific delivery record.

**Response 200**: `OutboundDeliveryResponse`
**Response 404**: Not found

---

## Dead Letter Queue

### GET /api/v1/workspaces/{workspace_id}/dead-letter
List dead-letter entries.

**Query params**: `connector_id`, `resolution_status` (pending/redelivered/discarded), `cursor`, `limit`

**Response 200**:
```json
{
  "items": [ /* DeadLetterEntryResponse[] */ ],
  "next_cursor": "...",
  "total": 5
}
```

### GET /api/v1/workspaces/{workspace_id}/dead-letter/{entry_id}
Get a specific dead-letter entry.

**Response 200**: `DeadLetterEntryResponse`
**Response 404**: Not found

### POST /api/v1/workspaces/{workspace_id}/dead-letter/{entry_id}/redeliver
Manually redeliver a dead-letter message.

**Request**:
```json
{ "note": "Retrying after fixing the channel configuration" }
```

**Response 200**: New `OutboundDeliveryResponse`
**Response 409**: Entry already redelivered or discarded

**Side effect**: Creates new `OutboundDelivery`, marks DLQ entry `resolution_status=redelivered`, publishes to `connector.delivery`.

### POST /api/v1/workspaces/{workspace_id}/dead-letter/{entry_id}/discard
Discard a dead-letter message.

**Request**:
```json
{ "note": "Obsolete — channel was deleted" }
```

**Response 204**: Discarded
**Response 409**: Entry already redelivered or discarded

**Side effect**: Archives original delivery payload to MinIO `connector-dead-letters/{workspace_id}/{entry_id}.json`, marks entry `resolution_status=discarded`.

---

## Internal Interfaces (In-Process)

### ConnectorsService.get_connector_for_inbound(connector_instance_id, workspace_id) → ConnectorInstance
Used by: interactions BC to look up the source connector when creating interactions from ingress events.

### ConnectorsService.resolve_inbound_route(connector_instance_id, workspace_id, channel, sender) → ConnectorRoute | None
Used by: inbound processing to find routing target before publishing to `connector.ingress`.

---

## Error Responses

All errors follow the standard `PlatformError` envelope:
```json
{
  "error": "connector_config_invalid",
  "message": "Missing required fields: bot_token, signing_secret",
  "details": {
    "missing_fields": ["bot_token", "signing_secret"],
    "connector_type": "slack"
  }
}
```

**Error codes**:
- `connector_not_found` — 404
- `connector_type_not_found` — 404
- `connector_type_deprecated` — 422
- `connector_config_invalid` — 400
- `connector_disabled` — 400
- `connector_name_conflict` — 409
- `route_not_found` — 404
- `route_missing_target` — 400
- `webhook_signature_invalid` — 401
- `delivery_not_found` — 404
- `dead_letter_not_found` — 404
- `dead_letter_already_resolved` — 409
- `credential_unavailable` — 503
