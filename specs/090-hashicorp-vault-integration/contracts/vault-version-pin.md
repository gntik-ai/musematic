# Vault Helm Chart Pin — UPD-040

Date: 2026-04-30

## Decision

Pin the Musematic wrapper chart to upstream `hashicorp/vault` chart `0.32.0`, which currently carries Vault app version `1.21.2`.

## Source Check

- [HashiCorp Developer's Vault Helm documentation](https://developer.hashicorp.com/vault/docs/deploy/kubernetes/helm) lists `hashicorp/vault` chart version `0.32.0` with app version `1.21.2` as the current chart shown by `helm search repo hashicorp/vault`.
- The same HashiCorp documentation lists recent versions as `0.32.0`, `0.31.0`, `0.30.1`, `0.30.0`, `0.29.1`, and `0.29.0`, so the brownfield default `0.30.0` is no longer current.
- The [`v0.32.0` release notes](https://github.com/hashicorp/vault-helm/releases/tag/v0.32.0) state it updates the default Vault image to `1.21.2`, updates `vault-k8s` and `vault-csi-provider`, and is tested with Kubernetes `1.31` through `1.35`.

## Compatibility Notes Since `0.30.0`

- `0.30.1` moved defaults to Vault `1.20.1`, `vault-k8s` `1.7.0`, and widened tested Kubernetes coverage to `1.29` through `1.33`.
- `0.31.0` moved defaults to Vault `1.20.4` and changed the CSI provider directory default to `/var/run/secrets-store-csi-providers`.
- `0.32.0` adds OpenShift service-ca automation, ServiceMonitor target-service configuration, and fixes network policy namespace rendering plus volume claim template declarative parameters.

## Impact

Track C chart files should use dependency version `0.32.0` and app version `1.21.2`. Local kind/E2E presets must dry-run the rendered chart before install because HashiCorp still labels the chart as under active development and recommends `--dry-run` before install or upgrade.
