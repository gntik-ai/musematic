# Per-BC Admin Router Inventory

Feature 086 mounts every bounded-context admin router below `/api/v1/admin/*` through
`apps/control-plane/src/platform/admin/router.py`. Each router must declare either
`Depends(require_admin)` or `Depends(require_superadmin)` on every operation.

| BC | Existing router | New admin router | Primary entity table(s) | FR mapping | Gate |
|---|---|---|---|---|---|
| auth | `apps/control-plane/src/platform/auth/router.py` | `apps/control-plane/src/platform/auth/admin_router.py` | `users`, `user_credentials`, `user_roles`, `sessions`, `oauth_providers`, `ibor_connectors` | FR-548 Identity & Access | admin; superadmin for role/provider destructive actions |
| accounts | `apps/control-plane/src/platform/accounts/router.py` | `apps/control-plane/src/platform/accounts/admin_router.py` | `users`, `memberships`, account lifecycle projections | FR-548 users and API keys | admin |
| workspaces | `apps/control-plane/src/platform/workspaces/router.py` | `apps/control-plane/src/platform/workspaces/admin_router.py` | `workspaces`, `memberships`, `workspaces_settings` | FR-549 Tenancy & Workspaces | admin; superadmin for tenants |
| policies | `apps/control-plane/src/platform/policies/router.py` | `apps/control-plane/src/platform/policies/admin_router.py` | `policy_bundles`, `policy_rules`, governance policy tables | FR-550 System Configuration | admin |
| connectors | `apps/control-plane/src/platform/connectors/router.py` | `apps/control-plane/src/platform/connectors/admin_router.py` | connector definitions, connector runs, credentials references | FR-550 System Configuration and FR-555 Integrations | admin |
| privacy_compliance | `apps/control-plane/src/platform/privacy_compliance/router.py` | `apps/control-plane/src/platform/privacy_compliance/admin_router.py` | DSR, DLP, PIA, consent records | FR-551 Security & Compliance | admin |
| security_compliance | `apps/control-plane/src/platform/security_compliance/router.py` | `apps/control-plane/src/platform/security_compliance/admin_router.py` | SBOMs, scans, pentests, rotations, JIT grants | FR-551 Security & Compliance | admin |
| cost_governance | `apps/control-plane/src/platform/cost_governance/router.py` | `apps/control-plane/src/platform/cost_governance/admin_router.py` | `cost_attributions`, `workspace_budgets`, `budget_alerts`, `cost_forecasts`, `cost_anomalies` | FR-553 Cost & Billing | admin |
| multi_region_ops | `apps/control-plane/src/platform/multi_region_ops/router.py` | `apps/control-plane/src/platform/multi_region_ops/admin_router.py` | regions, replication status, failover and maintenance tables | FR-552 Operations & Health | admin; superadmin + 2PA for failover and regions |
| model_catalog | `apps/control-plane/src/platform/model_catalog/router.py` | `apps/control-plane/src/platform/model_catalog/admin_router.py` | model catalog entries, model cards, fallback policies | FR-550 System Configuration | admin |
| notifications | `apps/control-plane/src/platform/notifications/router.py` | `apps/control-plane/src/platform/notifications/admin_router.py` | notification channels, webhooks, templates, alerts | FR-555 Integrations | admin |
| incident_response | `apps/control-plane/src/platform/incident_response/router.py` | `apps/control-plane/src/platform/incident_response/admin_router.py` | `incidents`, `runbooks`, `post_mortems`, `incident_integrations` | FR-552 Operations & Health and FR-555 Integrations | admin |
| audit | `apps/control-plane/src/platform/audit/router.py` | `apps/control-plane/src/platform/audit/admin_router.py` | `audit_events`, `audit_chain_entries` | FR-557 Audit & Logs | admin; superadmin for signed exports |

Notes:

- The admin composition layer owns only route mounting and cross-cutting primitives.
- Business logic remains with each bounded context; admin routers compose existing services.
- Super-admin-only operations must return FR-583 structured `403` responses, not `404`.
