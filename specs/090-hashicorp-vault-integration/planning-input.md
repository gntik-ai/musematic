# UPD-040 — HashiCorp Vault Integration

## Brownfield Context

**Current state (verified in repo):**
- The codebase has a `VaultResolver` class at `apps/control-plane/src/platform/connectors/security.py` that implements **only a `mock` mode** (file + env-var fallback for development).
- Config has `vault_mode: Literal["mock", "vault"] = "mock"` but the `vault` mode raises `CredentialUnavailableError` when invoked — it is a placeholder.
- OAuth providers store `client_secret_ref` in the DB pointing to a future vault path; the resolution path has no real Vault implementation.
- Several prior specs reference "vault" aspirationally (UPD-024 secret rotation, UPD-020 OAuth, feature 013 secrets-injection). These references assume a real Vault exists eventually.
- No Vault sub-chart in `deploy/helm/`.
- No Vault-related environment variables defined.

**Extends:**
- Feature 013 Secrets Injection (established `VaultResolver` interface and `vault_mode` setting).
- UPD-019 Generic S3 Storage (same pattern of provider-abstracted backend).
- UPD-024 Security Compliance & Supply Chain (secret rotation integration).
- UPD-020 OAuth Providers (the primary consumers of vault-stored client secrets).
- UPD-035 Observability Helm Bundle (Vault metrics and audit log integration).
- UPD-036 Administrator Workbench (new `/admin/security/vault` page).

**FRs:** FR-621 through FR-638 (section 113 of the FR document).

---

## Summary

UPD-040 elevates HashiCorp Vault from a placeholder config option to a first-class, production-ready secret backend. It fills in the `vault` mode of `VaultResolver`, adds a `kubernetes` transitional mode for existing deployments, ships an optional Helm sub-chart for in-cluster Vault, supports three authentication methods (Kubernetes, AppRole, Token), uses KV v2 + database + transit + PKI secret engines where applicable, and wires Vault into secret rotation (UPD-024), OAuth (UPD-020 / UPD-041), logging (UPD-034), audit chain (UPD-024), and admin workbench (UPD-036).

The feature explicitly includes a **migration path** from Kubernetes Secrets to Vault via a CLI command, so existing installations can adopt Vault without a full reinstall.

---

## User Scenarios

### User Story 1 — Production operator installs Musematic with HA Vault (Priority: P1)

An operator deploys Musematic to production on Hetzner per the UPD-039 installation guide. They want Vault as the secret backend with HA Raft storage (3 replicas).

**Independent Test:** Install the platform with `vault.mode=ha`, verify Vault pods reach healthy state, verify the control plane successfully authenticates to Vault via Kubernetes auth, verify a test secret can be written and read.

**Acceptance:**
1. `helm install platform` with Vault HA values creates 3 Vault pods.
2. Vault pods initialize with auto-unseal (if configured) or the operator unseals manually with Shamir shares.
3. Control plane pod authenticates via Kubernetes auth using its ServiceAccount.
4. Control plane logs structured JSON entry `vault.authenticated` with token expiry.
5. A written secret at `secret/data/musematic/production/test/value` is readable within 1s.
6. Lease renewal occurs at 50% of token TTL; metrics reflect renewal success.
7. `/admin/security/vault` page shows status=green, auth=kubernetes, cache hit rate > 0 after warm-up.

### User Story 2 — Migrate from Kubernetes Secrets to Vault (Priority: P1)

An operator has been running the platform with Kubernetes Secrets (transitional `kubernetes` mode). They want to migrate to Vault without downtime.

**Independent Test:** Install Vault alongside the running platform, run `platform-cli vault migrate-from-k8s`, verify all secrets appear at canonical Vault paths, flip `PLATFORM_VAULT_MODE=vault`, verify platform continues operating.

**Acceptance:**
1. Migration CLI reads all platform-owned Kubernetes Secrets.
2. CLI writes them to Vault at `secret/data/musematic/{env}/{domain}/{resource}` paths per FR-626.
3. CLI produces a migration report listing source secret → destination path → success/failure.
4. Idempotent — re-running migrates only missing items.
5. After cutover (`PLATFORM_VAULT_MODE=vault`), zero auth/login failures observed.
6. Kubernetes Secrets remain in place (operator removes them manually post-validation).
7. Rollback procedure documented: flip back to `PLATFORM_VAULT_MODE=kubernetes` and the platform resumes reading from K8s.

### User Story 3 — Model provider secret rotation via Vault (Priority: P2)

The security compliance feature (UPD-024) schedules a rotation of the OpenAI API key. Rotation happens through Vault with a dual-credential window.

**Independent Test:** Trigger rotation for the OpenAI API key. Verify new secret is written as a new Vault version. Verify executions in flight continue using the old version until cache expiry, then smoothly transition to the new version. Verify old version is destroyed after the dual-credential window.

