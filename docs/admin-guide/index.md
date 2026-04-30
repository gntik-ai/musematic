# Administrator Guide

The Administrator Guide mirrors the Admin Workbench sections from feature 086 and FR-548 through FR-557. It is written for workspace admins, platform admins, auditors, and super admins who manage users, tenants, settings, compliance, lifecycle state, cost, integrations, and audit evidence.

| Page | Scope |
| --- | --- |
| [Identity and Access](identity-access.md) | Users, roles, MFA, lockout, invitations, OAuth account state. |
| [OAuth Providers](oauth-providers.md) | Google and GitHub OAuth provider setup, rotation, role mappings, history, and rate limits. |
| [Tenancy and Workspaces](tenancy-workspaces.md) | Workspace creation, membership, quotas, visibility, goals. |
| [System Configuration](system-config.md) | Provider credentials, OAuth, feature switches, safe configuration changes. |
| [Security and Compliance](security-compliance.md) | Audit chain, evidence, vulnerability gates, privacy operations. |
| [Operations Health](operations-health.md) | Service health, maintenance windows, incidents, capacity warnings. |
| [Cost and Billing](cost-billing.md) | Budgets, forecasts, chargeback, hard caps, anomaly review. |
| [Observability](observability.md) | Dashboards, logs, traces, metrics, alert routing. |
| [Integrations](integrations.md) | Notification channels, webhooks, A2A endpoints, provider tests. |
| [Lifecycle](lifecycle.md) | Agent, workspace, user, model, and release lifecycle controls. |
| [Audit Logs](audit-logs.md) | Search, export, attestations, evidence review, correlation. |
| [Self-Service Surfaces](self-service-surfaces.md) | User-facing equivalents for notifications, API keys, MFA, sessions, consent, DSR, and activity. |

High-risk actions may require step-up authentication or two-person approval. If an action fails with `admin_read_only_mode` or `two_person_approval_required`, start the required approval flow before retrying.
