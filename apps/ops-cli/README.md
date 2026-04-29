# platform-cli

## Super Admin

The `superadmin` sub-app is reserved for platform-wide recovery operations. It is a
sibling to the tenant-scoped `admin` sub-app.

```sh
platform-cli superadmin recover --username eve --email eve@example.com
platform-cli superadmin reset --force --username alice --email alice@example.com
```

`recover` is the FR-579 break-glass path. It must run from a console with physical
cluster access and a valid emergency key at `/etc/musematic/emergency-key.bin`
unless `--emergency-key-path` points to the sealed install-time key. A successful
recovery creates or restores the super admin, emits a critical audit-chain entry,
and notifies remaining super admins through configured notification channels.

`reset --force` maps to the headless bootstrap reset path. In production,
`ALLOW_SUPERADMIN_RESET=true` is required in addition to the force flag.

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
