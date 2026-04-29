# platform-cli

## Observability

The observability sub-app wraps the Helm umbrella chart at
`deploy/helm/observability/`.

```sh
platform-cli observability install --preset minimal
platform-cli observability install --preset standard --namespace platform-observability
platform-cli observability upgrade --preset enterprise -f values-prod.yaml --wait
platform-cli observability status --namespace platform-observability
platform-cli observability uninstall --namespace platform-observability
```

Presets map directly to chart value files:

| Preset | Values file | Use |
|---|---|---|
| `minimal` | `values-minimal.yaml` | Local dev and small test clusters. |
| `standard` | `values-standard.yaml` | Small production installation. |
| `enterprise` | `values-enterprise.yaml` | HA production topology. |
| `e2e` | `values-e2e.yaml` | kind-based E2E tests only. |

`standard` and `enterprise` require the `minio-platform-credentials` secret in
the target namespace before install. Chart-side lifecycle, datasource, and
troubleshooting details are documented in `deploy/helm/observability/README.md`.
