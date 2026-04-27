# Cost and Billing

Cost pages expose workspace budgets, hard caps, attribution, chargeback reports, forecasts, and anomalies from the cost governance bounded context.

## Common Admin Workflows

### Set a Workspace Budget

Choose period type, budget amount, alert thresholds, and hard-cap behavior. Confirm owners receive notifications before enforcement begins.

### Review an Anomaly

Open the anomaly, compare against recent executions and provider activity, then either acknowledge it or adjust the budget/forecast model.

### Generate Chargeback

Select workspace, period, and output format. Wait for the asynchronous report, then verify totals against the monthly finance cycle.

### Grant a Cost Override

Use a single-shot override token only for approved urgent work. The override should expire within five minutes and should be attached to an audit event.
