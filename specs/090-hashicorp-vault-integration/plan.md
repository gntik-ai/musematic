# Implementation Plan: UPD-040 — HashiCorp Vault Integration

**Branch**: `090-hashicorp-vault-integration` | **Date**: 2026-04-27 | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

## Summary

UPD-040 fills the placeholder `vault` mode of the existing `VaultResolver` at `apps/control-plane/src/platform/connectors/security.py:51-82` (today only `mock` mode works; `vault` mode raises `CredentialUnavailableError`) with a real HashiCorp Vault integration, AND consolidates the secret-resolution path behind a single `SecretProvider` abstraction. Five parallelizable tracks converge for the bounded-context-suite + journey + matrix-CI verification:

- **Track A — `SecretProvider` consolidation** (~3 dev-days; **keystone — blocks B/D/E**): Promotes the existing `SecretProvider` Protocol from `notifications/channel_router.py:45-48` to `apps/control-plane/src/platform/common/secret_provider.py`; normalizes the method names from `read_secret`/`write_secret` to `get`/`put`/`delete_version`/`list_versions`/`health_check` per spec correction §3a; rewires the existing 6 callsites of `RotatableSecretProvider` (UPD-024 — verified) and the 5 per-BC `*_secret_ref` resolution paths (auth/OAuth, auth/IBOR, notifications×2, model_catalog) onto the consolidated Protocol; adds a Go-side mirror at `services/shared/secrets/provider.go`; adds the FR-687 CI deny-list check at `scripts/check-secret-access.py`.
- **Track B — Vault client implementations** (~4 dev-days; can start mid-Track-A once Protocol is finalized): Implements `VaultSecretProvider` (Python via `hvac>=2.3.0`; Go via `github.com/hashicorp/vault/api`); implements `KubernetesSecretProvider` (transitional mode via `kubernetes-asyncio` Python and `client-go` Go); refactors the existing `MockSecretProvider` extraction from `VaultResolver._resolve_mock` (no behavioural change); implements 3 auth methods (kubernetes/approle/token), token lifecycle (renewal + revocation + SIGTERM-clean-shutdown), per-pod LRU cache with TTL + max-staleness, fail-safe degradation per FR-688.
- **Track C — Vault Helm sub-chart** (~2 dev-days; **fully independent — can start day 1**): NEW `deploy/helm/vault/` wrapping the upstream `hashicorp/vault` chart (modeled on the existing `deploy/helm/qdrant/Chart.yaml` precedent); 3 sizing presets (`dev` / `standalone` / `ha`); commits the canonical 7 BC policies under `deploy/vault/policies/*.hcl` per FR-695; integrates Vault into the unified observability bundle from feature 085 / UPD-035 for unified install.
- **Track D — Migration tooling** (~2 dev-days; depends on Track B Phase 1): NEW `platform-cli vault` Typer sub-app at `apps/ops-cli/src/platform_cli/commands/vault.py` (modeled on existing `commands/backup.py` precedent — verified) with subcommands `migrate-from-k8s`, `verify-migration`, `status`, `flush-cache`, `rotate-token`. Idempotent, dry-run-by-default, manifest-emitting (SHA-256 only — no plaintext per Rule 31), one-way (rollback via mode-flag flip — never deletes Kubernetes Secrets).
- **Track E — Admin contracts + observability** (~2 dev-days; depends on Track A + B): 3 new admin endpoints under `/api/v1/admin/vault/*` (`GET /status`, `POST /cache-flush`, `POST /connectivity-test`) consumed by feature 086 (UPD-036) `/admin/security/vault` UI page; emits Prometheus metrics per FR-697 (11 metrics); commits a NEW `deploy/helm/observability/templates/alerts/vault.yaml` with 4 alert rules (`VaultUnreachable`, `VaultAuthFailureRate`, `VaultLeaseRenewalFailing`, `VaultStalenessHigh`) modeled on the existing 6 alert files (verified at `deploy/helm/observability/templates/alerts/{execution,kafka,reasoning,loki,service,fleet}-alerts.yaml`); commits a NEW Grafana dashboard `vault-overview.json`.
- **Phase 6 — E2E coverage + matrix CI** (~2 dev-days; convergent — depends on A+B+C+D+E): New `tests/e2e/suites/secrets/` directory with 8 tests (round-trip / kubernetes-mode / mock-mode-regression / migration / rotation / unreachable / kubernetes-auth / approle-auth); extends `tests/e2e/cluster/kind-config.yaml` (verified — current contents have 5 port mappings) with a Vault dev-mode pod port mapping; matrix-CI runs the J01 (Administrator) + J11 (Security Officer) journey suites against `mock` / `kubernetes` / `vault` modes to catch mode-specific regressions per spec SC-020.

