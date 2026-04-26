# Quickstart: Cost Governance and Chargeback

## Local Walkthrough

1. Start the control plane with PostgreSQL, Redis, Kafka, and ClickHouse.
2. Enable hard caps when testing refusal paths: `FEATURE_COST_HARD_CAPS=true`.
3. Create or select a workspace and configure a daily budget through `POST /api/v1/costs/workspaces/{workspace_id}/budgets`.
4. Run synthetic load that emits execution runtime events with model token counts.
5. Verify attribution through `GET /api/v1/costs/workspaces/{workspace_id}/attributions`.
6. Drive spend across the configured thresholds and verify budget alerts.
7. Seed steady history, inject a controlled spike, run anomaly detection, then acknowledge the anomaly.

## Smoke-Run Notes

- Static walkthrough reviewed against the implemented router, services, and frontend routes on 2026-04-26.
- The local external-service stack was not started in this task run; backend unit and contract-style integration coverage now exercise the same configure budget, synthetic load attribution, alert, anomaly, and acknowledgement paths without external services.
