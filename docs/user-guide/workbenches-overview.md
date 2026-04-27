# Workbenches Overview

Musematic workbenches group related workflows for repeated operational use.

| Workbench | Primary Users | Purpose |
| --- | --- | --- |
| Operator | Operators and platform admins | Cluster health, incidents, dashboards, runbooks, logs, traces, and deployment state. |
| Trust | Trust reviewers, compliance officers, agent owners | Certification queue, evidence, trust radar, policy attachments, privacy impact, and moderation review. |
| Admin | Workspace admins and platform admins | Identity, tenancy, OAuth, feature flags, lifecycle actions, cost, integrations, observability, and audit logs. |
| Super Admin | Super admins | Global platform settings, break-glass recovery, multi-region execution, maintenance windows, and high-risk approval flows. |

Each workbench is backed by the same REST and WebSocket surfaces documented in the [API Reference](../api-reference/index.md). Access is role-scoped, and high-risk actions may require step-up authentication or two-person approval.
