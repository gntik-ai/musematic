# SC Verification Record — UPD-040

Date: 2026-04-30

This record captures the local verification sweep completed during implementation. Cluster-live measurements that require a running kind platform are marked pending rather than inferred.

| SC | Status | Measurement |
| --- | --- | --- |
| SC-001 | Pending cluster-live | Fresh `helm install` wall-clock measurement requires a clean kind cluster. |
| SC-002 | Verified locally | `helm template` rendered platform + Vault chart values for `controlPlane.vault.mode=vault`; Vault chart rendered with `values-dev.yaml`. |
| SC-003 | Verified locally | `git grep "VaultResolver" apps/control-plane/src/platform` only leaves the legacy implementation boundary; secret callsites use `SecretProvider`. |
| SC-004 | Verified locally | Go shared interface exists at `services/shared/secrets/provider.go`; `go test ./...` passed in `services/shared/secrets`. |
| SC-005 | Verified locally | `python scripts/check-secret-access.py` passed; synthetic tests cover forbidden Python/Go secret env reads. |
| SC-006 | Partially verified | Unit coverage verifies stale read fallback and critical read refusal in `test_vault_secret_provider.py`; network partition timing remains cluster-live. |
| SC-007 | Pending cluster-live | Alert rule `VaultUnreachable` renders; live firing within 60s requires Prometheus in kind. |
| SC-008 | Verified locally | Python and Go canonical path validators reject non-canonical paths; `_internal/connectivity-test` is limited to admin probes. |
| SC-009 | Partially verified | Renewal loop and SIGTERM revoke exist in Python/Go clients; 24-hour lease test is pending. |
| SC-010 | Pending cluster-live | Cache-hit ratio target requires live traffic and Prometheus measurement. |
| SC-011 | Partially verified | KV v2 version tests and E2E suite are present; live audit/log capture is pending. |
| SC-012 | Partially verified | Migration manifest and idempotency tests exist; live rerun against kind is pending. |
| SC-013 | Verified locally | Vault `dev`, `standalone`, and `ha` value presets exist and chart dependencies render. |
| SC-014 | Partially verified | Policy files are committed per bounded context; least-privilege review remains a BC-owner review item. |
| SC-015 | Documented | Operator/developer docs describe KV v2 and optional Database/Transit/PKI follow-up hooks. |
| SC-016 | Partially verified | Metrics are implemented in Python/Go and dashboard JSON renders; live scrape per pod is pending. |
| SC-017 | Verified locally | OpenAPI contains `/api/v1/admin/vault/{status,cache-flush,connectivity-test}`; `scripts/check-admin-role-gates.py` passed. |
| SC-018 | Partially verified | `platform-cli vault verify-migration` exists; rollback is documented as `PLATFORM_VAULT_MODE=kubernetes`. |
| SC-019 | Verified locally | `scripts/generate-env-docs.py` classifies `PLATFORM_VAULT_TOKEN` and SecretID-related refs as sensitive. |
| SC-020 | Verified locally | `test_mock_mode_regression.py` exists and the focused MockSecretProvider unit tests passed. |

Local commands run:

```bash
python scripts/check-secret-access.py
python scripts/check-admin-role-gates.py
apps/control-plane/.venv/bin/python -m pytest apps/control-plane/tests/common/test_vault_secret_provider.py scripts/tests/test_check_admin_role_gates.py -q
GOMODCACHE=/tmp/go-mod-cache GOPATH=/tmp/go GOCACHE=/tmp/go-build-cache go test ./...
HELM_CONFIG_HOME=/tmp/helm-config HELM_CACHE_HOME=/tmp/helm-cache HELM_DATA_HOME=/tmp/helm-data helm template observability deploy/helm/observability --namespace platform-observability
PYTHONPATH=tests/e2e python -m pytest tests/e2e/suites/secrets --collect-only -q
```

Unrun local prerequisites:

- `promtool` is not installed in this environment, so `promtool check rules deploy/helm/observability/templates/alerts/vault.yaml` remains pending.
- No kind cluster or Grafana instance is running in this workspace, so live alert/dashboard checks remain pending.
