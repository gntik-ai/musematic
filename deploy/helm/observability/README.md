# Musematic Observability Chart

`deploy/helm/observability/` is the umbrella chart for Prometheus, Grafana,
Alertmanager, Jaeger, Loki, Promtail, and the OTEL Collector. It installs into
`platform-observability` and ships all dashboard, alert-rule, and Grafana
datasource ConfigMaps used by the E2E journeys.

## Install

```bash
helm upgrade --install observability ./deploy/helm/observability \
  --namespace platform-observability \
  --create-namespace \
  -f ./deploy/helm/observability/values-minimal.yaml \
  --wait
```

Presets:

| Preset | Use | Capacity Envelope |
|---|---|---|
| `minimal` | dev/kind with persistence | <= 1 GiB RAM, 100k series, 10 logs/s, 100 traces/s |
| `standard` | small production | ~4 GiB RAM, 1M series, 100 logs/s, 1k traces/s |
| `enterprise` | HA production | ~16 GiB RAM, 10M series, 10k logs/s, 100k traces/s |
| `e2e` | CI kind only | <= 1 GiB RAM, 1h retention, no PVs, no S3 |

The equivalent CLI path is:

```bash
platform-cli observability install --preset standard --wait
platform-cli observability status
```

## S3 Bucket Setup

`standard` and `enterprise` use S3-compatible storage for Loki chunks and run
the `loki-bucket-init` pre-install hook. The hook expects the
`minio-platform-credentials` secret to exist in `platform-observability`.
Production installs should install the platform chart first or pre-create that
generic-S3 secret. `minimal` and `e2e` use filesystem storage and skip the hook.

## Datasources

Grafana datasource provisioning is sidecar-driven. The chart renders three
ConfigMaps labelled `grafana_datasource: "1"`:

| Datasource | UID | Contract |
|---|---|---|
| Prometheus | `prometheus` | Default metrics datasource |
| Loki | `loki` | Derived fields for `trace_id` -> Jaeger and `correlation_id` -> Loki query |
| Jaeger | `jaeger` | Trace datasource referenced by the Loki derived field |

After install, verify:

```bash
kubectl -n platform-observability port-forward svc/observability-grafana 3000:80
curl -fsS http://localhost:3000/api/health
```

## Dashboards And Alerts

Dashboard inventory is versioned at
`specs/085-extended-e2e-journey/contracts/dashboard-inventory.md`. The chart
currently ships 22 dashboard ConfigMaps; `trust-content-moderation.yaml` is the
feature 078 dashboard that was absent from the brownfield 21-row list.

Alert rules are rendered from `templates/alerts/`. Loki label-cardinality rules
are enforced by the feature 084 lint:
`scripts/ci/check_loki_label_cardinality.py`.

## Uninstall

```bash
platform-cli observability uninstall
platform-cli observability uninstall --purge-pvcs
```

Without `--purge-pvcs`, the CLI lists Helm-owned PVCs, CRDs, webhooks, and
ConfigMaps that may remain after `helm uninstall`. With `--purge-pvcs`, it asks
for confirmation before deleting those residual resources.

## Troubleshooting

| Symptom | Check |
|---|---|
| PVC pending in `minimal` | Verify the cluster has a default StorageClass or switch to `values-e2e.yaml` for ephemeral CI. |
| S3 bucket creation fails | Confirm `minio-platform-credentials` exists and contains `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, and `S3_SECRET_KEY`. |
| Renderer OOMs | Use `minimal` or `e2e`, where `grafana-image-renderer` is disabled, or raise Grafana memory limits. |
| Datasource duplicates | Confirm `kube-prometheus-stack.grafana.additionalDataSources` is not reintroduced in tenant overlays. |

## Tested Distributions

The everyday CI target is kind via `tests/e2e/cluster/install.sh` with
`values-e2e.yaml`. k3s and managed-cluster smoke results are tracked by feature
085 validation tasks.
