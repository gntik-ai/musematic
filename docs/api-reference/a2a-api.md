# A2A API

Musematic exposes A2A routes under `/api/v1/a2a` for external agent interoperability. The surface exists in the OpenAPI snapshot but remains subject to change as integrations land.

## Current Surface

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/a2a/external-endpoints` | List external endpoints registered for the caller's workspace. |
| `POST /api/v1/a2a/external-endpoints` | Register an external endpoint with auth and routing metadata. |
| `DELETE /api/v1/a2a/external-endpoints/{endpoint_id}` | Remove a registered endpoint. |
| `POST /api/v1/a2a/tasks` | Create an A2A task. |
| `GET /api/v1/a2a/tasks/{task_id}` | Inspect task state. |
| `POST /api/v1/a2a/tasks/{task_id}/messages` | Append a task message. |
| `GET /api/v1/a2a/tasks/{task_id}/stream` | Stream task events. |

## Compatibility

A2A integrations should treat IDs, status values, and message envelopes as the stable contract, but should allow additional fields. Until the integration reaches a fully locked external contract, clients should pin to a Musematic release and validate against `docs/api-reference/openapi.json`.

Related requirements: FR-619 for API quality and FR-616 for reference freshness.