**Acceptance:**
1. Rotation request invokes `vault kv put` with the new API key value.
2. KV v2 versioning retains both versions for the dual-credential window duration.
3. Platform reads show the new version after cache TTL expiry (default 60s).
4. Old version is destroyed via `vault kv metadata delete` after the configured window.
5. Audit chain entry records rotation with non-secret metadata only (no key value in any log).

### User Story 4 — Super admin verifies Vault status (Priority: P2)

A super admin opens `/admin/security/vault` to verify the Vault integration is healthy during an incident.

**Independent Test:** Open the page and inspect status panels. Trigger a manual cache flush. Verify subsequent reads hit Vault directly.

**Acceptance:**
1. Page loads within 3s with connection status, auth method, token expiry, lease count, recent auth failures, per-BC read rates, cache hit rate.
2. Cache flush action emits audit entry and clears the pod-local cache.
3. Connectivity test verifies HTTP reachability, authentication, and a test KV read.
4. Recent auth failures link to Loki-filtered logs.

### User Story 5 — Vault unreachable; platform degrades gracefully (Priority: P1)

Vault becomes unreachable due to a network partition.

**Independent Test:** Kill network to Vault. Verify cached secrets continue serving reads. Verify writes fail safely. Verify login attempts fail with safe error (never bypass authentication). Verify alerts fire.

**Acceptance:**
1. Reads within cache TTL succeed.
2. Reads past cache TTL serve stale data up to configured maximum staleness (e.g., 300s).
3. Critical reads (authentication, OAuth callback) fail explicitly with error when Vault is unreachable and cache is cold.
4. No hardcoded credential fallback path exists.
5. `Vault unreachable` alert fires within 1 minute.
6. Post-recovery, cache repopulates lazily on next read.

---

### Edge Cases

- **Kubernetes auth token rotation during request**: ServiceAccount token changes every few hours; client must re-authenticate transparently.
- **AppRole SecretID expired during operation**: client detects 403, re-authenticates if a fresh SecretID is available (from secret-mounted file), fails otherwise with clear error.
- **Vault policy denies a path**: client receives 403, emits structured log entry, fails the operation. Never retries with a different path.
- **KV v2 version history exceeds max retention**: old versions auto-destroyed per Vault's own retention policy.
- **Vault audit log full / disk pressure on Vault side**: platform cannot write secrets; emit clear error; trigger alert.
- **Clock skew between Vault and platform**: token expiry calculations diverge; client refreshes more conservatively when skew detected via response headers.
- **Operator uses `token` auth in production**: constitution rule 10 blocks this; installer refuses to start unless `ALLOW_INSECURE=true` and `PLATFORM_ENVIRONMENT=dev`.

---

## Deployment Modes

### Mode: `mock` (existing, retained for dev)
File-backed resolver at `.vault-secrets.json` plus env-var fallback. No Vault pod. Used by kind, local development, CI for bounded-context tests that don't specifically exercise Vault integration.

### Mode: `kubernetes` (new, transitional)
Reads secrets from Kubernetes Secrets at paths matching the canonical scheme. Useful for operators who have not yet migrated. Still goes through the `SecretProvider` abstraction, preserving consistent error handling and caching.

### Mode: `vault` (new, production recommended)
Real HashiCorp Vault via `hvac` (Python) / `vault/api` (Go). Supports three auth methods: `kubernetes`, `approle`, `token`. Uses KV v2, optional database / transit / PKI engines.

---

## Helm Chart Additions

### Sub-chart: `deploy/helm/vault/`

Based on the official HashiCorp `vault` Helm chart (version-pinned), with platform-specific defaults:

```yaml
# deploy/helm/vault/values.yaml (defaults)
vault:
  server:
    ha:
      enabled: true
      replicas: 3
      raft:
        enabled: true
        setNodeId: true
    dataStorage:
      enabled: true
      size: 10Gi
      storageClass: longhorn
    extraEnvironmentVars:
      VAULT_CACERT: /vault/userconfig/tls/ca.crt
  ui:
    enabled: true
    serviceType: ClusterIP  # Exposed via platform ingress with SSO proxy
  injector:
    enabled: false  # Platform doesn't use Vault injector; uses hvac/vault-api clients
```

Three sizing presets:
- **dev** (`vault.mode=dev`, single pod, in-memory): for kind and quick demos.
- **standalone** (`vault.mode=standalone`, single pod with persistent storage): small production.
- **ha** (`vault.mode=ha`, 3 pods with Raft): production HA.

### Integration with platform chart

