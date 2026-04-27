# Admin Page Inventory

All pages live under `apps/web/app/(admin)/` and use the shared `AdminLayout`,
`AdminPage`, and `AdminTable` primitives unless noted. Role gates are enforced
server-side in the route group layout and repeated by the backing API.

| Route | Section / FR | Gate | Backing API | Data dependencies |
|---|---|---|---|---|
| `/admin` | Landing / FR-547 | admin or superadmin | `/api/v1/admin/health`, `/api/v1/admin/activity` | summary counters, incidents, approvals, audit-chain status |
| `/admin/users` | Identity & Access / FR-548 | admin | `/api/v1/admin/users` | users, credentials, roles, sessions |
| `/admin/users/[id]` | Identity & Access / FR-548 | admin | `/api/v1/admin/users/{id}` | user detail, roles, sessions, audit entries |
| `/admin/roles` | Identity & Access / FR-548 | admin | `/api/v1/admin/roles` | role permissions |
| `/admin/roles/[id]` | Identity & Access / FR-548 | admin | `/api/v1/admin/roles/{id}` | role detail, permission diff |
| `/admin/groups` | Identity & Access / FR-548 | admin | `/api/v1/admin/groups` | directory groups, role mappings |
| `/admin/sessions` | Identity & Access / FR-548 | admin | `/api/v1/admin/sessions` | active sessions |
| `/admin/oauth-providers` | Identity & Access / FR-548 | admin | `/api/v1/admin/oauth-providers` | OAuth providers, domain restrictions |
| `/admin/ibor` | Identity & Access / FR-548 | admin | `/api/v1/admin/ibor/connectors` | IBOR connectors, sync status |
| `/admin/ibor/[connector_id]` | Identity & Access / FR-548 | admin | `/api/v1/admin/ibor/connectors/{connector_id}` | sync runs, mappings |
| `/admin/api-keys` | Identity & Access / FR-548 | admin | `/api/v1/admin/api-keys` | service-account credentials |
| `/admin/tenants` | Tenancy & Workspaces / FR-549 | superadmin | `/api/v1/admin/tenants` | tenants, tenant mode |
| `/admin/tenants/[id]` | Tenancy & Workspaces / FR-549 | superadmin | `/api/v1/admin/tenants/{id}` | tenant detail, users, workspaces |
| `/admin/workspaces` | Tenancy & Workspaces / FR-549 | admin | `/api/v1/admin/workspaces` | workspaces, membership counts |
| `/admin/workspaces/[id]` | Tenancy & Workspaces / FR-549 | admin | `/api/v1/admin/workspaces/{id}` | workspace detail, members, quotas |
| `/admin/workspaces/[id]/quotas` | Tenancy & Workspaces / FR-549 | admin | `/api/v1/admin/workspaces/{id}/quotas` | quota settings and usage |
| `/admin/namespaces` | Tenancy & Workspaces / FR-549 | admin | `/api/v1/admin/namespaces` | namespace inventory |
| `/admin/settings` | System Configuration / FR-550 | admin | `/api/v1/admin/settings` | platform settings |
| `/admin/feature-flags` | System Configuration / FR-550 | admin | `/api/v1/admin/feature-flags` | scoped feature flags |
| `/admin/model-catalog` | System Configuration / FR-550 | admin | `/api/v1/admin/model-catalog` | model catalog entries |
| `/admin/model-catalog/[id]` | System Configuration / FR-550 | admin | `/api/v1/admin/model-catalog/{id}` | model detail, cards, fallback policy |
| `/admin/policies` | System Configuration / FR-550 | admin | `/api/v1/admin/policies` | policy bundles and rules |
| `/admin/connectors` | System Configuration / FR-550 | admin | `/api/v1/admin/connectors` | connector definitions and runs |
| `/admin/audit-chain` | Security & Compliance / FR-551 | admin | `/api/v1/admin/audit-chain` | chain verification, attestations |
| `/admin/security/sbom` | Security & Compliance / FR-551 | admin | `/api/v1/admin/security/sbom` | SBOM documents |
| `/admin/security/pentests` | Security & Compliance / FR-551 | admin | `/api/v1/admin/security/pentests` | pentest reports |
| `/admin/security/rotations` | Security & Compliance / FR-551 | admin | `/api/v1/admin/security/rotations` | secret rotation schedules |
| `/admin/security/jit` | Security & Compliance / FR-551 | admin | `/api/v1/admin/security/jit` | JIT grants |
| `/admin/privacy/dsr` | Security & Compliance / FR-551 | admin | `/api/v1/admin/privacy/dsr` | DSR queue |
| `/admin/privacy/dlp` | Security & Compliance / FR-551 | admin | `/api/v1/admin/privacy/dlp` | DLP rules and events |
| `/admin/privacy/pia` | Security & Compliance / FR-551 | admin | `/api/v1/admin/privacy/pia` | PIA reviews |
| `/admin/compliance` | Security & Compliance / FR-551 | admin | `/api/v1/admin/compliance` | compliance controls |
| `/admin/privacy/consent` | Security & Compliance / FR-551 | admin | `/api/v1/admin/privacy/consent` | consent records |
| `/admin/health` | Operations & Health / FR-552 | admin | `/api/v1/admin/health` | service health, Grafana panel |
| `/admin/incidents` | Operations & Health / FR-552 | admin | `/api/v1/admin/incidents` | incidents, ADMIN_INCIDENTS channel |
| `/admin/incidents/[id]` | Operations & Health / FR-552 | admin | `/api/v1/admin/incidents/{id}` | incident detail |
| `/admin/runbooks` | Operations & Health / FR-552 | admin | `/api/v1/admin/runbooks` | runbook library |
| `/admin/runbooks/[id]` | Operations & Health / FR-552 | admin | `/api/v1/admin/runbooks/{id}` | runbook detail |
| `/admin/maintenance` | Operations & Health / FR-552 | admin | `/api/v1/admin/maintenance` | maintenance windows |
| `/admin/regions` | Operations & Health / FR-552 | superadmin | `/api/v1/admin/regions` | regions, failover, replication |
| `/admin/queues` | Operations & Health / FR-552 | admin | `/api/v1/admin/queues` | queue depth and lag |
| `/admin/warm-pool` | Operations & Health / FR-552 | admin | `/api/v1/admin/warm-pool` | warm-pool capacity |
| `/admin/executions` | Operations & Health / FR-552 | admin | `/api/v1/admin/executions` | execution status |
| `/admin/costs/overview` | Cost & Billing / FR-553 | admin | `/api/v1/admin/costs/overview` | cost summaries |
| `/admin/costs/budgets` | Cost & Billing / FR-553 | admin | `/api/v1/admin/costs/budgets` | budgets, alerts |
| `/admin/costs/chargeback` | Cost & Billing / FR-553 | admin | `/api/v1/admin/costs/chargeback` | cost attributions |
| `/admin/costs/anomalies` | Cost & Billing / FR-553 | admin | `/api/v1/admin/costs/anomalies` | anomalies |
| `/admin/costs/forecasts` | Cost & Billing / FR-553 | admin | `/api/v1/admin/costs/forecasts` | forecasts |
| `/admin/costs/rates` | Cost & Billing / FR-553 | admin | `/api/v1/admin/costs/rates` | rates and model costs |
| `/admin/observability/dashboards` | Observability / FR-554 | admin | `/api/v1/admin/observability/dashboards` | dashboard inventory |
| `/admin/observability/alerts` | Observability / FR-554 | admin | `/api/v1/admin/observability/alerts` | Prometheus and Loki rules |
| `/admin/observability/log-retention` | Observability / FR-554 | admin | `/api/v1/admin/observability/log-retention` | retention settings |
| `/admin/observability/registry` | Observability / FR-554 | admin | `/api/v1/admin/observability/registry` | metrics/logs/traces registry |
| `/admin/integrations/webhooks` | Integrations / FR-555 | admin | `/api/v1/admin/integrations/webhooks` | outbound webhooks |
| `/admin/integrations/incidents` | Integrations / FR-555 | admin | `/api/v1/admin/integrations/incidents` | incident integrations |
| `/admin/integrations/notifications` | Integrations / FR-555 | admin | `/api/v1/admin/integrations/notifications` | notification channels |
| `/admin/integrations/a2a` | Integrations / FR-555 | admin | `/api/v1/admin/integrations/a2a` | A2A gateway config |
| `/admin/integrations/mcp` | Integrations / FR-555 | admin | `/api/v1/admin/integrations/mcp` | MCP servers and tools |
| `/admin/lifecycle/version` | Platform Lifecycle / FR-556 | superadmin | `/api/v1/admin/lifecycle/version` | version and release metadata |
| `/admin/lifecycle/migrations` | Platform Lifecycle / FR-556 | superadmin | `/api/v1/admin/lifecycle/migrations` | migration state |
| `/admin/lifecycle/backup` | Platform Lifecycle / FR-556 | superadmin | `/api/v1/admin/lifecycle/backup` | backups |
| `/admin/lifecycle/installer` | Platform Lifecycle / FR-556 | superadmin | `/api/v1/admin/lifecycle/installer` | installer state, config import/export |
| `/admin/audit` | Audit & Logs / FR-557 | admin | `/api/v1/admin/audit` | unified audit query |
| `/admin/audit/admin-activity` | Audit & Logs / FR-557 | admin | `/api/v1/admin/activity` | admin activity feed |
