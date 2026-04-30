# Rule 45 UI Mapping

Status: static mapping complete.

| Backend capability | UI surface |
| --- | --- |
| `GET /api/v1/workspaces/{id}/summary` | `/workspaces/{id}` dashboard cards |
| Workspace member add/update/remove | `/workspaces/{id}/members` |
| Ownership transfer challenge creation | `/workspaces/{id}/members` transfer dialog |
| 2PA challenge metadata/consume | `/workspaces/{id}/members` transfer dialog |
| Workspace settings budget/quota/DLP/residency | `/workspaces/{id}/settings` and `/workspaces/{id}/quotas` |
| Connector list/detail | `/workspaces/{id}/connectors` and `/workspaces/{id}/connectors/{connectorId}` |
| Connector test-connectivity | `/workspaces/{id}/connectors` setup wizard |
| Connector deliveries | `/workspaces/{id}/connectors/{connectorId}` activity panel |
| Visibility grants | `/workspaces/{id}/visibility` |
| IBOR test-connection/sync/history | `/admin/settings?tab=ibor` |
| Admin workspace index | `/admin/settings?tab=workspaces` |