```yaml
# deploy/helm/platform/values.yaml (new section)
vault:
  mode: vault                     # mock | kubernetes | vault
  addr: http://vault.platform-security.svc.cluster.local:8200
  namespace: ""                   # Vault Enterprise
  caCertSecretRef:                # CA cert when Vault uses private TLS
    name: ""
    key: ""
  authMethod: kubernetes          # kubernetes | approle | token
  kubernetes:
    role: musematic-platform
    serviceAccountTokenPath: /var/run/secrets/tokens/vault-token
  approle:
    roleId: ""
    secretIdSecretRef:
      name: ""
      key: ""
  token: ""                       # dev/CI only
  kvMount: secret
  kvPrefix: "musematic/{environment}"
  cache:
    ttlSeconds: 60
    maxStalenessSeconds: 300
  retry:
    attempts: 3
    timeoutSeconds: 10
  leaseRenewalThreshold: 0.5
```

## SecretProvider Abstraction

A single abstraction wraps all three modes. Bounded contexts never call `VaultResolver` directly — they use `SecretProvider`.

```python
# apps/control-plane/src/platform/common/secret_provider.py
from typing import Protocol

class SecretProvider(Protocol):
    async def get(self, path: str, key: str = "value") -> str: ...
    async def put(self, path: str, values: dict[str, str]) -> None: ...
    async def delete_version(self, path: str, version: int) -> None: ...
    async def list_versions(self, path: str) -> list[int]: ...
    async def health_check(self) -> HealthStatus: ...

# Concrete implementations
class VaultSecretProvider: ...     # hvac-based
class KubernetesSecretProvider: ...  # K8s API-based
class MockSecretProvider: ...      # file-based (existing logic)
```

Go services use an equivalent interface:

```go
// services/shared/secrets/provider.go
type SecretProvider interface {
    Get(ctx context.Context, path, key string) (string, error)
    Put(ctx context.Context, path string, values map[string]string) error
    DeleteVersion(ctx context.Context, path string, version int) error
    ListVersions(ctx context.Context, path string) ([]int, error)
    HealthCheck(ctx context.Context) (*HealthStatus, error)
}
```

A CI check (per constitution rule 37) fails the build on any direct call to `os.getenv(...)` or `os.Getenv(...)` for a name matching known secret patterns (`*_SECRET`, `*_PASSWORD`, `*_API_KEY`, `*_TOKEN`) outside the `SecretProvider` implementation files.

## Vault Policies (HCL)

```hcl
# deploy/vault/policies/platform-auth.hcl
path "secret/data/musematic/+/oauth/*" {
  capabilities = ["read"]
}

path "secret/metadata/musematic/+/oauth/*" {
  capabilities = ["read", "list"]
}
```

```hcl
# deploy/vault/policies/platform-cost-governance.hcl
path "secret/data/musematic/+/model-providers/*" {
  capabilities = ["read"]
}
```

Policies attached to the `musematic-platform` Kubernetes auth role grant only the union of capabilities needed. Bounded-context-specific policies serve as the basis for future per-BC ServiceAccount separation.

## Acceptance Criteria

- [ ] `vault` mode in `VaultResolver` fully implemented (no placeholder raises).
- [ ] `kubernetes` mode added and operates against Kubernetes Secrets.
- [ ] `SecretProvider` abstraction in both Python and Go.
- [ ] CI check fails on direct env-var access for secret patterns outside the abstraction.
- [ ] Vault Helm sub-chart (3 presets: dev, standalone, ha) installable standalone.
- [ ] Auth methods `kubernetes`, `approle`, `token` all functional.
- [ ] KV v2 read/write/versioning/history verified end-to-end.
- [ ] Database secrets engine optionally configured with documented setup.
- [ ] Transit engine optionally used by audit chain sign/verify operations.
- [ ] Path scheme `secret/data/musematic/{env}/{domain}/{resource}` consistently applied.
- [ ] Env vars `PLATFORM_VAULT_*` all recognized with documented defaults.
- [ ] Token lifecycle: renewal at threshold, re-auth on revocation, lease revocation on SIGTERM.
- [ ] Client-side caching with 60s default TTL, flushable via admin action.
- [ ] Fail-safe behavior on Vault unreachability: stale reads, critical-path refusal, alert fires.
- [ ] Migration CLI `platform-cli vault migrate-from-k8s` functional and idempotent.
- [ ] Admin page `/admin/security/vault` shows status and controls.
- [ ] Secret rotation (UPD-024) integrates with Vault KV v2 versioning.
- [ ] Prometheus metrics for lease count, renewal rate, auth failures, read rate, cache hit rate exposed.
- [ ] E2E test infrastructure supports `vault` mode with an in-cluster dev Vault.
- [ ] Journey tests run in both `mock` and `vault` modes.
- [ ] Bounded-context suite `tests/e2e/suites/secrets/` covers reads, writes, rotations, failure handling.
- [ ] No regression in existing `mock` mode behavior.
