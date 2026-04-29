# Dashboard Inventory

This is the source-of-truth inventory for the dashboard ConfigMaps shipped by
`deploy/helm/observability/templates/dashboards/` for feature 085.

| # | ConfigMap template | Dashboard UID | Owning feature |
|---:|---|---|---|
| 1 | `platform-overview.yaml` | `platform-overview` | 047-observability-stack |
| 2 | `workflow-execution.yaml` | `workflow-execution` | 047-observability-stack |
| 3 | `reasoning-engine.yaml` | `reasoning-engine` | 047-observability-stack |
| 4 | `data-stores.yaml` | `data-stores` | 047-observability-stack |
| 5 | `fleet-health.yaml` | `fleet-health` | 033-fleet-management-learning |
| 6 | `self-correction.yaml` | `self-correction` | 064-reasoning-modes-and-trace |
| 7 | `cost-intelligence.yaml` | `cost-intelligence` | 020-analytics-cost-intelligence |
| 8 | `control-plane-logs.yaml` | `d8-control-plane-logs` | 084-log-aggregation-dashboards |
| 9 | `go-services-logs.yaml` | `d9-go-services-logs` | 084-log-aggregation-dashboards |
| 10 | `frontend-web-logs.yaml` | `d10-frontend-web-logs` | 084-log-aggregation-dashboards |
| 11 | `audit-event-stream.yaml` | `d11-audit-event-stream` | 084-log-aggregation-dashboards |
| 12 | `cross-service-errors.yaml` | `d12-cross-service-errors` | 084-log-aggregation-dashboards |
| 13 | `privacy-compliance.yaml` | `d13-privacy-compliance` | 076-privacy-compliance |
| 14 | `security-compliance.yaml` | `d14-security-compliance` | 074-security-compliance |
| 15 | `cost-governance.yaml` | `cost-governance` | 079-cost-governance-chargeback |
| 16 | `notifications-channels.yaml` | `notifications-channels` | 077-multi-channel-notifications |
| 17 | `model-catalog.yaml` | `d17-model-catalog` | 075-model-catalog-fallback |
| 18 | `multi-region-ops.yaml` | `multi-region-ops` | 081-multi-region-ha |
| 19 | `incident-response.yaml` | `d19-incident-response` | 080-incident-response-runbooks |
| 20 | `goal-lifecycle.yaml` | `d20-goal-lifecycle` | 059-workspace-goal-response |
| 21 | `governance-pipeline.yaml` | `d21-governance-pipeline` | 061-judge-enforcer-governance |
| 22 | `trust-content-moderation.yaml` | `trust-content-moderation` | 078-content-safety-fairness |
| 23 | `localization.yaml` | `localization` | 083-accessibility-i18n |

The 22nd dashboard, `trust-content-moderation.yaml`, is intentionally included.
It is owned by feature 078 and was omitted from the brownfield-input 21-row
enumeration.

`localization.yaml` was added by feature 083 after the original UPD-035
brownfield inventory was drafted. Feature 085's chart checks therefore assert
the current on-disk count of 23 dashboard ConfigMaps.
