# Event Topology

Kafka connects bounded contexts without forcing synchronous coupling. Events are used for workflow runtime state, account lifecycle, workspace provisioning, registry lifecycle, policy decisions, trust evidence, notifications, incidents, and analytics ingestion.

| Topic Family | Typical Producers | Typical Consumers |
| --- | --- | --- |
| `auth.events` | Auth service | Audit, analytics, notifications. |
| `accounts.events` | Accounts service | Workspaces, audit, signup dashboards. |
| `workspaces.events` | Workspaces service | WebSocket gateway, analytics. |
| `workflow.runtime` | Execution scheduler | WebSocket gateway, analytics, incidents. |
| `execution.events` | Execution service | WebSocket gateway, audit, dashboards. |
| `runtime.lifecycle` | Runtime Controller | WebSocket gateway, operator dashboards. |
| `trust.events` | Trust and certification services | Audit, analytics, compliance. |
| `notifications.events` | Notification service | Dead-letter monitoring, audit. |
| `incident.events` | Incident response | Operator dashboards, post-mortems. |

Event consumers must be idempotent because retries and replay are expected. Correlation IDs and GIDs should flow through every envelope when available.
