# Quickstart: UPD-034 Log Aggregation and Dashboards

This walkthrough validates the local operator path for Loki + Promtail + Grafana + Jaeger:

1. Deploy the observability stack.
2. Emit a structured JSON log.
3. Query it through Loki.
4. Confirm Grafana can pivot from logs to Jaeger by `trace_id`.
5. Trigger the audit-chain Loki alert route.

## Prerequisites

- Docker and kind are available.
- Helm 3 is available.
- The local control-plane stack can be started with `make dev-up`.
- S3-compatible credentials are available to the Helm chart through the existing `minio-platform-credentials` secret keys: `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_USE_PATH_STYLE`.

Cold-cache `make dev-up` and Helm dependency resolution can exceed 5 minutes on a first run.

## Deploy

```bash
make dev-up
helm dependency build deploy/helm/observability
helm upgrade --install musematic-observability deploy/helm/observability \
  --namespace platform-observability \
  --create-namespace \
  --values deploy/helm/observability/values-e2e.yaml \
  --api-versions loki.grafana.com/v1/LokiRule
```

Forward the local service ports:

```bash
kubectl -n platform-observability port-forward svc/observability-loki-gateway 3100:80
kubectl -n platform-observability port-forward svc/musematic-observability-grafana 3000:80
kubectl -n platform-observability port-forward svc/kube-prometheus-stack-alertmanager 9093:9093
kubectl -n platform-observability port-forward svc/musematic-observability-jaeger-query 16686:16686
```

## Emit and Query a Structured Log

```bash
now="$(date +%s%N)"
trace_id="0123456789abcdef0123456789abcdef"
curl -sS -X POST http://localhost:3100/loki/api/v1/push \
  -H 'Content-Type: application/json' \
  -d "{
    \"streams\": [{
      \"stream\": {\"service\":\"api\",\"bounded_context\":\"audit\",\"level\":\"error\"},
      \"values\": [[\"${now}\", \"{\\\"timestamp\\\":\\\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\\\",\\\"level\\\":\\\"error\\\",\\\"service\\\":\\\"api\\\",\\\"bounded_context\\\":\\\"audit\\\",\\\"message\\\":\\\"chain mismatch invalid hash quickstart\\\",\\\"trace_id\\\":\\\"${trace_id}\\\",\\\"correlation_id\\\":\\\"quickstart\\\"}\"]]
    }]
  }"
curl -G -sS http://localhost:3100/loki/api/v1/query_range \
  --data-urlencode 'query={service="api",bounded_context="audit"} | json | correlation_id="quickstart"'
```

The query should return the emitted JSON payload with `service`, `bounded_context`, `level`, `message`, `trace_id`, and `correlation_id`.

## Grafana Pivot Checks

Open Grafana at `http://localhost:3000` and load:

- Platform Overview: verify the Loki log-volume panels render.
- D11 Audit Event Stream: verify the emitted audit log appears.
- Explore > Loki: query `{service="api",bounded_context="audit"} | json | correlation_id="quickstart"` and confirm `trace_id` renders with the Jaeger derived-field link.

The Jaeger target should open in the configured Jaeger data source using the same `trace_id`.

## Alert Route Check

The synthetic log above matches the `AuditChainAnomaly` Loki rule. When live alert firing is enabled, run:

```bash
cd tests/e2e
MUSEMATIC_E2E_ALERT_FIRE=1 \
MUSEMATIC_E2E_LOKI_URL=http://localhost:3100 \
MUSEMATIC_E2E_GRAFANA_URL=http://localhost:3000 \
MUSEMATIC_E2E_ALERTMANAGER_URL=http://localhost:9093 \
python -m pytest suites/observability/test_alerts_fire.py -q
```

The test polls Alertmanager for `AuditChainAnomaly` with `incident_trigger=audit_chain_anomaly`.

## Local Smoke Commands

```bash
python scripts/ci/check_loki_label_cardinality.py
python scripts/ci/check_observability_dashboards.py
helm lint deploy/helm/observability --strict
helm template release deploy/helm/observability --api-versions loki.grafana.com/v1/LokiRule >/tmp/musematic-observability.yaml
```

## Deviations Captured

- `values-e2e.yaml` shortens Loki retention for local tests; production-like values keep `hot: 336h` and `cold: 2160h`.
- The live alert-firing and retention-boundary tests are opt-in because they require a running observability stack and clock/control-plane coordination.
- In this workspace, the Spec Kit prerequisite script can reject timestamped branch names even when `.specify/feature.json` points at `specs/084-log-aggregation-dashboards`; use the feature.json path as the source of truth for this quickstart.
