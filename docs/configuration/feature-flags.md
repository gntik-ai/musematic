# Feature Flags

Feature flags are configured through environment variables and, where applicable, Helm values. Production changes should be audited and tied to a rollout plan.

| Flag | Default | Scope | Controlled By | Description | Related Requirements | Rollout History |
| --- | --- | --- | --- | --- | --- | --- |
| `FEATURE_GOAL_AUTO_COMPLETE` | `false` | Workspace | Platform admin | Auto-completes workspace goals when completion signals are met. | FR-612 | Added before UPD-039. |
| `FEATURE_E2E_MODE` | `false` | Platform | Operator | Enables E2E-only test paths and mock-provider controls. | FR-612 | Used by test harness. |
| `FEATURE_COST_HARD_CAPS` | `false` | Workspace | Admin / super admin | Enforces budget hard caps in cost governance. | FR-612 | Added with cost governance. |
| `FEATURE_MAINTENANCE_MODE` | `false` | Platform / region | Super admin | Enables maintenance gate behavior. | FR-612 | Added with multi-region ops. |
| `FEATURE_MULTI_REGION` | `false` | Platform | Super admin | Enables multi-region routes and controls. | FR-612 | Added with feature 081. |
| `FEATURE_PRIVACY_DSR_ENABLED` | `false` | Platform | Privacy officer | Enables data-subject request operations. | FR-612 | Added with privacy compliance. |
| `FEATURE_DLP_ENABLED` | `false` | Platform | Privacy officer | Enables DLP rule/event surfaces. | FR-612 | Added with privacy compliance. |
| `FEATURE_RESIDENCY_ENFORCEMENT` | `false` | Platform / tenant | Privacy officer | Enforces workspace residency policy. | FR-612 | Added with privacy compliance. |
| `FEATURE_API_RATE_LIMITING` | `true` | Platform | Platform admin | Enables API gateway rate limiting. | FR-588, FR-612 | Added with API governance. |
| `FEATURE_API_RATE_LIMITING_FAIL_OPEN` | `false` | Platform | Super admin | Allows API traffic when rate limiter is unavailable. | FR-612 | Emergency-only setting. |
| `FEATURE_AUDIT_CHAIN_STRICT` | `false` | Platform | Auditor / super admin | Fails closed on audit append errors. | FR-612 | Added with audit chain. |
| `FEATURE_VULN_GATE_ENABLED` | `true` | Platform | Security admin | Enforces vulnerability gate checks. | FR-612 | Added with security compliance. |
| `FEATURE_MULTI_CHANNEL_NOTIFICATIONS` | `false` | Platform | Platform admin | Enables Slack, Teams, SMS, and webhook delivery families. | FR-612 | Added with notifications. |
| `FEATURE_ALLOW_HTTP_WEBHOOKS` | `false` | Platform | Super admin | Allows non-TLS webhook URLs outside production. | FR-612 | Blocked in production validation. |
| `FEATURE_MODEL_ROUTER_ENABLED` | `true` | Platform | Platform admin | Enables model router and fallback behavior. | FR-612 | Added with model catalog. |
| `FEATURE_CONTENT_MODERATION` | `false` | Platform / workspace | Trust admin | Enables content moderation providers and policy checks. | FR-612 | Added with trust safety. |

When changing a flag, record the actor, reason, expected duration, rollback condition, and dashboard used for verification.