The five tracks converge on day 8 for journey-suite verification; the feature lands on day 12 wall-clock with 2-3 devs working in parallel. **Effort estimate: 15-17 dev-days** (the brownfield's "10 days (9 points)" is understated — the migration tooling, the 7 per-BC policy authoring, the Go-side mirror, and the matrix-CI verification add ~5-7 days of work the brownfield doesn't account for; this plan corrects the estimate consistent with the v1.3.0 cohort's pattern of brownfield-understated estimates).

## Constitutional Anchors

This plan is bounded by the following Constitution articles + FRs. Each implementation step below cites the article it serves.

| Anchor | Citation | Implementation tie |
|---|---|---|
| **UPD-040 declared** | Constitution audit-pass roster | The whole feature |
| **Rule 10 — Every credential goes through vault** | `.specify/memory/constitution.md:123-126` | Track A consolidates secret resolution; Track B implements the real `vault` mode; FR-688 fail-safe behaviour ensures Vault outage NEVER bypasses authentication |
| **Rule 30 — Every admin endpoint role-gated** | `.specify/memory/constitution.md:198-202` | Track E's 3 new `/api/v1/admin/vault/*` endpoints depend on `require_superadmin` per FR-698 |
| **Rule 31 — Super-admin bootstrap never logs secrets** | `.specify/memory/constitution.md:204-212` | Track D's migration manifest emits SHA-256 only (NEVER plaintext); Track B's structured-log discipline (no token / SecretID / KV-value in any log entry) per FR-700 |
| **Rule 37 — Env vars / Helm values / feature flags auto-documented** | `.specify/memory/constitution.md:228-231` | Track A's FR-687 CI deny-list check extends UPD-039's `scripts/generate-env-docs.py`; new `PLATFORM_VAULT_*` env vars flow through UPD-039's auto-doc pipeline per FR-700 |
| **Constitution Rule 41** | `.specify/memory/constitution.md` (highest defined per research R11) | Indirect — UPD-040 does not introduce UI; the audit-page (UPD-036's `/admin/security/vault`) inherits Rule 41's WCAG AA discipline from UPD-036 |
| **FR-683 — `vault` deployment mode** | spec FR-683 (NEW; section 113 appended after FR-682) | Track A + Track B Phase 1 + Phase 2 |
| **FR-684 — Three auth methods** | spec FR-684 | Track B Phase 1 (Python) + Phase 2 (Go) |
| **FR-685 — `SecretProvider` Protocol consolidation** | spec FR-685 | Track A — entire scope |
| **FR-686 — Go-side `SecretProvider` interface** | spec FR-686 | Track A Phase 4 (Go mirror) |
| **FR-687 — CI deny-list for direct secret-pattern env-var access** | spec FR-687 | Track A Phase 5 |
| **FR-688 — Fail-safe behaviour on Vault unreachability** | spec FR-688 | Track B Phase 1 (cache + stale-read + critical-path-refusal); Track E (alert rule `VaultUnreachable`) |
| **FR-689 — Canonical KV v2 path scheme** | spec FR-689 | Track A defines the scheme; Track D enforces it during migration |
| **FR-690 — Token lifecycle** | spec FR-690 | Track B Phase 1 (Python renewal loop); Phase 2 (Go renewal loop) |
| **FR-691 — Per-pod cache** | spec FR-691 | Track B Phase 1 (Python LRU); Phase 2 (Go `sync.Map` + TTL); flush trigger via Track D `platform-cli vault flush-cache` AND Track E admin endpoint |
| **FR-692 — Rotation via KV v2 versioning** | spec FR-692 | Track A (`RotatableSecretProvider` rewire — preserve `get_current` / `get_previous` / `validate_either` / `cache_rotation_state` per research R1); Track B (KV v2 implementation) |
| **FR-693 — Migration tool** | spec FR-693 | Track D — entire scope |
| **FR-694 — Helm sub-chart with 3 sizing presets** | spec FR-694 | Track C — entire scope |
| **FR-695 — Per-BC Vault policies** | spec FR-695 | Track C — `deploy/vault/policies/*.hcl` (7 files) |
| **FR-696 — Optional Database / Transit / PKI engines** | spec FR-696 | Track C ships docs only; not part of MVP |
| **FR-697 — 11 Prometheus metrics** | spec FR-697 | Track B Phase 1 + Phase 2 emit metrics; Track E commits Grafana dashboard |
| **FR-698 — Admin page backend contracts** | spec FR-698 | Track E — entire scope |
| **FR-699 — Migration manifest verifiability + rollback** | spec FR-699 | Track D `verify-migration` subcommand |
| **FR-700 — Env-var classification: `sensitive`** | spec FR-700 | Track A's `VaultSettings` config; auto-flowed through UPD-039's FR-610 reference |

**Verdict: gate passes. No declared variances.** UPD-040 satisfies all four constitutional rules (10, 30, 31, 37) governing credential handling. Brownfield's reference to constitution Rule 10 (token auth blocked in production) is honoured by the startup-check at FR-684.

## Technical Context

| Item | Value |
|---|---|
| **Languages** | Python 3.12 (control plane — adds `hvac>=2.3.0`); Go 1.22 (4 satellites: runtime-controller, reasoning-engine, simulation-controller, sandbox-manager — each adds `github.com/hashicorp/vault/api` per spec correction §7); YAML (Helm chart values + Prometheus alert rules + Grafana dashboard JSON); HCL (Vault policies — 7 files at `deploy/vault/policies/*.hcl`); TypeScript 5.x (Next.js — UI page owned by feature 086 / UPD-036; UPD-040 only contributes the backend API contracts). |
| **Primary Dependencies (existing — reused)** | `pydantic-settings 2.x` (`BaseSettings` per `common/config.py` — env-prefix discipline; new `VaultSettings` block follows the existing `ConnectorsSettings` pattern with `env_prefix="VAULT_"` resolved to `PLATFORM_VAULT_*` via the parent `PlatformSettings.model_config = SettingsConfigDict(env_prefix="PLATFORM_")`); `aiokafka 0.11+` (broadcasts cluster-wide cache-flush events on `platform.events` topic — out of scope for MVP per spec assumptions); `redis-py 5.x async` (rotation-state cache via existing `RotatableSecretProvider`); `kubernetes-asyncio` (existing — Track B Phase 3 K8s mode); `prometheus-client` (metrics emission); structlog (UPD-084 logging discipline); `aioboto3` (NOT for Vault — UPD-040 has no S3 dependency, but the abstraction is modeled on UPD-019's `AsyncObjectStorageClient` pattern at `common/clients/object_storage.py:37-50`). |
| **Primary Dependencies (NEW in 090)** | Python: `hvac>=2.3.0` (HashiCorp Vault Python client — MPL 2.0). Go: `github.com/hashicorp/vault/api` v1.15.0+ in 4 satellite `go.mod` files. Helm: `hashicorp/vault` chart v0.30.0+ (pin determined during T030 — see Phase 0 R6) declared as `dependencies:` in `deploy/helm/vault/Chart.yaml` per the precedent at `deploy/helm/qdrant/Chart.yaml`. Container images: `hashicorp/vault:1.18.x` (LTS; pin during T030). |
| **Storage** | Vault: per-replica `dataStorage.size: 10Gi` PVC for Raft data + audit log device (per the upstream chart's defaults, retained). PostgreSQL: NO new tables (all secret references already have columns per research R2 — `OAuthProvider.client_secret_ref`, `ChannelConfig.signing_secret_ref` (nullable), `OutboundWebhook.signing_secret_ref` (required), `ModelProviderCredential.vault_ref`, `IBORConnector.credential_ref`). Redis: NO new key namespaces (the existing `rotation_state:*` keys from `RotatableSecretProvider` are preserved). MinIO: NO buckets. |
| **Testing** | `pytest 8.x` + `pytest-asyncio` (control plane); Go: `go test`; E2E: 8 new test files at `tests/e2e/suites/secrets/test_*.py` (modeled on the existing 3-file precedent at `tests/e2e/suites/cost_governance/` — verified per research R9); kind cluster extension at `tests/e2e/cluster/kind-config.yaml` adds Vault dev-mode pod (current config has 5 port mappings: 30080-30084 — verified per research R10; UPD-040 adds 30085 for Vault). Matrix-CI variant runs the existing J01 (Administrator) + J11 (Security Officer) journey tests against all 3 modes (`mock`, `kubernetes`, `vault`) to catch mode-specific regressions. |
| **Target Platform** | Linux x86_64 (Kubernetes 1.28+ control plane + worker nodes). Vault HA mode requires 3 nodes (constraint per Raft consensus minimum). Auto-unseal options documented but operator-chosen (cloud KMS / Transit / Shamir manual). The `dev` preset works on kind for E2E and local; the `ha` preset is the production path. |
| **Project Type** | Distributed system feature — touches: (a) the Python control plane (`apps/control-plane/`); (b) 4 Go satellites (`services/{runtime-controller,reasoning-engine,simulation-controller,sandbox-manager}/`); (c) the Helm chart layout (`deploy/helm/vault/` NEW + `deploy/helm/platform/values.yaml` extended + `deploy/helm/observability/templates/alerts/vault.yaml` NEW); (d) the operator CLI (`apps/ops-cli/src/platform_cli/commands/vault.py` NEW); (e) the FR document (`docs/functional-requirements-revised-v6.md` — appends section 113 with FR-683-FR-700); (f) the docs site (`docs/operator-guide/runbooks/vault-rotation.md` etc. — owned by UPD-039 but deliverable in this feature if UPD-039 has not landed); (g) E2E test scaffolding (`tests/e2e/suites/secrets/`); (h) the admin REST API (3 new endpoints under `/api/v1/admin/vault/*`). |
| **Performance Goals** | Cache hit ≤ 5 ms p99 (in-process LRU lookup); Vault read ≤ 50 ms p95 on cache miss (intra-cluster gRPC-equivalent latency); token renewal MUST succeed at 50% TTL with ≤ 1 second wall-clock; cache hit ratio MUST reach ≥ 80% within 5 minutes of platform startup under typical traffic per SC-010; migration tool MUST complete a 100-secret migration in ≤ 30 seconds wall-clock (a single Vault `kv put` is ~5 ms locally). |
| **Constraints** | Rule 10 — no plaintext credentials in code/config/database/logs (CI-enforced via FR-687 deny-list check); Rule 31 — manifest emits SHA-256 only; FR-688 — no hardcoded fallback path on Vault unreachability (CI verification via code-search); FR-689 — canonical KV v2 path scheme is the ONLY allowed shape; FR-700 — `PLATFORM_VAULT_TOKEN`, `PLATFORM_VAULT_APPROLE_SECRET_ID` classified as `sensitive` per UPD-039 / FR-610 auto-doc (verified at build time). |
| **Scale / Scope** | Track A: 1 NEW Protocol module (Python) + 1 NEW Go interface package + 5 callsite refactors + 1 NEW CI script + 8 unit tests. Track B: 1 NEW `VaultSecretProvider` (~600 lines Python) + 1 NEW `VaultSecretProvider` (~500 lines Go × 4 satellites with shared internal package) + 1 refactored `MockSecretProvider` + 1 NEW `KubernetesSecretProvider` (~250 lines Python). Track C: 1 NEW Helm sub-chart wrapping upstream + 7 HCL policy files (~30 lines each = ~210 lines) + 3 preset values files + Helm post-install Job. Track D: 1 NEW Typer sub-app (~600 lines) + 5 subcommands. Track E: 3 NEW admin endpoints + 1 NEW Prometheus alert YAML (~60 lines) + 1 NEW Grafana dashboard JSON (~600 lines). Phase 6: 8 NEW E2E tests (~80 lines each = ~640 lines) + matrix-CI extension (~30 lines `.github/workflows/ci.yml` change). **Total: ~4500 lines of new Python + Go + YAML + HCL across ~50 NEW files + ~15 MODIFIED files.** |

## Constitution Check

> **GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.**

| Check | Verdict | Rationale |
|---|---|---|
| Brownfield rule — modifications respect existing repo discipline | ✅ Pass | UPD-040 (a) refactors the existing `VaultResolver` mock-mode logic into the new abstraction WITHOUT behavioural change (regression-tested per SC-020); (b) preserves the 5 existing per-BC `*_secret_ref` columns unchanged at the schema level; (c) preserves the existing `RotatableSecretProvider` (UPD-024) public method names per research R1; (d) extends, never replaces, the existing observability bundle. |
| Rule 10 — every credential goes through vault | ✅ Pass (CI-enforced) | FR-687's deny-list at `scripts/check-secret-access.py` fails any PR adding `os.getenv("*_API_KEY")` outside the `SecretProvider` implementation files; Track B's startup-check refuses `vault_auth_method=token` in production per FR-684. |
| Rule 30 — every admin endpoint role-gated | ✅ Pass | Track E's 3 new `/api/v1/admin/vault/*` endpoints all depend on `require_superadmin` (the existing dependency at `auth/services/dependencies.py`); a static-analysis check (added in T140) verifies. |
| Rule 31 — super-admin bootstrap never logs secrets | ✅ Pass | Track D's manifest emits `value_sha256` only; Track B's structured logger fields use a deny-list (`token`, `secret_id`, `kv_value`) — any code-review violation is a blocker. |
| Rule 37 — env vars / Helm values / feature flags auto-documented | ✅ Pass | UPD-039's auto-doc pipeline (FR-610 + FR-611) ingests the new `PLATFORM_VAULT_*` env vars + the new Helm values from `deploy/helm/vault/values.yaml` automatically; CI fails any PR that adds a new vault env var without regenerating the docs reference. |
| FR-683 — `vault` deployment mode | ✅ Pass | Tracks A + B Phase 1 + Phase 2 deliver the implementation; previously `_resolve_mock` raised `CredentialUnavailableError` for non-mock modes (`security.py:58`). |
| FR-685 — `SecretProvider` Protocol consolidation | ✅ Pass | Track A moves the existing Protocol from `notifications/channel_router.py:45-48` to `common/secret_provider.py`; the existing `RotatableSecretProvider` and `InMemorySecretProvider` are rewired per research R4. |
| FR-688 — Fail-safe degradation | ✅ Pass | Track B Phase 1 implements per-pod LRU + TTL + max-staleness + critical-path-refusal; Phase 6 E2E test `test_vault_unreachable.py` verifies under network partition. |

**Verdict: gate passes. No declared variances. UPD-040 satisfies all five constitutional rules (10, 30, 31, 37 + brownfield discipline) governing credential handling.**

## Project Structure

### Documentation (this feature)

```text
specs/090-hashicorp-vault-integration/
├── plan.md                # this file
├── spec.md
├── planning-input.md
└── tasks.md               # produced by /speckit.tasks (next phase)
```

### Source Code (repository root) — files this feature creates or modifies

```text
# === Track A — SecretProvider abstraction ===
apps/control-plane/src/platform/common/secret_provider.py            # NEW — canonical Protocol + 3 implementations + the Go-mirror docstring
apps/control-plane/src/platform/common/__init__.py                   # MODIFY — re-export `SecretProvider`
apps/control-plane/src/platform/connectors/security.py               # MODIFY — `VaultResolver._resolve_mock` extraction into `MockSecretProvider`; `vault` mode deferred to `VaultSecretProvider`
apps/control-plane/src/platform/notifications/channel_router.py      # MODIFY — re-export `SecretProvider` from new canonical home for one release; emit DeprecationWarning on import
apps/control-plane/src/platform/notifications/dependencies.py        # MODIFY — `InMemorySecretProvider` migrated to `get`/`put` method names
apps/control-plane/src/platform/security_compliance/providers/rotatable_secret_provider.py  # MODIFY — rewire onto consolidated SecretProvider; preserve all public method names per research R1
apps/control-plane/src/platform/auth/services/oauth_service.py       # MODIFY — `_resolve_secret` (lines 732-747) delegates to SecretProvider; line 604 callsite preserved
apps/control-plane/src/platform/notifications/dependencies.py        # MODIFY — already covered above
apps/control-plane/src/platform/model_catalog/services/credential_service.py  # MODIFY — `vault_ref` resolution flows through SecretProvider
apps/control-plane/src/platform/auth/services/ibor_service.py        # MODIFY (verify file path during T010) — `credential_ref` resolution flows through SecretProvider
services/shared/secrets/provider.go                                  # NEW — Go interface mirror per FR-686
services/shared/secrets/types.go                                     # NEW — `HealthStatus` + error taxonomy
scripts/check-secret-access.py                                       # NEW — CI deny-list for `os.getenv`/`os.Getenv` of secret-pattern names per FR-687
scripts/tests/test_check_secret_access.py                            # NEW — pytest tests for the CI script

# === Track B — Vault client implementations ===
apps/control-plane/src/platform/common/secret_provider.py            # MODIFY (continuation from Track A) — adds `VaultSecretProvider` + `KubernetesSecretProvider`
apps/control-plane/src/platform/common/config.py                     # MODIFY — adds NEW `VaultSettings` block under `PlatformSettings`; deprecates `ConnectorsSettings.vault_mode` with DeprecationWarning
apps/control-plane/requirements.txt                                  # MODIFY — adds `hvac>=2.3.0`
apps/control-plane/pyproject.toml                                    # MODIFY (if present, per repo convention) — adds `hvac` to declared deps
services/runtime-controller/internal/vault/client.go                 # NEW — Go vault client wrapper
services/runtime-controller/internal/vault/auth.go                   # NEW — 3 auth methods (kubernetes, approle, token)
services/runtime-controller/internal/vault/cache.go                  # NEW — sync.Map + TTL
services/runtime-controller/internal/vault/metrics.go                # NEW — Prometheus emission
services/runtime-controller/go.mod                                   # MODIFY — adds vault/api dep
services/runtime-controller/go.sum                                   # MODIFY — vault/api transitive deps
services/reasoning-engine/internal/vault/                            # NEW — same structure as runtime-controller (or shared via services/shared/secrets/)
services/simulation-controller/internal/vault/                       # NEW
services/sandbox-manager/internal/vault/                             # NEW
# Note: A consolidation decision (per Phase 0 R7) determines whether the 4 satellites use a shared package at services/shared/secrets/ or each gets its own internal/vault/ — default is shared.

# === Track C — Vault Helm sub-chart ===
deploy/helm/vault/Chart.yaml                                          # NEW — wrapper modeled on deploy/helm/qdrant/Chart.yaml (research R6)
deploy/helm/vault/Chart.lock                                          # NEW — generated by `helm dep update`
deploy/helm/vault/values.yaml                                         # NEW — defaults (HA, Raft, 10Gi storage, injector disabled)
deploy/helm/vault/values-dev.yaml                                     # NEW — dev preset (1 pod, in-memory, no PVC)
deploy/helm/vault/values-standalone.yaml                              # NEW — standalone preset (1 pod, 10Gi PVC)
deploy/helm/vault/values-ha.yaml                                      # NEW — HA preset (3 pods, Raft)
deploy/helm/vault/templates/post-install-policies-job.yaml            # NEW — Job that runs `vault policy write` for each .hcl file
deploy/helm/vault/templates/post-install-kubernetes-auth-job.yaml     # NEW — Job that configures `auth/kubernetes/role/musematic-platform`
deploy/helm/vault/templates/networkpolicy.yaml                        # NEW — denies all ingress except from control plane + Go satellites
deploy/helm/vault/charts/                                             # NEW (generated by `helm dep update` — vendored upstream chart)
deploy/vault/policies/platform-auth.hcl                               # NEW — auth BC: oauth/* read; ibor/* read
deploy/vault/policies/platform-model-catalog.hcl                      # NEW — model_catalog BC: model-providers/* read
deploy/vault/policies/platform-notifications.hcl                      # NEW — notifications BC: webhook-secrets/* read; sms-providers/* read
deploy/vault/policies/platform-runtime.hcl                            # NEW — runtime BC: connectors/* read
deploy/vault/policies/platform-security-compliance.hcl                # NEW — security BC: audit-chain/* + transit/* (if Transit engine enabled)
deploy/vault/policies/platform-accounts.hcl                           # NEW — accounts BC: minimal (admin lifecycle + signup-rate-limit references)
deploy/vault/policies/platform-cost-governance.hcl                    # NEW — cost-governance BC: model-providers/* read (overlaps model_catalog by design)
deploy/helm/platform/values.yaml                                      # MODIFY — adds new `vault.*` block per spec correction §1; injects `PLATFORM_VAULT_*` env vars into control-plane Deployment
deploy/helm/platform/templates/deployment-control-plane.yaml          # MODIFY — adds projected SA token volume (for kubernetes auth) at `/var/run/secrets/tokens/vault-token`
deploy/helm/platform/templates/serviceaccount.yaml                    # MODIFY — annotates the platform ServiceAccount with the `auth/kubernetes/role/musematic-platform` binding

# === Track D — Migration tooling ===
apps/ops-cli/src/platform_cli/commands/vault.py                       # NEW — Typer sub-app modeled on commands/backup.py (research R7)
apps/ops-cli/src/platform_cli/main.py                                 # MODIFY — registers `vault_app` per the existing precedent at lines 72-78
apps/ops-cli/src/platform_cli/secrets/                                # NEW directory — migration helpers (path-mapping, manifest emitter, idempotency check)
apps/ops-cli/src/platform_cli/secrets/__init__.py                     # NEW
apps/ops-cli/src/platform_cli/secrets/migration.py                    # NEW — core migration logic
apps/ops-cli/src/platform_cli/secrets/manifest.py                     # NEW — JSON manifest emitter + verifier
apps/ops-cli/tests/commands/test_vault.py                             # NEW — pytest tests for the migration tool
docs/operator-guide/runbooks/vault-migration-from-k8s.md              # NEW — operator runbook (deliverable here if UPD-039's runbook library has not landed; otherwise UPD-039 owns)

# === Track E — Admin contracts + observability ===
apps/control-plane/src/platform/admin/routers/vault.py                # NEW — 3 admin endpoints
apps/control-plane/src/platform/admin/services/vault_admin_service.py # NEW — backing service (status aggregation, cache flush, connectivity test)
apps/control-plane/src/platform/admin/schemas/vault.py                # NEW — Pydantic schemas for the 3 endpoints
apps/control-plane/src/platform/main.py                               # MODIFY — registers the new `vault_admin_router` under `/api/v1/admin`
deploy/helm/observability/templates/alerts/vault.yaml                 # NEW — 4 alert rules; modeled on the existing 6 alert files (research R8)
deploy/helm/observability/dashboards/vault-overview.json              # NEW — Grafana dashboard JSON
docs/operator-guide/observability.md                                  # MODIFY — adds Vault overview panel description (deliverable here if UPD-039 has not landed)

# === Phase 6 — E2E coverage + matrix CI ===
tests/e2e/cluster/kind-config.yaml                                    # MODIFY — adds containerPort 30085 → hostPort for Vault dev-mode (research R10)
tests/e2e/suites/secrets/__init__.py                                  # NEW
tests/e2e/suites/secrets/conftest.py                                  # NEW — shared fixtures (vault dev pod, kubernetes mode mock, mock mode reset)
tests/e2e/suites/secrets/test_vault_round_trip.py                     # NEW — write/read/delete in vault mode
tests/e2e/suites/secrets/test_kubernetes_mode.py                      # NEW — K8s Secret backend
tests/e2e/suites/secrets/test_mock_mode_regression.py                 # NEW — preserves existing mock behaviour (SC-020)
tests/e2e/suites/secrets/test_migration_k8s_to_vault.py               # NEW — migration CLI dry-run + apply + idempotency
tests/e2e/suites/secrets/test_rotation_via_vault.py                   # NEW — UPD-024 rotation via KV v2 versioning
tests/e2e/suites/secrets/test_vault_unreachable.py                    # NEW — graceful degradation per FR-688
tests/e2e/suites/secrets/test_auth_method_kubernetes.py               # NEW — kubernetes auth path
tests/e2e/suites/secrets/test_auth_method_approle.py                  # NEW — approle auth path
.github/workflows/ci.yml                                              # MODIFY — adds matrix-CI job: `secret_mode: [mock, kubernetes, vault]` for J01 + J11 journey tests
docs/functional-requirements-revised-v6.md                            # MODIFY — appends section 113 (FR-683 through FR-700) per spec correction §6
```

**Structure decision**: UPD-040 follows the brownfield repo discipline established by UPD-019 (Generic S3) and UPD-024 (Security Compliance). The `SecretProvider` Protocol lives in `common/` (provider-agnostic), with concrete implementations co-located. Bounded contexts depend on the abstraction, NEVER on `VaultResolver` or `hvac` directly. The Go satellites share a `services/shared/secrets/` package to avoid duplicating the auth/cache/metrics logic across 4 services.

## Phase 0 — Research

> Research notes captured during plan authoring. Each item resolves a specific design question; the file paths cited are verified by the research agent (see research summary below). Items marked **[RESEARCH-COMPLETE]** are settled; items marked **[OPEN — DEFER TO IMPLEMENTATION]** are intentionally deferred to the implementation phase.

- **R1 — `RotatableSecretProvider` public method preservation [RESEARCH-COMPLETE]**: Verified at `apps/control-plane/src/platform/security_compliance/providers/rotatable_secret_provider.py`. Public methods to preserve: `get_current(secret_name) -> str` (line ~28), `get_previous(secret_name) -> str | None` (line ~43), `validate_either(secret_name, presented) -> bool` (line ~52), `cache_rotation_state(secret_name, state, *, ttl_seconds=60) -> None` (line ~62). Six callers identified: `model_catalog/dependencies.py:14`, `main.py:1648, 1658`, `security_compliance/dependencies.py:9, 64`, `security_compliance/services/secret_rotation_service.py:12, 22`, `multi_region_ops/dependencies.py:37, 66`, `incident_response/dependencies.py:27, 54`. **Resolution**: Track A's rewire preserves all 4 public method names; the internal `_read_secret` private method is replaced by a `SecretProvider.get()` call; `_cached` is replaced by the consolidated cache implementation in `VaultSecretProvider`. UPD-024 tests must pass unchanged.

- **R2 — Per-BC secret-reference inventory [RESEARCH-COMPLETE]**: 5 columns confirmed across 4 BCs: `auth.OAuthProvider.client_secret_ref` (auth/models.py:230, callsite at oauth_service.py:604), `notifications.ChannelConfig.signing_secret_ref` (notifications/models.py — nullable), `notifications.OutboundWebhook.signing_secret_ref` (notifications/models.py — required), `model_catalog.ModelProviderCredential.vault_ref` (model_catalog/models.py, callsite via `RotatableSecretProvider.get_current`), `auth.IBORConnector.credential_ref` (auth/models.py:176). **Resolution**: All 5 callsites flow through `SecretProvider.get()` after Track A; no schema changes; the column values themselves are unchanged. The migration tool (Track D) reads each column to determine source-K8s-Secret-name and destination-Vault-path mappings.

- **R3 — `oauth_service._resolve_secret` rewire [RESEARCH-COMPLETE]**: `auth/services/oauth_service.py:732-747` shows the existing fallback chain: (1) `self.credential_resolver(reference)` (an injected callable — used by tests); (2) `plain:` prefix shortcut; (3) env-var fallback `OAUTH_SECRET_*`; (4) returns the reference itself as the value (development fallback — DEPRECATED). **Resolution**: Track A REPLACES this 16-line function with a single delegation `return await self._secret_provider.get(reference)`; the `credential_resolver` constructor parameter is REMOVED (tests inject a `MockSecretProvider` instead — same shape). The `OAUTH_SECRET_*` env-var fallback is REMOVED in favour of the canonical scheme; existing deployments relying on `OAUTH_SECRET_*` env vars are migrated by `platform-cli vault migrate-from-k8s` per Track D.

- **R4 — `SecretProvider` Protocol existing implementations [RESEARCH-COMPLETE]**: 2 implementations exist today: `InMemorySecretProvider` at `notifications/dependencies.py:72-78` (no-op stub for tests) and `RotatableSecretProvider` at `security_compliance/providers/rotatable_secret_provider.py` (production rotation provider; does NOT explicitly inherit from Protocol but provides `get_current`/`get_previous` semantics). **Resolution**: Track A explicitly types both as `SecretProvider` implementations after the method-name normalization (R3a in spec); the rewired `RotatableSecretProvider` becomes a wrapper that maps `get_current` → `SecretProvider.get(path, key="current")` and `get_previous` → `SecretProvider.get(path, key="previous")`. KV v2 versioning replaces the bespoke 2-key (`current`/`previous`) value scheme with native version 1 / version 2 — see Phase 4 design.

- **R5 — `PlatformSettings` block insertion point [RESEARCH-COMPLETE]**: `common/config.py` defines `PlatformSettings(BaseSettings)` with `env_prefix="PLATFORM_"` at the parent level; nested config blocks include 28+ context-specific blocks (`db`, `redis`, `kafka`, ..., `connectors`, `security_compliance`). **Resolution**: New `vault: VaultSettings = Field(default_factory=VaultSettings)` is inserted alphabetically between `tagging: TaggingSettings` and `visibility: VisibilitySettings` (or wherever fits the existing alphabetic-ish convention; T020 confirms during implementation). `VaultSettings` uses `env_prefix="VAULT_"` resolved through the parent prefix → final env var names are `PLATFORM_VAULT_MODE`, `PLATFORM_VAULT_ADDR`, etc. Existing `ConnectorsSettings.vault_mode` becomes a deprecated alias: a Pydantic `model_validator` reads `CONNECTOR_VAULT_MODE`, copies to `PLATFORM_VAULT_MODE` if the latter is unset, emits a structured DeprecationWarning, and fails if both are set with conflicting values.

- **R6 — Helm wrapper sub-chart precedent [RESEARCH-COMPLETE]**: `deploy/helm/qdrant/Chart.yaml` shows the precedent — `dependencies:` block with `name: qdrant`, `repository: https://qdrant.github.io/qdrant-helm`, `version: "1.16.3"`. The wrapper passes values via the upstream chart's expected schema (e.g., `qdrant:` top-level key). **Resolution**: `deploy/helm/vault/Chart.yaml` declares `dependencies: [{name: vault, repository: https://helm.releases.hashicorp.com, version: 0.30.0}]`. The wrapper's `values.yaml` has a `vault:` top-level block matching the upstream chart's schema; UPD-040's 3 sizing presets are SEPARATE values files (`values-dev.yaml`, etc.) that override the defaults. Pinning to v0.30.0 is determined during T030 by checking the upstream release at the time of authoring and the supported `appVersion: 1.18.x` LTS.

- **R7 — Go satellite scope decision [RESEARCH-COMPLETE — DEFAULT TO SHARED]**: 4 Go satellites (runtime-controller, reasoning-engine, simulation-controller, sandbox-manager) consume connector / model-provider credentials via the gRPC bridge from the control plane. **Open question**: do the satellites need direct Vault access, or can the control plane resolve secrets and pass values via gRPC at runtime? **Resolution (default — SHARED PACKAGE)**: To avoid every satellite-to-control-plane gRPC round-trip leaking credential values across the wire, each satellite has direct Vault access via a SHARED Go package at `services/shared/secrets/` (vs. duplicated `internal/vault/` per-satellite). The decision is revisited during implementation if the gRPC-only path proves simpler; both are documented in T100. **Default for Phase 1**: shared package; satellites authenticate via their own ServiceAccount (each satellite's pod has a distinct SA — this requires per-satellite Vault Kubernetes auth roles per FR-695's deny-by-default discipline).

- **R8 — Prometheus alert rule placement [RESEARCH-COMPLETE]**: `deploy/helm/observability/templates/alerts/` contains 6 existing alert files (execution / kafka / reasoning / loki / service / fleet alerts). **Resolution**: Track E commits `vault.yaml` here as the 7th file; modelled on `service-alerts.yaml`'s structure (PrometheusRule kind, group `platform.vault`, 4 rules: `VaultUnreachable` for=1m / `VaultAuthFailureRate` for=5m / `VaultLeaseRenewalFailing` for=any / `VaultStalenessHigh` for=5m).

- **R9 — E2E suite directory precedent [RESEARCH-COMPLETE]**: `tests/e2e/suites/cost_governance/` contains 3 minimal pytest files (test_anomaly_alert_routes_to_admin.py, test_attribution_visible_during_run.py, test_hard_cap_blocks_then_override.py). The pattern is a single test function per file with assertion-style scenario validation (no async / no FastAPI client in the visible examples — but other suites likely use a richer fixture set). **Resolution**: Track Phase 6 commits 8 NEW pytest files at `tests/e2e/suites/secrets/` modeled on the cost_governance precedent; conftest.py adds shared fixtures: `vault_dev_pod` (kind cluster sidecar bringup), `kubernetes_secret_seed` (pre-populated K8s Secrets for migration test), `mock_mode_temp_file` (`.vault-secrets.json` test fixture). Each test asserts both behaviour and metrics emission per FR-697.

- **R10 — kind cluster config extension [RESEARCH-COMPLETE]**: `tests/e2e/cluster/kind-config.yaml` currently has 5 port mappings (30080-30084) on the control-plane node + 2 worker nodes. **Resolution**: Phase 6 adds containerPort 30085 → hostPort `${PORT_VAULT}` (a new envar in the existing port-mapping convention). Vault dev-mode runs as a Deployment in the `platform-security` namespace; the in-cluster service port 8200 is NodePort-exposed on 30085 for E2E direct-access from outside the cluster.

- **R11 — Constitutional rules verbatim [RESEARCH-COMPLETE]**: Rule 30 (`.specify/memory/constitution.md:198-202`): "Every admin endpoint declares a role gate. Every method in every `admin_router.py` module MUST depend on either `require_admin` or `require_superadmin`. A CI static-analysis check shall fail the build if any method is missing the gate." Rule 31 (`.specify/memory/constitution.md:204-212`): "Super-admin bootstrap never logs secrets. Code paths for `PLATFORM_SUPERADMIN_PASSWORD` / `PLATFORM_SUPERADMIN_PASSWORD_FILE` MUST be reviewed for logging. Structured logger fields containing these values are forbidden." **Resolution**: Track E's 3 admin endpoints depend on `require_superadmin`; T140 adds a static-analysis check verifying every `admin/routers/*.py` method uses one of the two gates; Track D's manifest-emitter discipline and Track B's structured-log discipline both honour Rule 31.

- **R12 — Cluster-wide cache flush [OPEN — DEFER TO IMPLEMENTATION]**: The spec proposes per-pod cache flush via `platform-cli vault flush-cache --pod=...` AND mentions optional cluster-wide flush via Kafka broadcast. Cluster-wide is OUT OF SCOPE for MVP per spec assumptions. **Resolution**: Track D ships per-pod-only flush; the Kafka-broadcast variant is documented as a known limitation; if a future operator hits the case, a follow-up enhancement adds the broadcast.

## Phase 1 — Design Decisions

> The following design decisions are pinned by this plan. Implementation tasks (in tasks.md) MUST honour these decisions or escalate via spec amendment.

### D1 — Method names: `get` / `put` / `delete_version` / `list_versions` / `health_check`

The existing Protocol uses `read_secret(path) -> dict[str, Any]` and `write_secret(path, payload)`. UPD-040 adopts the brownfield's signature (the hvac convention; aligns with KV v2's nested-key access). Migration is INTERNAL ONLY (no public API contract — these are Python protocols with limited callers). The 2 existing implementations (`InMemorySecretProvider`, `RotatableSecretProvider`) are migrated in T010-T030.

### D2 — Async-only Protocol surface

All `SecretProvider` methods are `async def`. The existing `MockSecretProvider` extraction from `_resolve_mock` (which is synchronous) wraps the synchronous file-read in an `asyncio.to_thread()` call to preserve the async interface. The Go interface at `services/shared/secrets/provider.go` uses `context.Context` + return values per Go convention; no goroutine-internal async.

### D3 — Per-pod LRU cache (NOT shared across pods)

The cache is in-process and per-pod. Cluster-wide flush is OUT OF SCOPE per Phase 0 R12. Each pod's cache fills lazily on first read and TTLs out per `PLATFORM_VAULT_CACHE_TTL_SECONDS` (default 60). Stale-read fallback is per-pod (independent staleness clocks).

### D4 — Path scheme is enforced at the SecretProvider boundary

`SecretProvider.get(path, key)` validates `path` matches the regex `^secret/data/musematic/(production|staging|dev|test|ci)/(oauth|model-providers|notifications|ibor|audit-chain|connectors|accounts)/[a-zA-Z0-9_/-]+$`. Non-conforming paths raise `InvalidVaultPathError` immediately (no Vault round-trip). The migration tool (Track D) emits manifest entries with `success=false, reason="invalid_path"` for any K8s Secret that cannot be mapped to a canonical path.

### D5 — KV v2 versioning replaces bespoke `current`/`previous` keys

`RotatableSecretProvider.get_current(secret_name)` becomes `SecretProvider.get(path).read_latest_version()` (hvac equivalent). `get_previous(secret_name)` reads version `latest_version - 1` if available. The bespoke `current`/`previous` two-key scheme in the existing rotation logic is REMOVED; existing rotation state in Redis (`rotation_state:*` keys) is migrated by Track D's `verify-migration` subcommand at the same time as the K8s Secret migration.

### D6 — Token auth refused in production

`VaultSettings.auth_method=token` MUST trigger a startup-error when `PLATFORM_ENVIRONMENT in {"production", "staging"}` AND `ALLOW_INSECURE != "true"` per Rule 10 + spec FR-684. The error message points at the operator runbook for AppRole bootstrap (delivered in Track D's runbook).

### D7 — Helm sub-chart depends on upstream `hashicorp/vault`

NOT a fork; a wrapper. Pinned to v0.30.0 (the latest stable LTS at the time of authoring; T030 verifies during plan-to-implementation handoff). Upgrade cadence: every 6 months OR on a critical CVE in the upstream.

### D8 — One-way migration

`platform-cli vault migrate-from-k8s` only writes; never modifies Kubernetes Secrets after the migration. Rollback is operator-driven mode-flag flip (`PLATFORM_VAULT_MODE=kubernetes`); the K8s Secrets remain in place until the operator deletes them manually post-validation.

### D9 — Per-BC ServiceAccount separation: PHASE-2 OPT-IN

For MVP, the entire platform authenticates as a single `musematic-platform` Kubernetes auth role (single SA: `platform-control-plane`). The 7 BC policies (`platform-auth.hcl`, etc.) are all attached to the same role; least-privilege at the role-level (a SINGLE role with the union of capabilities) NOT at the per-BC-ServiceAccount level. **Future hardening**: each BC's pods get a distinct SA + role + policy; the policies become the per-BC capability boundaries. This is documented as a known limitation; the spec's FR-695 deny-by-default discipline is satisfied at the role-policy level today.

### D10 — Brownfield-compatibility shim deprecation timeline

The existing `notifications/channel_router.py:45-48` `SecretProvider` Protocol is re-exported from `common/secret_provider.py` for ONE release (v1.3.0); imports must move to `common/secret_provider` by v1.4.0. CI emits a DeprecationWarning on import from the old path. Same applies to the deprecated `CONNECTOR_VAULT_MODE` env var.

## Phase 2 — Track A Build Order (SecretProvider abstraction)

**Days 1-3 (1 dev). Blocks Tracks B, D, E.**

1. **Day 1 morning** — Author the canonical `common/secret_provider.py`: Protocol, `MockSecretProvider`, `KubernetesSecretProvider` skeleton (real impl in Track B), error taxonomy (`CredentialUnavailableError` re-export from existing `connectors/security.py`, `CredentialPolicyDeniedError` NEW, `InvalidVaultPathError` NEW). Re-export from `notifications/channel_router.py` with DeprecationWarning.
2. **Day 1 afternoon** — Refactor `_resolve_mock` from `connectors/security.py` into `MockSecretProvider`; preserve byte-for-byte semantics; pinpoint regression test.
3. **Day 2 morning** — Rewire `oauth_service.py:_resolve_secret` (research R3); rewire `RotatableSecretProvider` (research R1) preserving all public method names; rewire `notifications/dependencies.py:InMemorySecretProvider` to new method names.
4. **Day 2 afternoon** — Migrate the remaining 3 callsites (research R2): `model_catalog/services/credential_service.py` (vault_ref resolution), `auth/services/ibor_service.py` (credential_ref resolution; verify file path), and any callsite the regression check turns up that R2 missed.
5. **Day 3 morning** — Author `services/shared/secrets/provider.go` Go interface mirror per FR-686; commit unit tests for the interface (no concrete impl yet — Track B Phase 2).
6. **Day 3 afternoon** — Author `scripts/check-secret-access.py` per FR-687 (deny-list of `os.getenv("*_API_KEY")` etc. outside SecretProvider implementation files); pytest unit tests at `scripts/tests/test_check_secret_access.py`; wire into CI as a new job in `ci.yml` per UPD-039's docs-staleness pattern. Day-3 acceptance: `pytest apps/control-plane/tests/` passes; the 6 callers of `RotatableSecretProvider` show no test regressions; `git grep "VaultResolver" apps/control-plane/src/platform/` returns zero matches outside `connectors/security.py` and `common/secret_provider.py`.

## Phase 3 — Track B Build Order (Vault client implementations)

**Days 4-7 (1 dev Python + 1 dev Go in parallel). Depends on Track A Phase 2 day 1.**

7. **Day 4 (Python)** — Author `VaultSecretProvider` core: hvac client construction; KV v2 read/write/delete-version/list-versions; canonical-path validation per D4.
8. **Day 4 (Go)** — Set up shared `services/shared/secrets/` Go package; declare `Client` struct + 5 interface methods.
9. **Day 5 (Python)** — Implement 3 auth methods: kubernetes (read SA token from `serviceAccountTokenPath`, call `/v1/auth/kubernetes/login`); approle (read RoleID from settings, SecretID from a mounted file path or settings); token (use `PLATFORM_VAULT_TOKEN` directly; refused in prod per D6); add startup-validation per D6.
10. **Day 5 (Go)** — Mirror 3 auth methods in Go.
11. **Day 6 (Python)** — Token lifecycle: background asyncio task renewing at 50% TTL (40% under detected clock skew per spec edge case); SIGTERM handler revoking the lease; lease accounting metric.
12. **Day 6 (Go)** — Mirror token lifecycle (background goroutine + signal.Notify SIGTERM).
13. **Day 6 afternoon (Python)** — Per-pod LRU cache: `cachetools.TTLCache` with size=1000, ttl=60s; max-staleness window via separate timestamp tracking; structured-log entry on stale-read fallback.
14. **Day 6 afternoon (Go)** — Per-pod cache: `sync.Map` + per-key `time.Time` for TTL/staleness tracking.
15. **Day 7 (Python)** — Prometheus metrics (FR-697 — 11 metrics); structured-log discipline (UPD-084 logger config; deny-list check on token / secret_id / kv_value fields).
16. **Day 7 (Go)** — Mirror metrics + structured-log discipline; verify shared package compiles into all 4 satellites without import cycles.
17. **Day 7 afternoon** — `KubernetesSecretProvider` real impl (Python only; Go satellites consume credentials via control plane gRPC in `kubernetes` mode — no Go-side K8s client required).

Day-7 acceptance: a kind cluster with `vault.mode=ha` (Track C deliverable) + 1 control-plane pod + 1 runtime-controller pod can: (a) authenticate via kubernetes auth; (b) read/write/version/delete a synthetic KV v2 path; (c) flush the cache via direct method call; (d) emit all 11 metrics to Prometheus; (e) log auth/renewal/critical-path events with no plaintext-secret leakage.

## Phase 4 — Track C Build Order (Vault Helm sub-chart)

**Days 1-2 (1 dev — fully independent — can start day 1 in parallel with Track A).**

18. **Day 1** — Create `deploy/helm/vault/Chart.yaml` modeled on `deploy/helm/qdrant/Chart.yaml`; declare upstream `hashicorp/vault` v0.30.0 dependency; run `helm dep update` to vendor the upstream chart under `deploy/helm/vault/charts/`.
19. **Day 1 afternoon** — Author 3 preset values files (`values-dev.yaml`, `values-standalone.yaml`, `values-ha.yaml`) per spec FR-694.
20. **Day 2 morning** — Author the post-install Job (`templates/post-install-policies-job.yaml`) that runs `vault policy write` for each `.hcl` file in `deploy/vault/policies/`; idempotent (uses `vault policy read | diff` before write).
21. **Day 2 morning** — Author the kubernetes-auth setup Job (`templates/post-install-kubernetes-auth-job.yaml`) that configures the `auth/kubernetes/role/musematic-platform` role; binds the platform ServiceAccount to all 7 BC policies per D9.
22. **Day 2 afternoon** — Author 7 HCL policy files (`platform-auth.hcl`, `platform-model-catalog.hcl`, `platform-notifications.hcl`, `platform-runtime.hcl`, `platform-security-compliance.hcl`, `platform-accounts.hcl`, `platform-cost-governance.hcl`); each grants minimal capabilities for the BC's actual reads (verified via the BC's `*_secret_ref` callsites from research R2).
23. **Day 2 afternoon** — Author `templates/networkpolicy.yaml` denying ingress to the Vault namespace except from the control-plane and 4 satellite namespaces.
24. **Day 2 afternoon** — Extend `deploy/helm/platform/values.yaml` with the new `vault.*` block per spec correction §1; extend `deploy/helm/platform/templates/deployment-control-plane.yaml` with the projected SA token volume; extend `deploy/helm/platform/templates/serviceaccount.yaml` with the auth/kubernetes binding annotation.

Day-2 acceptance: `helm install vault deploy/helm/vault/ --set mode=dev` brings up a single Vault dev pod on kind; `helm install platform deploy/helm/platform/ --set vault.mode=dev` configures the control plane to point at the dev pod; manual `vault kv put` + `vault kv get` succeeds against the dev pod from inside a control-plane shell.

## Phase 5 — Track D Build Order (Migration tooling)

**Days 6-7 (1 dev — depends on Track B Phase 1).**

25. **Day 6** — Author `apps/ops-cli/src/platform_cli/commands/vault.py` Typer sub-app per the precedent at `commands/backup.py` (research R7); register the sub-app in `main.py` per the existing `app.add_typer()` pattern at lines 72-78. Stub all 5 subcommands (`migrate-from-k8s`, `verify-migration`, `status`, `flush-cache`, `rotate-token`).
26. **Day 6 afternoon** — Author `secrets/migration.py` core logic: scan all platform namespaces; for each Secret matching the canonical-path-mirror naming convention (`musematic-{env}-{domain}-{resource}`), derive the destination Vault path; emit dry-run preview; on `--apply`, write to Vault using `VaultSecretProvider.put()` with CAS conflict handling.
27. **Day 7 morning** — Author `secrets/manifest.py`: JSON manifest emitter (columns per spec Key Entities); SHA-256-only (no plaintext per Rule 31); `verify-migration` subcommand re-reads each Vault path and compares SHA-256 against the manifest entry.
28. **Day 7 morning** — Idempotency: re-running `migrate-from-k8s` skips entries that already exist with matching SHA-256; reports `already_migrated_count`.
29. **Day 7 afternoon** — Author 3 utility subcommands: `status` (calls Track E's `GET /api/v1/admin/vault/status` endpoint via the existing platform CLI's HTTP-client utilities); `flush-cache` (calls Track E's `POST /cache-flush`); `rotate-token` (forces immediate token renewal; useful for incident response).
30. **Day 7 afternoon** — Author the operator runbook `docs/operator-guide/runbooks/vault-migration-from-k8s.md` (delivered here if UPD-039's runbook library has not landed; otherwise UPD-039 owns).

Day-7 acceptance: a kind cluster with N synthetic K8s Secrets matching the canonical scheme is migrated end-to-end; manifest verifies post-hoc; idempotency check passes; rollback (mode-flag flip) is documented + tested.

## Phase 6 — Track E Build Order (Admin contracts + observability)

**Days 6-7 (1 dev — depends on Track A + B).**

31. **Day 6** — Author `admin/routers/vault.py` with 3 endpoints (`GET /status`, `POST /cache-flush`, `POST /connectivity-test`); wire `require_superadmin` dependency per Rule 30.
32. **Day 6 afternoon** — Author `admin/services/vault_admin_service.py` aggregating: connection state from `VaultSecretProvider.health_check()`, auth method from settings, token expiry from the renewal-loop accountant, lease count from Vault `sys/leases/lookup`, recent auth failures from a ring buffer (size 10), per-BC read rates from Prometheus metric introspection (or via direct counter access), cache hit rate from Prometheus metric.
33. **Day 6 afternoon** — Audit-chain integration: `cache-flush` action emits a `vault.cache_flushed` audit entry via the existing UPD-024 audit-chain plumbing.
34. **Day 7 morning** — Author `admin/schemas/vault.py` Pydantic schemas; ensure no token / secret_id values appear in any response schema.
35. **Day 7 morning** — Author `deploy/helm/observability/templates/alerts/vault.yaml` modeled on `service-alerts.yaml` (research R8); 4 alert rules per spec Key Entities.
36. **Day 7 afternoon** — Author `deploy/helm/observability/dashboards/vault-overview.json` Grafana dashboard (panels: connection state, token expiry countdown, lease count, per-BC read rate, cache hit ratio, auth failure rate, staleness gauge, policy-denied counter).

Day-7 acceptance: `curl /api/v1/admin/vault/status` (with super-admin token) returns the full panel data; `curl /api/v1/admin/vault/cache-flush -X POST` flushes the calling pod's cache and emits an audit-chain entry; the Grafana dashboard renders with live data; the 4 Prometheus alert rules validate against the running cluster (`promtool check rules`).

## Phase 7 — E2E coverage + matrix CI (Phase 6 — convergent)

**Days 8-9 (1 dev — depends on all 5 tracks).**

37. **Day 8 morning** — Extend `tests/e2e/cluster/kind-config.yaml` per research R10 (add containerPort 30085 → hostPort `${PORT_VAULT}`); extend the kind bootstrap script to run `helm install vault deploy/helm/vault/ --set mode=dev` after the platform install.
38. **Day 8 morning** — Author `tests/e2e/suites/secrets/conftest.py` shared fixtures.
39. **Day 8 afternoon** — Author the 8 E2E test files per spec Key Entities; each file has 2-5 test functions; total ~640 lines of test code.
40. **Day 9 morning** — Extend `.github/workflows/ci.yml` with a matrix-CI job: `secret_mode: [mock, kubernetes, vault]`; runs the J01 (Administrator) and J11 (Security Officer) journey suites against each mode; failure in any mode fails the PR.
41. **Day 9 afternoon** — Verify all 20 spec SCs pass: SC-001 (HA install ≤ 30 min on a fresh cluster — verified on a real Hetzner cluster following the FR-608 guide if UPD-039's installation guide has landed; otherwise on kind); SC-002 through SC-020.
42. **Day 9 afternoon** — Publish a verification report under `specs/090-hashicorp-vault-integration/contracts/vault-install-verification.md` documenting the actual measurements against each SC.

Day-9 acceptance: full SC sweep passes; matrix CI green for all 3 modes; UPD-040 ready for merge.

## Phase 8 — Documentation polish + handoff

**Days 10-12 (1 dev — overlaps Phase 7 days 8-9).**

43. **Day 10** — Append section 113 to `docs/functional-requirements-revised-v6.md` with FR-683 through FR-700 per spec correction §6.
44. **Day 10 afternoon** — Author the operator-guide pages: `docs/operator-guide/vault-overview.md`, `docs/operator-guide/runbooks/vault-rotation.md`, `docs/operator-guide/runbooks/vault-cache-flush.md`, `docs/operator-guide/runbooks/vault-token-rotation.md`. (These integrate into UPD-039's runbook library; if UPD-039 has not landed, the files live here and merge into UPD-039 later.)
45. **Day 11** — Author the developer-guide pages: `docs/developer-guide/secret-provider-protocol.md`, `docs/developer-guide/adding-a-new-secret.md` (the recipe for adding a new BC-owned secret).
46. **Day 11 afternoon** — Run UPD-039's `scripts/generate-env-docs.py` to verify the new `PLATFORM_VAULT_*` env vars are auto-listed with `sensitive` classification per FR-700; CI must pass.
47. **Day 12** — Final review pass; address PR feedback; merge.

## Effort & Wave

**Total estimated effort: 15-17 dev-days** (5-6 wall-clock days with 3 devs in parallel: 1 on Tracks A+D, 1 on Track B Python+E, 1 on Track B Go+C, then converging for Phase 6 + 7).

The brownfield's "10 days (9 points)" understates because it does not account for: (a) the 7 per-BC HCL policy authoring + verification (~2 days); (b) the Go-side mirror across 4 satellites (~2-3 days); (c) the matrix-CI verification across 3 modes (~1 day); (d) the comprehensive E2E coverage of 8 scenarios (~1 day). The corrected estimate is consistent with the v1.3.0 cohort's pattern of brownfield-understated estimates (per features 085-089's plan corrections).

**Wave: Wave 15 — after UPD-039 (documentation pass).** Position in execution order:
- Wave 11 — UPD-036 Administrator Workbench
- Wave 12 — UPD-037 Public Signup Flow
- Wave 13 — UPD-038 Multilingual README
- Wave 14 — UPD-039 Documentation Site
- **Wave 15 — UPD-040 Vault** (this feature)
- Wave 16 — UPD-041 OAuth env bootstrap (depends on Vault for OAuth client_secret_ref resolution at install time)

**Cross-feature dependency map**:
- UPD-040 BLOCKS UPD-041 (OAuth env bootstrap stores client_secret in Vault on first launch).
- UPD-040 INTEGRATES with UPD-024 (rotation: rewires `RotatableSecretProvider`).
- UPD-040 INTEGRATES with UPD-035 (observability: alerts + dashboards in observability bundle).
- UPD-040 INTEGRATES with UPD-036 (admin workbench: backend contracts for `/admin/security/vault` UI page).
- UPD-040 INTEGRATES with UPD-039 (docs: runbook library + env-vars / Helm-values reference auto-flow).
- UPD-040 EXTENDS UPD-019 (S3 abstraction architectural pattern is reused for SecretProvider).
- UPD-040 EXTENDS feature 013 (the original `VaultResolver` interface is preserved at the abstraction-boundary level).

## Risk Assessment

**Medium risk overall.** The 5 main risk categories (mirroring the brownfield's analysis with refinements):

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **R1: Migration data loss on production cluster** | Low | High (operational outage) | Default dry-run; `--apply` requires explicit flag; K8s Secrets preserved untouched; manifest emits SHA-256 for post-hoc verification; documented rollback (mode-flag flip); Track D Day 7 afternoon includes a synthetic-cluster test of the rollback path. |
| **R2: Mode-specific regressions caught late** | Medium | Medium (CI failure during release-candidate cut) | Matrix CI from day one of Track A: `secret_mode: [mock, kubernetes, vault]` runs the J01 + J11 journey suites in every mode; failure in any mode blocks the PR. Phase 6 day 9 has a SC sweep that hits every SC across all 3 modes. |
| **R3: Vault operational complexity** | Medium | Low (operator UX friction, not a security risk) | UPD-039's installation guide includes a Vault operator guide; the `standalone` preset works for small production deployments without Raft expertise; the `kubernetes` transitional mode lets operators delay Vault adoption. |
| **R4: Policy misconfiguration leaks secrets across BCs** | Low | High (privacy / compliance breach) | Track C ships tight default policies (deny-by-default per FR-695); Track A's CI deny-list (FR-687) catches misuse at code-review time; SC-014 is a static-analysis check that flags overly permissive policy entries. |
| **R5: Token starvation under high load** | Low | Medium (degraded performance) | Aggressive caching (60s TTL, hit ratio target ≥ 80%); per-pod LRU sized at 1000; Vault rate limits documented in the operator guide. The brownfield mentions this; UPD-040 does NOT add read batching as a follow-up.  |
| **R6 (NEW — not in brownfield): Mode-flag DeprecationWarning ignored by operators** | Medium | Low (one-release transition pain) | The DeprecationWarning emits via structured logger to Loki (UPD-084); a Grafana panel surfaces the count; operators see the warning during their normal monitoring rounds. Removal in v1.4.0 is announced in release notes. |
| **R7 (NEW — not in brownfield): Per-BC SA hardening incomplete** | Medium | Medium (single-SA-failure compromises all BCs) | Phase D9 documents this as a known limitation; the per-BC SA hardening is a follow-up feature (likely UPD-042 or UPD-046); the v1.3.0 cohort accepts the single-SA risk in exchange for ship-on-time. |

## Plan-correction notes (vs. brownfield input)

1. **Effort estimate corrected from 10 days to 15-17 days.** Brownfield understates by ~50%; corrected per the v1.3.0 cohort pattern.
2. **Wave placement: Wave 15 (not Wave 12 or 13 as the brownfield draft implies).** Per the cross-feature dependency map.
3. **`SecretProvider` Protocol is NOT new** — it already exists at `notifications/channel_router.py:45-48` (Track A promotes it; brownfield's "Define SecretProvider Protocol" step in Track A is REPHRASED as "Promote and extend SecretProvider Protocol").
4. **Method-name normalization is REQUIRED** (R3a — spec correction). Brownfield's `get`/`put`/etc. names are ADOPTED; existing `read_secret`/`write_secret` are migrated internally; this is a 2-callsite migration (not a deprecation).
5. **`/admin/security/vault` UI page is owned by UPD-036**, not UPD-040 (per spec correction §5). Brownfield's Track E "Create `/admin/security/vault` page in Next.js" is RESCOPED to "Deliver the 3 backend admin endpoints + audit-chain integration; UI page consumes them via UPD-036."
6. **FR numbering: FR-683-FR-700 (NEW section 113), NOT FR-621-FR-638** (per spec correction §6).
7. **Helm chart pinned at v0.30.0** (T030 verification during implementation; brownfield is silent on the pin).
8. **Go satellite scope is 4 satellites with a SHARED package** at `services/shared/secrets/` (not per-satellite duplicated `internal/vault/`). Phase 0 R7 default.
9. **The 7 BC policies (NOT 2 as the brownfield example shows)** are: `platform-auth.hcl`, `platform-model-catalog.hcl`, `platform-notifications.hcl`, `platform-runtime.hcl`, `platform-security-compliance.hcl`, `platform-accounts.hcl`, `platform-cost-governance.hcl`. Brownfield only enumerates 2; UPD-040 commits all 7 per FR-695.
10. **Cluster-wide cache flush is OUT OF SCOPE for MVP** (Phase 0 R12). Brownfield's Track E "cache flush, policy reload, manual token renewal" is per-pod only; cluster-wide is a follow-up.
11. **Auto-unseal is documented but operator-chosen** (3 options per spec assumptions). Brownfield is silent.
12. **`KubernetesSecretProvider` is Python-only**; Go satellites in `kubernetes` mode consume credentials via gRPC from the control plane (no Go-side K8s client required). Phase 0 R7 default.

## Complexity Tracking

| Area | Complexity | Why |
|---|---|---|
| `SecretProvider` Protocol consolidation | Medium | 5 callsites + 2 implementations to migrate; method-name normalization touches every caller. |
| Vault client implementation | High | 3 auth methods × 2 languages = 6 paths; token lifecycle is async + signal-handling; clock skew detection is subtle. |
| Helm sub-chart | Low | Wrapper of upstream chart; the upstream handles HA/Raft/storage. |
| Migration tooling | Medium | Idempotency + manifest verification + rollback path are all subtle; the K8s Secret-name → Vault path mapping requires per-BC understanding. |
| Admin contracts | Low | 3 endpoints + Pydantic schemas; the audit-chain integration is the only non-trivial piece. |
| E2E + matrix CI | Medium | 8 test files + 3-mode matrix on the journey suite; debugging mode-specific failures is tricky. |
| Documentation | Medium | 4 runbooks + 2 developer-guide pages + section 113 of FR doc + env-var auto-doc verification. |

**Net complexity: medium.** The keystone (Track A) is the highest-risk piece; once the abstraction is right, the rest is mechanical implementation.
