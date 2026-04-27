# Dashboard De-Duplication Audit

Feature 084 reconciles the brownfield D8-D21 dashboard list against the existing
observability dashboard ConfigMaps under `deploy/helm/observability/templates/dashboards/`.

| ID | Dashboard | Decision | Target |
| --- | --- | --- | --- |
| D8 | Control Plane Service Logs | CREATE | `control-plane-logs.yaml` |
| D9 | Go Satellite Service Logs | CREATE | `go-services-logs.yaml` |
| D10 | Frontend Web Logs | CREATE | `frontend-web-logs.yaml` |
| D11 | Audit Event Stream | CREATE | `audit-event-stream.yaml` |
| D12 | Cross-Service Error Overview | CREATE | `cross-service-errors.yaml` |
| D13 | Privacy & Compliance | CREATE | `privacy-compliance.yaml` |
| D14 | Security Compliance | CREATE | `security-compliance.yaml` |
| D15 | Cost Governance | EXTEND | existing `cost-governance.yaml` |
| D16 | Multi-Region Operations | EXTEND | existing `multi-region-ops.yaml` |
| D17 | Model Catalog & Fallback | CREATE | `model-catalog.yaml` |
| D18 | Notifications Delivery | EXTEND | existing `notifications-channels.yaml` |
| D19 | Incident Response & Runbooks | CREATE | `incident-response.yaml` |
| D20 | Goal Lifecycle & Agent Responses | CREATE | `goal-lifecycle.yaml` |
| D21 | Governance Pipeline | CREATE | `governance-pipeline.yaml` |

No dashboard is a replacement. Existing metric panels remain owned by their
original features; this feature adds log pivots or net-new dashboards only.
