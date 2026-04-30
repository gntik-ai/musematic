# SC Verification Record — UPD-040

Date: 2026-04-30

This record captures the local verification sweep completed during implementation. Cluster-live measurements that require a running kind platform are marked pending rather than inferred.

| SC | Status | Measurement |
| --- | --- | --- |
| SC-001 | Pending cluster-live | Fresh `helm install` wall-clock measurement requires a clean kind cluster. |
| SC-002 | Verified locally | `helm template` rendered platform + Vault chart values for `controlPlane.vault.mode=vault`; Vault chart rendered with `values-dev.yaml`. |
| SC-003 | Verified locally | `git grep "VaultResolver" apps/control-plane/src/platform` only leaves the legacy implementation boundary; secret callsites use `SecretProvider`. |
| SC-004 | Verified locally | Go shared interface exists at `services/shared/secrets/provider.go`; `go test ./...` passed in `services/shared/secrets` and all four satellite Go modules. |
| SC-005 | Verified locally | `python scripts/check-secret-access.py` passed; synthetic tests cover forbidden Python/Go secret env reads. |
| SC-006 | Partially verified | Unit coverage verifies stale read fallback and critical read refusal in `test_vault_secret_provider.py`; network partition timing remains cluster-live. |
| SC-007 | Partially verified | Alert rule `VaultUnreachable` renders; rendered `spec.groups` passed `promtool check rules` with 4 rules found. Live firing within 60s requires Prometheus in kind. |
| SC-008 | Verified locally | Python and Go canonical path validators reject non-canonical paths; `_internal/connectivity-test` is limited to admin probes. |
| SC-009 | Partially verified | Renewal loop and SIGTERM revoke exist in Python/Go clients; 24-hour lease test is pending. |
| SC-010 | Pending cluster-live | Cache-hit ratio target requires live traffic and Prometheus measurement. |
| SC-011 | Partially verified | KV v2 version tests and E2E suite are present; live audit/log capture is pending. |
| SC-012 | Partially verified | Migration manifest and idempotency tests exist; live rerun against kind is pending. |
| SC-013 | Verified locally | Vault `dev`, `standalone`, and `ha` value presets exist and chart dependencies render. |
| SC-014 | Partially verified | Policy files are committed per bounded context; least-privilege review remains a BC-owner review item. |
| SC-015 | Documented | Operator/developer docs describe KV v2 and optional Database/Transit/PKI follow-up hooks. |
| SC-016 | Partially verified | Metrics are implemented in Python/Go; dashboard JSON is valid with 8 panels and renders as chart data. Live Grafana load and scrape per pod are pending. |
| SC-017 | Verified locally | OpenAPI contains `/api/v1/admin/vault/{status,cache-flush,connectivity-test}`; `scripts/check-admin-role-gates.py` passed. |
| SC-018 | Partially verified | `platform-cli vault verify-migration` exists; rollback is documented as `PLATFORM_VAULT_MODE=kubernetes`. |
| SC-019 | Verified locally | `scripts/generate-env-docs.py` classifies `PLATFORM_VAULT_TOKEN` and SecretID-related refs as sensitive. |
| SC-020 | Verified locally | `test_mock_mode_regression.py` exists and the focused MockSecretProvider unit tests passed. |

Local commands run:

```bash
python scripts/check-secret-access.py
python scripts/check-admin-role-gates.py
apps/control-plane/.venv/bin/python -m pytest apps/control-plane/tests/common/test_vault_secret_provider.py scripts/tests/test_check_admin_role_gates.py -q
apps/control-plane/.venv/bin/python -m pytest apps/control-plane/
apps/ops-cli/.venv/bin/python -m pytest apps/ops-cli/tests/commands/test_vault.py
GOMODCACHE=/tmp/go-mod-cache GOPATH=/tmp/go GOCACHE=/tmp/go-build-cache go test ./...  # run from services/shared/secrets
GOMODCACHE=/tmp/go-mod-cache GOPATH=/tmp/go GOCACHE=/tmp/go-build-cache go test ./...  # run from services/runtime-controller
GOMODCACHE=/tmp/go-mod-cache GOPATH=/tmp/go GOCACHE=/tmp/go-build-cache go test ./...  # run from services/reasoning-engine
GOMODCACHE=/tmp/go-mod-cache GOPATH=/tmp/go GOCACHE=/tmp/go-build-cache go test ./...  # run from services/simulation-controller
GOMODCACHE=/tmp/go-mod-cache GOPATH=/tmp/go GOCACHE=/tmp/go-build-cache go test ./...  # run from services/sandbox-manager
HELM_CONFIG_HOME=/tmp/helm-config HELM_CACHE_HOME=/tmp/helm-cache HELM_DATA_HOME=/tmp/helm-data helm template observability deploy/helm/observability --namespace platform-observability
helm template observability deploy/helm/observability --namespace platform-observability --show-only templates/alerts/vault.yaml > /tmp/musematic-vault-alert.yaml
awk '/^  groups:/{emit=1} emit{sub(/^  /, ""); print}' /tmp/musematic-vault-alert.yaml > /tmp/musematic-vault-prom-rules.yaml
docker run --rm --entrypoint /bin/promtool -v /tmp:/tmp -w /tmp prom/prometheus:v2.55.1 check rules /tmp/musematic-vault-prom-rules.yaml
jq empty deploy/helm/observability/dashboards/vault-overview.json
PYTHONPATH=tests/e2e python -m pytest tests/e2e/suites/secrets --collect-only -q
```

Blocked commands attempted:

```bash
go test ./services/...
PYTHONPATH=tests/e2e python -m pytest tests/e2e/suites/secrets/
kubectl cluster-info
curl -fsS http://localhost:3000/api/health
curl -fsS http://localhost:8081/health
```

Results:

- `go test ./services/...` is not valid from the repository root because there is no root `go.mod`; each service module was tested directly instead.
- The full secrets E2E suite collected 34 tests, then failed at the shared login fixture because the platform API at `http://localhost:8081` was not running.
- `kubectl cluster-info` could not reach a Kubernetes API server, Grafana at `localhost:3000` was unavailable, and the platform API at `localhost:8081` was unavailable.

Unrun local prerequisites:

- No kind cluster, Grafana instance, platform API, matrix-CI runner, or 24-hour log-capture job is running in this workspace, so live alert/dashboard/E2E/matrix checks remain pending.
