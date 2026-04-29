# Quickstart: Incident Response and Runbooks

This walkthrough exercises the local control plane with provider mocks only. Do not use real PagerDuty, OpsGenie, or VictorOps credentials here; the mock providers accept any auth value and return deterministic success or error payloads.

## Prerequisites

- Control plane running locally with `FEATURE_E2E_MODE=true`.
- PostgreSQL, Redis, Kafka, and the configured MinIO-compatible object store available to the control plane.
- Seeded runbooks from migration `063_incident_response.py`.
- A superadmin or platform-operator token for integration setup and post-mortem distribution.

## Provider Mocks

Reusable mocks live in `tests/fixtures/incident_response/provider_mocks/`.

- `provider_mock("pagerduty")` emulates `POST https://events.pagerduty.com/v2/enqueue` and returns `{status, message, dedup_key}`.
- `provider_mock("opsgenie")` emulates `POST https://api.opsgenie.com/v2/alerts` and close requests under `/v2/alerts/{alias}/close`; it returns `{result, requestId, took}`.
- `provider_mock("victorops")` emulates `POST https://alert.victorops.com/integrations/generic/20131114/alert/{key}/{route}` and returns `{result, entity_id}`.
- Pass `status_code=503` or send header `x-musematic-mock-status: 503` to exercise retryable provider failure shapes.

The mock response shapes are covered by `tests/fixtures/incident_response/provider_mocks/test_provider_mocks.py`.

## Walkthrough

1. Configure a provider integration with a Vault reference, not a credential value:

   ```bash
   curl -sS -X POST "$CONTROL_PLANE_URL/api/v1/admin/incidents/integrations" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "provider": "pagerduty",
       "integration_key_ref": "incident-response/integrations/local-pagerduty",
       "enabled": true,
       "alert_severity_mapping": {
         "critical": "critical",
         "high": "error",
         "warning": "warning",
         "info": "info"
       }
     }'
   ```

2. Fire a synthetic alert through the E2E-only seed endpoint:

   ```bash
   curl -sS -X POST "$CONTROL_PLANE_URL/api/v1/_e2e/incidents/seed/kafka-lag" \
     -H "Authorization: Bearer $OPERATOR_TOKEN"
   ```

3. Open `/operator/incidents` and verify the incident appears with status `open`, severity `critical`, and an external delivery state row.

4. Open the incident detail page and verify the matching runbook is visible inline. Diagnostic commands should be copyable from the runbook panel.

5. Resolve the incident:

   ```bash
   curl -sS -X POST "$CONTROL_PLANE_URL/api/v1/incidents/$INCIDENT_ID/resolve" \
     -H "Authorization: Bearer $OPERATOR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"resolution_note":"Validated recovery in local smoke test"}'
   ```

6. Start the post-mortem from the resolved incident:

   ```bash
   curl -sS -X POST "$CONTROL_PLANE_URL/api/v1/incidents/$INCIDENT_ID/post-mortem" \
     -H "Authorization: Bearer $OPERATOR_TOKEN"
   ```

7. Update post-mortem sections and confirm timeline source coverage is explicit for audit chain, execution journal, and Kafka.

8. Publish and distribute the post-mortem:

   ```bash
   curl -sS -X POST "$CONTROL_PLANE_URL/api/v1/post-mortems/$POST_MORTEM_ID/distribute" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"recipients":["oncall@example.test","ops-review@example.test"]}'
   ```

9. Verify the response carries per-recipient delivery outcomes and the UI displays each outcome instead of collapsing partial failure into a generic success.

## Expected Signals

- Kafka emits `incident.triggered` on create and `incident.resolved` on resolve.
- Provider failure records remain attached to the local incident and are retried by the delivery scanner.
- Integration and runbook mutations append audit-chain entries without credential values.
- Timeline coverage is never silently complete: unavailable or partial sources are visible in both API responses and the post-mortem UI.
