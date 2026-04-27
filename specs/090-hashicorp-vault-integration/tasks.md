# Tasks: UPD-040 — HashiCorp Vault Integration

**Feature**: 090-hashicorp-vault-integration
**Branch**: `090-hashicorp-vault-integration`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

User stories (from spec.md):
- **US1 (P1)** — Production operator installs Musematic with HA Vault (3 Raft replicas, Kubernetes auth, end-to-end verified within 30 minutes of `helm install` on a fresh cluster).
- **US2 (P1)** — Operator migrates from Kubernetes Secrets to Vault without downtime via `platform-cli vault migrate-from-k8s` (idempotent, dry-run-by-default, SHA-256 manifest, mode-flag rollback).
- **US3 (P2)** — Security engineer rotates a model provider API key via Vault KV v2 versioning (UPD-024 `RotatableSecretProvider` rewired; dual-credential window via cache TTL).
- **US4 (P2)** — Super admin verifies Vault status during an incident (`/admin/security/vault` UI page owned by UPD-036 + `platform-cli vault status` CLI fallback).
- **US5 (P1)** — Platform degrades gracefully when Vault is unreachable (cached reads → stale reads up to maxStaleness → critical-path refusal — NEVER hardcoded fallback per FR-688).

Independent-test discipline: every US MUST be verifiable in isolation. US1 = HA install on a fresh kind cluster + read/write a synthetic KV v2 path. US2 = K8s-Secret → Vault migration on a synthetic cluster + idempotency re-run + rollback. US3 = end-to-end rotation via UPD-024's flow on a vault-mode cluster + version 1 destroyed after dual-credential window. US4 = `platform-cli vault status` returns full panel data + `/api/v1/admin/vault/cache-flush` succeeds with audit-chain entry. US5 = NetworkPolicy blocks Vault → cached reads serve → stale-window expires → critical-path refused (HTTP 503).

**Wave-15 sub-division** (per plan.md "Wave Placement" + "Effort & Wave"):
- W15.0 — Setup: T001-T004
- W15A — Track A SecretProvider consolidation (KEYSTONE — blocks B/D/E): T005-T028
- W15B — Track B Vault client implementations (Python + Go): T029-T053
- W15C — Track C Vault Helm sub-chart (FULLY INDEPENDENT): T054-T070
- W15D — Track D Migration tooling: T071-T084
- W15E — Track E Admin contracts + observability: T085-T097
- W15F — Phase 6 E2E coverage + matrix CI: T098-T108
- W15G — Phase 7 Documentation polish + handoff: T109-T120

---

## Phase 1: Setup

- [ ] T001 [W15.0] Verify the on-disk repo state per plan.md "Phase 0 — Research" + spec.md scope-discipline section: confirm `apps/control-plane/src/platform/connectors/security.py` exists with `VaultResolver` class at lines 51-82 and the `vault` mode raising `CredentialUnavailableError` at line 58; confirm `apps/control-plane/src/platform/notifications/channel_router.py:45-48` defines the existing `SecretProvider` Protocol with `read_secret` / `write_secret` methods; confirm `apps/control-plane/src/platform/security_compliance/providers/rotatable_secret_provider.py` exists with the 4 public method names per research R1 (`get_current`, `get_previous`, `validate_either`, `cache_rotation_state`); confirm 5 per-BC `*_secret_ref` columns per research R2; confirm NO `deploy/helm/vault/` directory exists; confirm NO `services/shared/secrets/` package exists; confirm NO `apps/ops-cli/src/platform_cli/commands/vault.py` exists. Document the inventory in `specs/090-hashicorp-vault-integration/contracts/repo-inventory.md` (NEW file).
- [ ] T002 [P] [W15.0] Verify CI substrate per plan.md "Source Code" section: read `.github/workflows/ci.yml` and confirm the existing `dorny/paths-filter@v3` block; confirm UPD-039 has merged its `docs:` filter (or note it has not); plan integration of the new matrix-CI job (`secret_mode: [mock, kubernetes, vault]`) for the journey suite. Document the integration plan in `specs/090-hashicorp-vault-integration/contracts/ci-integration.md` (NEW file).
- [ ] T003 [P] [W15.0] Verify the constitutional anchors per plan.md Constitutional Anchors table: open `.specify/memory/constitution.md` and confirm Rule 10 (lines 123-126) + Rule 30 (lines 198-202) + Rule 31 (lines 204-212) + Rule 37 (lines 228-231) match the plan's quoted text. If any rule has been renumbered or rewritten, escalate via spec amendment before authoring code. Document confirmation (or required amendment) in `specs/090-hashicorp-vault-integration/contracts/constitution-confirmation.md` (NEW file).
- [ ] T004 [P] [W15.0] Cross-feature coordination check per plan.md "Cross-feature dependency map": confirm UPD-024 (security_compliance) is on `main`; confirm UPD-035 (observability bundle) is on `main`; check status of UPD-036 (Administrator Workbench — feature 086) and UPD-039 (Documentation Site — feature 089). If UPD-036 has not landed, T087's `/admin/security/vault` UI page is documented as DEFERRED (UPD-040 ships only the backend contracts + the `platform-cli vault status` CLI fallback per spec correction §5). If UPD-039 has not landed, T109-T118's runbook+developer-guide pages live in this feature and merge into UPD-039 later. Document the coordination decisions in `specs/090-hashicorp-vault-integration/contracts/cross-feature-deps.md` (NEW file).

---

## Phase 2: Track A — SecretProvider Consolidation (KEYSTONE — Blocks B / D / E)

**Story goal**: Promote the existing `SecretProvider` Protocol from `notifications/channel_router.py:45-48` to `apps/control-plane/src/platform/common/secret_provider.py`; normalize method names from `read_secret`/`write_secret` to `get`/`put`/`delete_version`/`list_versions`/`health_check` per spec correction §3a; rewire the 5 per-BC `*_secret_ref` callsites + the 6 callers of `RotatableSecretProvider`; add a Go-side mirror at `services/shared/secrets/`; add the FR-687 CI deny-list check. Without these, the Vault client (Track B) and the migration tool (Track D) cannot be wired into the BCs.

### Canonical Protocol module + error taxonomy

- [ ] T005 [W15A] Create `apps/control-plane/src/platform/common/secret_provider.py` (NEW canonical home per FR-685): defines `class SecretProvider(Protocol)` with 5 async methods (`get(path: str, key: str = "value") -> str`, `put(path: str, values: dict[str, str]) -> None`, `delete_version(path: str, version: int) -> None`, `list_versions(path: str) -> list[int]`, `health_check() -> HealthStatus`). Defines `HealthStatus` dataclass (`status: Literal["green", "yellow", "red"]`, `auth_method`, `token_expiry_at`, `lease_count`, `recent_failures`, `cache_hit_rate`, `error: str | None`). Defines error taxonomy: re-export `CredentialUnavailableError` from existing `connectors/security.py` (preserves backward compatibility); NEW `CredentialPolicyDeniedError` (inherits `CredentialUnavailableError`); NEW `InvalidVaultPathError` (inherits `ValueError` — raised at boundary per design D4). Includes the canonical-path regex `^secret/data/musematic/(production|staging|dev|test|ci)/(oauth|model-providers|notifications|ibor|audit-chain|connectors|accounts)/[a-zA-Z0-9_/-]+$` per FR-689.
- [ ] T006 [W15A] Modify `apps/control-plane/src/platform/notifications/channel_router.py` per design D10: replace the existing `SecretProvider` Protocol definition at lines 45-48 with a re-export `from platform.common.secret_provider import SecretProvider as _CanonicalSecretProvider; SecretProvider = _CanonicalSecretProvider` plus a module-level DeprecationWarning emitted on first import (track via a module-level boolean to avoid log spam). Add a docstring explaining the migration path: "Imports of `SecretProvider` from `platform.notifications.channel_router` are deprecated; migrate to `platform.common.secret_provider` by v1.4.0."
- [ ] T007 [W15A] Modify `apps/control-plane/src/platform/common/__init__.py`: re-export `SecretProvider`, `HealthStatus`, `CredentialUnavailableError`, `CredentialPolicyDeniedError`, `InvalidVaultPathError` per Python convention. This is the public API surface for BC code.

### MockSecretProvider extraction (preserves existing behaviour per SC-020)

- [ ] T008 [W15A] [US1, US5] Create `MockSecretProvider` class inside `apps/control-plane/src/platform/common/secret_provider.py`: extracts the byte-for-byte logic from `connectors/security.py:60-82` (`_resolve_mock` method) into the new class's `get()` method. Wraps the synchronous file read in `await asyncio.to_thread(...)` per design D2 to satisfy the async Protocol surface. Implements `put()` (writes to the same `.vault-secrets.json`), `delete_version()` (no-op for mock — versioning is not real), `list_versions()` (returns `[1]` always), `health_check()` (returns `green` if file readable, `red` if not).
- [ ] T009 [W15A] [US5] Create `apps/control-plane/tests/common/test_secret_provider_mock.py` (NEW pytest unit test file): ~12 test cases covering MockSecretProvider semantics: `.vault-secrets.json` JSON-dict read; env-var fallback `CONNECTOR_SECRET_*`; no file present + no env var → `CredentialUnavailableError`; canonical-path regex enforcement (non-conforming path → `InvalidVaultPathError`); health_check on present + absent file. Acceptance: byte-for-byte semantic parity with the existing `_resolve_mock` (SC-020). Run `pytest apps/control-plane/tests/common/test_secret_provider_mock.py -v`.
- [ ] T010 [W15A] [US1] Modify `apps/control-plane/src/platform/connectors/security.py` per plan.md design Track A: refactor `VaultResolver._resolve_mock` (lines 60-82) to delegate to the new `MockSecretProvider`. KEEP `VaultResolver` as a thin compatibility wrapper for one release per design D10; add a DeprecationWarning. Day-1 acceptance: existing tests in `apps/control-plane/tests/connectors/` pass unchanged.

### Existing-callsite rewires (5 per-BC `*_secret_ref` resolution paths)

- [ ] T011 [W15A] [US1] Rewire `apps/control-plane/src/platform/auth/services/oauth_service.py:_resolve_secret` (lines 732-747) per plan.md research R3: REPLACE the 16-line fallback chain with `return await self._secret_provider.get(reference)`. REMOVE the `self.credential_resolver` constructor parameter (tests inject a `MockSecretProvider` instead). REMOVE the `OAUTH_SECRET_*` env-var fallback. Update the call at line 604 to remain unchanged (`client_secret = await self._resolve_secret(provider.client_secret_ref)`). Update `apps/control-plane/src/platform/auth/services/oauth_service.py.__init__` signature to accept `secret_provider: SecretProvider` instead of `credential_resolver`.
- [ ] T012 [W15A] [US1] Rewire `RotatableSecretProvider` at `apps/control-plane/src/platform/security_compliance/providers/rotatable_secret_provider.py` per plan.md research R1 + design D5: PRESERVE all 4 public method names (`get_current`, `get_previous`, `validate_either`, `cache_rotation_state`) per the contract; INTERNAL `_read_secret` is REPLACED by `await self._secret_provider.get(path)`. Implement KV v2 versioning: `get_current(name)` reads version `latest`; `get_previous(name)` reads version `latest - 1` if it exists. The bespoke `current`/`previous` two-key scheme is REMOVED. Migrate the 6 callers per research R1 (no signature changes — only constructor injection of the new `SecretProvider`).
- [ ] T013 [P] [W15A] [US1] Rewire `apps/control-plane/src/platform/notifications/dependencies.py:InMemorySecretProvider` (lines 72-78) per plan.md research R4: rename `read_secret` → `get` and `write_secret` → `put` per design D1. Update the 2 callers (research found 2: `channel_router.py` and the dependencies-injection callsite). Tests in `apps/control-plane/tests/notifications/` confirm zero behavioural regression.
- [ ] T014 [P] [W15A] [US1] Rewire `apps/control-plane/src/platform/model_catalog/services/credential_service.py` per research R2: the `ModelProviderCredential.vault_ref` resolution path delegates to `await self._secret_provider.get(credential.vault_ref)`. The `RotatableSecretProvider` integration (UPD-024 rotation flow) is preserved unchanged via T012's rewire.
- [ ] T015 [P] [W15A] [US1] Rewire `apps/control-plane/src/platform/auth/services/ibor_service.py` (verify exact file path during T015 — search for `IBORConnector.credential_ref` callsite) per research R2: the `credential_ref` resolution path delegates to `await self._secret_provider.get(connector.credential_ref)`. If the file is in a different location (e.g., `auth/services/ibor_sync.py`), update the path inline.
- [ ] T016 [W15A] [US1] Rewire the 2 notifications `signing_secret_ref` callsites per research R2: `ChannelConfig.signing_secret_ref` (nullable) and `OutboundWebhook.signing_secret_ref` (required) both flow through `await self._secret_provider.get(...)`. The webhook-signing logic (UPD-077 NotificationsBC) is preserved.
- [ ] T017 [W15A] Add a `git grep` regression check to `scripts/check-secret-access.py` (created in T026) that verifies zero direct callers of `VaultResolver.resolve()` exist outside the `connectors/security.py` (the deprecated wrapper) and `common/secret_provider.py` files per SC-003. Exit code 1 on any violation.

### Go-side `SecretProvider` interface mirror (FR-686)

- [ ] T018 [W15A] [US1] Create `services/shared/secrets/provider.go` (NEW canonical Go interface per FR-686): defines `type SecretProvider interface` with 5 methods (`Get(ctx, path, key) (string, error)`, `Put(ctx, path, values) error`, `DeleteVersion(ctx, path, version) error`, `ListVersions(ctx, path) ([]int, error)`, `HealthCheck(ctx) (*HealthStatus, error)`). Defines `HealthStatus` struct mirroring the Python dataclass.
- [ ] T019 [W15A] Create `services/shared/secrets/types.go` (NEW): error taxonomy — `var ErrCredentialUnavailable = errors.New("credential unavailable")`, `var ErrCredentialPolicyDenied = errors.New("policy denied")`, `var ErrInvalidVaultPath = errors.New("invalid vault path")`. Exposes `IsCredentialUnavailable(err) bool` etc. for callers' error-handling.
- [ ] T020 [P] [W15A] Create `services/shared/secrets/path_validator.go` (NEW): mirror of the Python canonical-path regex per FR-689. Exposes `ValidatePath(path string) error` returning `ErrInvalidVaultPath` on non-conforming input.
- [ ] T021 [P] [W15A] Create `services/shared/secrets/go.mod` (NEW): module name `github.com/musematic/services/shared/secrets`; Go 1.22+; declares the eventual `github.com/hashicorp/vault/api` dependency (added in Track B Phase 2).
- [ ] T022 [P] [W15A] Create `services/shared/secrets/secrets_test.go` (NEW): Go unit tests for the path validator + error taxonomy. ~6 test cases. `go test` passes.

### CI deny-list for direct env-var access (FR-687)

- [ ] T023 [W15A] Create `scripts/check-secret-access.py` (NEW per FR-687 + plan.md design Track A Phase 5): Python stdlib + `ast.parse()` walker. Scans (a) `apps/control-plane/src/platform/` for direct `os.getenv("*")` calls where the env name matches the deny-list patterns (`*_SECRET`, `*_PASSWORD`, `*_API_KEY`, `*_TOKEN`); (b) `services/` for direct `os.Getenv("*")` calls with the same patterns via regex (Go AST is overkill); (c) excludes the `SecretProvider` implementation files (`apps/control-plane/src/platform/common/secret_provider.py`, `apps/control-plane/src/platform/connectors/security.py`, `services/shared/secrets/*`). Exit codes: 0 (clean), 1 (violation found), 2 (parse error).
- [ ] T024 [P] [W15A] Create `scripts/tests/test_check_secret_access.py` (NEW pytest unit test file): ~8 test cases covering allowed paths (calls inside `SecretProvider` impls), denied paths (calls outside), pattern matching (`API_KEY` matched, `API_VERSION` not matched), Go-file scanning, parse-error handling.
- [ ] T025 [W15A] Modify `.github/workflows/ci.yml` per plan.md Constitutional Anchors row Rule 37: append a new job `check-secret-access` (runs on every PR; depends on the existing `python` and `go-*` paths-filters; runs `python scripts/check-secret-access.py`; fails the build on exit code 1). Modeled on UPD-039's docs-staleness pattern.
- [ ] T026 [W15A] Run `python scripts/check-secret-access.py` against the current main + the in-flight Track A branch; document any pre-existing violations that were not introduced by UPD-040 in `specs/090-hashicorp-vault-integration/contracts/pre-existing-secret-access-violations.md` (NEW file). These violations are flagged for follow-up but do NOT block UPD-040 unless they are introduced by Track A's rewires.

### `VaultSettings` config block (PLATFORM_VAULT_* env scheme per spec correction §1)

- [ ] T027 [W15A] [US1] Modify `apps/control-plane/src/platform/common/config.py` per plan.md research R5 + design D6: add `class VaultSettings(BaseSettings)` with `model_config = SettingsConfigDict(env_prefix="VAULT_", extra="ignore", populate_by_name=True)`. Fields per spec Key Entities: `mode: Literal["mock", "kubernetes", "vault"] = "mock"`, `addr: str = ""`, `namespace: str = ""`, `ca_cert_secret_ref: str | None = None`, `auth_method: Literal["kubernetes", "approle", "token"] = "kubernetes"`, `kubernetes_role: str = "musematic-platform"`, `service_account_token_path: str = "/var/run/secrets/tokens/vault-token"`, `approle_role_id: str = ""`, `approle_secret_id_secret_ref: str | None = None`, `token: str = ""`, `kv_mount: str = "secret"`, `kv_prefix: str = "musematic/{environment}"`, `cache_ttl_seconds: int = 60`, `cache_max_staleness_seconds: int = 300`, `retry_attempts: int = 3`, `retry_timeout_seconds: int = 10`, `lease_renewal_threshold: float = 0.5`. Add `vault: VaultSettings = Field(default_factory=VaultSettings)` to `PlatformSettings` between `tagging` and `visibility` per the alphabetic-ish convention.
- [ ] T028 [W15A] [US1] Add Pydantic `model_validator(mode="after")` on `PlatformSettings` per spec correction §1 (deprecated alias migration): if `os.environ.get("PLATFORM_VAULT_MODE") is None and os.environ.get("CONNECTOR_VAULT_MODE") is not None`, copy the value to `vault.mode` and emit a structured-log DeprecationWarning ("CONNECTOR_VAULT_MODE is deprecated; migrate to PLATFORM_VAULT_MODE by v1.4.0."). If both are set with conflicting values, raise a startup error. Per design D6: if `vault.auth_method == "token"` AND `environment in ("production", "staging")` AND `os.environ.get("ALLOW_INSECURE", "").lower() != "true"`, raise a startup error pointing at the AppRole bootstrap runbook.

**Checkpoint (end of Phase 2)**: `pytest apps/control-plane/` passes; `git grep "VaultResolver" apps/control-plane/src/platform/` returns zero matches outside `connectors/security.py` (deprecated wrapper) and `common/secret_provider.py`; `python scripts/check-secret-access.py` exits 0; the 6 callers of `RotatableSecretProvider` show no test regressions; `mypy apps/control-plane/src/platform/common/secret_provider.py` passes strict.

---

## Phase 3: Track B — Vault Client Implementations (Python)

**Story goal**: Implement `VaultSecretProvider` (Python via `hvac>=2.3.0`); 3 auth methods (kubernetes/approle/token); token lifecycle; per-pod LRU + max-staleness cache; FR-688 fail-safe degradation; emit FR-697 11 metrics; structured-log discipline. Depends on Track A Phase 2.

### Dependencies + scaffolding

- [ ] T029 [W15B] [US1] Modify `apps/control-plane/requirements.txt` per plan.md Technical Context: add `hvac>=2.3.0`. Modify `apps/control-plane/pyproject.toml` (if dependencies are also declared there) to keep parity. Run `pip install -r requirements.txt` in a clean venv to verify.
- [ ] T030 [W15B] [US1] Pin the upstream `hashicorp/vault` Helm chart version per plan.md design D7: research the latest stable LTS at the time of authoring (default v0.30.0; T030 verifies live); document the pin decision in `specs/090-hashicorp-vault-integration/contracts/vault-version-pin.md` (NEW file). Cross-check against the upstream release notes for any breaking changes since the brownfield's reference.

### `VaultSecretProvider` core (KV v2)

- [ ] T031 [W15B] [US1] Add `class VaultSecretProvider` to `apps/control-plane/src/platform/common/secret_provider.py` per plan.md design Track B Phase 1 day 4: `__init__(settings: VaultSettings)` constructs a `hvac.Client` with `url=settings.addr`, `namespace=settings.namespace`, `verify=ca_cert_path_resolved_from_secret_ref`. Implements `get(path, key="value")` via `client.secrets.kv.v2.read_secret_version(path=path).data.data[key]`; raises `CredentialUnavailableError` on 404 + `CredentialPolicyDeniedError` on 403. Implements `put(path, values)` via `client.secrets.kv.v2.create_or_update_secret(path, secret=values, cas=current_version)` per design D5 + spec edge case (CAS conflict handling with 3-retry loop). Implements `delete_version(path, version)` via `client.secrets.kv.v2.destroy_secret_versions(path, versions=[version])`. Implements `list_versions(path)` via `client.secrets.kv.v2.read_secret_metadata(path).data.versions.keys()`. All operations validate the canonical path per design D4 BEFORE any Vault round-trip.
- [ ] T032 [W15B] [US1] Implement `health_check()` in `VaultSecretProvider`: aggregates `client.sys.read_health_status()` (Vault sealed/standby/active) + token expiry from the renewal-loop accountant (T036) + lease count from `client.sys.list_leases()` (if policy allows) + recent failures from a ring buffer (size 10) + cache hit rate from the metrics counter. Returns the `HealthStatus` dataclass per FR-698. Used by Track E's admin endpoint.

### 3 auth methods (FR-684)

- [ ] T033 [W15B] [US1] Implement Kubernetes auth in `VaultSecretProvider._authenticate_kubernetes()` per plan.md design Track B day 5: read the projected ServiceAccount token from `settings.service_account_token_path` (default `/var/run/secrets/tokens/vault-token`); call `client.auth.kubernetes.login(role=settings.kubernetes_role, jwt=sa_token)`; cache the resulting client token + lease ID + expiry timestamp. Handle Kubernetes SA token rotation (transparent re-auth on next request after a 403) per spec edge case.
- [ ] T034 [P] [W15B] [US1] Implement AppRole auth in `VaultSecretProvider._authenticate_approle()`: read `settings.approle_role_id` directly + `settings.approle_secret_id_secret_ref` resolved as a file path (mounted SecretID file refreshed by an external rotator); call `client.auth.approle.login(role_id, secret_id)`; same caching as kubernetes auth. Handle SecretID expiry per spec edge case (re-auth on 403; fail clearly if SecretID file is itself stale).
- [ ] T035 [P] [W15B] [US1] Implement Token auth in `VaultSecretProvider._authenticate_token()`: use `settings.token` directly as the Vault token. The startup-check from T028 ensures this path is unreachable in production unless `ALLOW_INSECURE=true` AND `PLATFORM_ENVIRONMENT=dev`. Per design D6, this is dev/CI only.

### Token lifecycle (FR-690)

- [ ] T036 [W15B] [US1] Implement the token-renewal background asyncio task per plan.md design Track B day 6: spawn an `asyncio.create_task(self._renewal_loop())` on first authenticate; loop sleeps until `expiry_at - (settings.lease_renewal_threshold * ttl)` (default 50% of TTL); calls `client.auth.token.renew_self()`; updates the cached expiry; emits `vault_renewal_success_total` metric on success and `vault_renewal_failure_total` on failure. On 3 consecutive failures, attempts full re-authentication via the original auth method.
- [ ] T037 [W15B] [US1] Implement clock-skew detection per spec edge case: parse the `Date` HTTP response header from each Vault response; compare to local `datetime.utcnow()`; if skew > 30 seconds, lower the renewal threshold from 0.5 to 0.4 for the next renewal cycle; emit a structured-log warning `{event: "vault.clock_skew_detected", skew_seconds: ...}` (NO token value).
- [ ] T038 [W15B] [US1] Implement SIGTERM lease-revocation handler: register a `signal.signal(SIGTERM, self._on_sigterm)` callback that runs `client.auth.token.revoke_self()` synchronously before the asyncio loop exits. Idempotent (safe if already revoked). Verifies the token is revoked via `vault list auth/kubernetes/role/musematic-platform/...` (operator's manual check; not a unit test).

### Per-pod cache (FR-691)

- [ ] T039 [W15B] [US1, US5] Implement the per-pod LRU cache in `VaultSecretProvider` per plan.md design D3: use `cachetools.TTLCache(maxsize=1000, ttl=settings.cache_ttl_seconds)` for the primary cache. Add a parallel `dict[str, datetime]` tracking the last-successful-Vault-read timestamp per path, used for the max-staleness window per FR-688.
- [ ] T040 [P] [W15B] [US5] Implement the stale-read fallback per FR-688 per plan.md design Track B day 6 afternoon: on cache miss + Vault unreachable (timeout / connection refused / 5xx), check the parallel `last_successful_read` timestamp; if the last successful read is within `settings.cache_max_staleness_seconds` (default 300s), serve the stale value from a separate "graveyard" cache that is NEVER evicted by TTL; emit `vault_serving_stale_total` metric + structured-log `{event: "vault.serving_stale", path: "...", stale_age_seconds: ...}`.
- [ ] T041 [P] [W15B] [US5] Implement critical-path refusal per FR-688: introduce a `critical: bool = False` parameter on `get()` (default False; OAuth callback / login pass `critical=True`). When `critical=True` AND cache is cold AND Vault unreachable, raise `CredentialUnavailableError` immediately (no stale-read fallback even if available). This catches auth-bypass risks per spec edge case.
- [ ] T042 [P] [W15B] [US4] Implement cache flush API: `flush_cache(path: str | None = None) -> int` clears either a single path or the entire cache; returns the number of entries flushed. Used by Track D `platform-cli vault flush-cache` AND Track E `POST /api/v1/admin/vault/cache-flush`.

### Prometheus metrics (FR-697 — 11 metrics)

- [ ] T043 [W15B] [US1, US4] Author the 11 Prometheus metrics per FR-697 in `apps/control-plane/src/platform/common/secret_provider.py`: `vault_lease_count` (Gauge, labels: pod), `vault_renewal_success_total` (Counter), `vault_renewal_failure_total` (Counter), `vault_auth_failure_total` (Counter, labels: auth_method), `vault_read_total` (Counter, labels: domain — extracted from path), `vault_write_total` (Counter, labels: domain), `vault_cache_hit_total` (Counter), `vault_cache_miss_total` (Counter), `vault_cache_hit_ratio` (Gauge, computed from hit/miss), `vault_serving_stale_total` (Counter), `vault_policy_denied_total` (Counter, labels: path). All metric registration uses the existing `prometheus_client` pattern from UPD-047.

### Structured-log discipline (Rule 31)

- [ ] T044 [W15B] [US1] Author structured-log entries per plan.md Constitutional Anchors row Rule 31 + UPD-084 logging discipline: events `vault.authenticated`, `vault.lease_renewed`, `vault.lease_revoked`, `vault.policy_denied`, `vault.serving_stale`, `vault.unreachable`, `vault.clock_skew_detected`, `vault.cache_flushed`. Apply a deny-list check inside the logger: if any field name appears in `{"token", "secret_id", "kv_value", "client_secret"}`, raise an assertion error at runtime (this catches accidental leaks during code review and at production-runtime). Implement as a structlog processor.
- [ ] T045 [W15B] [US1] Add a code-review check via `scripts/check-secret-access.py` extension: scan all `logger.info(...)` and `logger.error(...)` calls for any kwarg named `token`, `secret_id`, `kv_value`, `client_secret`; fail the CI on any match. Add 4 test cases in `scripts/tests/test_check_secret_access.py`.

### `KubernetesSecretProvider` (transitional mode — Python only)

- [ ] T046 [W15B] [US2] Add `class KubernetesSecretProvider(SecretProvider)` to `apps/control-plane/src/platform/common/secret_provider.py` per plan.md Phase 0 R7: uses the existing `kubernetes-asyncio` library (already in requirements.txt — verify during T046; if absent, add). Reads from K8s Secrets at the canonical-path-mirrored Secret-name scheme (`Secret name=musematic-{env}-{domain}-{resource}`, key=`value`). Implements `get`/`put`/`delete_version`/`list_versions`/`health_check`. Versioning is mocked: `list_versions` always returns `[1]`; `delete_version` is a no-op (K8s Secrets don't natively version). Reads namespace from `PLATFORM_KUBERNETES_NAMESPACE` env var (default `platform`).
- [ ] T047 [P] [W15B] [US2] Author the canonical-path → K8s-Secret-name mapping function: `vault_path_to_k8s_secret_name("secret/data/musematic/production/oauth/google") -> "musematic-production-oauth-google"`. Implements the inverse for the migration tool (Track D). Validates the round-trip mapping is bijective. ~12 test cases.

### Track B Python integration tests

- [ ] T048 [W15B] [US1] Create `apps/control-plane/tests/common/test_vault_secret_provider.py` (NEW pytest test file) per plan.md design Track B day 7: ~30 test cases covering KV v2 read/write/delete-version/list-versions/health-check; 3 auth methods (kubernetes/approle/token mocked via `pytest-mock`); token lifecycle (renewal trigger, SIGTERM revocation); cache hit/miss; stale-read fallback; critical-path refusal; canonical-path enforcement; metric emission; structured-log discipline. Uses `pytest-asyncio` for async tests + a `vault-dev-pod` fixture (kind cluster sidecar started in conftest.py).

---

## Phase 4: Track B — Vault Client Implementations (Go)

**Story goal**: Mirror the Python implementation in Go via `github.com/hashicorp/vault/api` per FR-686. Single shared package at `services/shared/secrets/` (per plan.md Phase 0 R7 default) consumed by all 4 satellites.

- [ ] T049 [W15B] [US1] Modify `services/shared/secrets/go.mod` per plan.md Technical Context: add `github.com/hashicorp/vault/api v1.15.0+`. Run `go mod tidy`.
- [ ] T050 [W15B] [US1] Create `services/shared/secrets/client.go` (NEW): implements `VaultSecretProvider` struct + 5 interface methods + cache (sync.Map + per-key time.Time TTL/staleness). KV v2 ops via `client.KVv2(mountPath).Get/Put/DeleteVersions/...`.
- [ ] T051 [P] [W15B] [US1] Create `services/shared/secrets/auth.go` (NEW): implements 3 auth methods (kubernetes/approle/token); kubernetes uses `auth/kubernetes` API via the upstream client; mirrors Python logic from T033-T035.
- [ ] T052 [P] [W15B] [US1] Create `services/shared/secrets/cache.go` (NEW): per-pod cache with TTL + max-staleness; uses `sync.Map` + per-key `time.Time` for last-successful-read tracking; mirrors Python logic from T039-T042.
- [ ] T053 [W15B] [US1] Create `services/shared/secrets/metrics.go` (NEW): 11 Prometheus metrics via `promauto.NewCounter` etc.; mirrors Python from T043. Includes the structlog-equivalent (Go `log/slog` via the existing UPD-084 pattern) deny-list check from T044.

**Checkpoint (end of Phase 4)**: `go test services/shared/secrets/...` passes; integration test brings up a kind cluster with Vault dev-mode (Track C deliverable from T060 below) + a runtime-controller pod and verifies (a) auth via SA token; (b) KV v2 round-trip; (c) cache; (d) metrics emission; (e) no plaintext-secret leakage in logs.

---

## Phase 5: Track C — Vault Helm Sub-chart (Fully Independent)

**Story goal**: Wrapper sub-chart at `deploy/helm/vault/` depending on the upstream `hashicorp/vault` chart per FR-694; 3 sizing presets; 7 BC policies per FR-695; integration with `deploy/helm/platform/` per spec correction §1.

### Wrapper sub-chart scaffolding

- [ ] T054 [W15C] [US1] Create `deploy/helm/vault/Chart.yaml` per plan.md research R6: `apiVersion: v2`, `name: musematic-vault`, `type: application`, `version: 0.1.0`, `appVersion: "1.18.x"`, `dependencies: [{name: vault, repository: https://helm.releases.hashicorp.com, version: 0.30.0}]`. Pin per T030.
- [ ] T055 [P] [W15C] [US1] Create `deploy/helm/vault/.helmignore` standard ignore patterns + `Chart.lock` (generated by `helm dep update`).
- [ ] T056 [P] [W15C] [US1] Run `helm dep update deploy/helm/vault/` to vendor the upstream chart under `deploy/helm/vault/charts/vault-0.30.0.tgz`. Commit the lockfile.
- [ ] T057 [W15C] [US1] Create `deploy/helm/vault/values.yaml` (defaults — production HA): mirrors brownfield's example (server.ha.enabled=true, replicas=3, raft.enabled=true, dataStorage.size=10Gi, ui.enabled=true, ui.serviceType=ClusterIP, injector.enabled=false). Adds `extraEnvironmentVars: {VAULT_CACERT: /vault/userconfig/tls/ca.crt}` for TLS support.

### 3 sizing presets (FR-694)

- [ ] T058 [P] [W15C] [US1] Create `deploy/helm/vault/values-dev.yaml` (dev preset — kind / E2E): `vault.server.dev.enabled: true`, single pod, in-memory storage, no PVC, root token `root` (dev-only), auto-unseal disabled. Used by E2E tests + local development.
- [ ] T059 [P] [W15C] [US1] Create `deploy/helm/vault/values-standalone.yaml` (standalone preset — small production): single pod, persistent storage 10Gi, manual Shamir-share unseal, audit log device enabled (`audit.file.path: /vault/logs/audit.log`).
- [ ] T060 [P] [W15C] [US1] Create `deploy/helm/vault/values-ha.yaml` (HA preset — production): 3 pods with Raft, 10Gi PVC per pod, anti-affinity (different nodes), auto-unseal documented but operator-chosen (cloud KMS / Transit / Shamir).

### Helm post-install Jobs

- [ ] T061 [W15C] [US1] Create `deploy/helm/vault/templates/post-install-policies-job.yaml` per plan.md design Track C day 2: a Helm `Job` resource with `helm.sh/hook: post-install,post-upgrade` that mounts the 7 HCL policy files (T065-T070) as a ConfigMap and runs `vault policy write platform-{bc} /policies/{bc}.hcl` for each. Uses an init-container to wait for Vault to be ready via `vault status`. Idempotent (`vault policy read platform-{bc}` followed by `diff` before write).
- [ ] T062 [P] [W15C] [US1] Create `deploy/helm/vault/templates/post-install-kubernetes-auth-job.yaml`: a Helm `Job` that (a) enables the kubernetes auth backend (`vault auth enable kubernetes`); (b) configures it with the cluster's Kubernetes API server URL + CA cert; (c) creates the `musematic-platform` role bound to the platform ServiceAccount + all 7 BC policies per design D9.
- [ ] T063 [P] [W15C] [US1] Create `deploy/helm/vault/templates/networkpolicy.yaml`: denies all ingress to the `platform-security` namespace except from the control-plane pods (`platform-control-plane`) and the 4 satellite namespaces (`platform-runtime`, `platform-reasoning`, `platform-simulation`, `platform-sandbox`). Uses Kubernetes `NetworkPolicy` resource with `podSelector` and `from.namespaceSelector + podSelector`.

### 7 BC HCL policies (FR-695)

- [ ] T064 [W15C] [US1] Create `deploy/vault/policies/platform-auth.hcl` per FR-695 + plan.md correction §9: grants `read` + `list` on `secret/data/musematic/+/oauth/*` and `secret/data/musematic/+/ibor/*` and `secret/metadata/musematic/+/{oauth,ibor}/*`. Documents the BC's actual reads from research R2 (OAuthProvider.client_secret_ref, IBORConnector.credential_ref).
- [ ] T065 [P] [W15C] [US1] Create `deploy/vault/policies/platform-model-catalog.hcl`: grants `read` + `list` on `secret/data/musematic/+/model-providers/*`. ModelProviderCredential.vault_ref reads.
- [ ] T066 [P] [W15C] [US1] Create `deploy/vault/policies/platform-notifications.hcl`: grants `read` + `list` on `secret/data/musematic/+/notifications/webhook-secrets/*` and `secret/data/musematic/+/notifications/sms-providers/*`. ChannelConfig.signing_secret_ref + OutboundWebhook.signing_secret_ref reads.
- [ ] T067 [P] [W15C] [US1] Create `deploy/vault/policies/platform-runtime.hcl`: grants `read` + `list` on `secret/data/musematic/+/connectors/*`. Runtime BC reads connector credentials at execution time.
- [ ] T068 [P] [W15C] [US1] Create `deploy/vault/policies/platform-security-compliance.hcl`: grants `read` + `list` + `update` (for rotation) on `secret/data/musematic/+/audit-chain/*` and `secret/metadata/musematic/+/audit-chain/*`. Optionally references `transit/sign/audit-chain` if the Transit engine is enabled per FR-696.
- [ ] T069 [P] [W15C] [US1] Create `deploy/vault/policies/platform-accounts.hcl`: minimal — grants `read` on `secret/data/musematic/+/accounts/*` (for any future account-scoped secret references; today minimal).
- [ ] T070 [P] [W15C] [US1] Create `deploy/vault/policies/platform-cost-governance.hcl`: grants `read` + `list` on `secret/data/musematic/+/model-providers/*` (overlap with model_catalog by design — same paths but distinct policy file for future per-BC SA separation per design D9 Phase 2).

**Checkpoint (end of Phase 5)**: `helm install vault deploy/helm/vault/ --set mode=dev` brings up a single Vault dev pod on kind; `helm install platform deploy/helm/platform/ --set vault.mode=dev` configures the control plane to point at the dev pod; manual `vault kv put secret/musematic/dev/test/value foo=bar` followed by `vault kv get` succeeds from inside a control-plane shell; the post-install Job successfully wrote all 7 policies (`vault policy list` confirms).

### Platform chart integration

- [ ] T071 [W15C] [US1] Modify `deploy/helm/platform/values.yaml` per spec correction §1: add a new top-level `vault:` block mirroring the brownfield example — `mode: vault`, `addr`, `namespace`, `caCertSecretRef`, `authMethod`, `kubernetes.role`, `kubernetes.serviceAccountTokenPath`, `approle.roleId`, `approle.secretIdSecretRef`, `token`, `kvMount`, `kvPrefix`, `cache.ttlSeconds`, `cache.maxStalenessSeconds`, `retry.attempts`, `retry.timeoutSeconds`, `leaseRenewalThreshold`. Each value includes a `# --` helm-docs annotation per UPD-039 / FR-611.
- [ ] T072 [P] [W15C] [US1] Modify `deploy/helm/platform/templates/deployment-control-plane.yaml`: add the projected SA token volume `vault-token` (TokenRequestProjection with audience `vault`) at `/var/run/secrets/tokens/vault-token`; inject all `PLATFORM_VAULT_*` env vars from the `vault.*` values block.
- [ ] T073 [P] [W15C] [US1] Modify `deploy/helm/platform/templates/serviceaccount.yaml`: annotate the platform ServiceAccount with `vault.hashicorp.com/role: musematic-platform` (informational; the actual binding is configured by the Helm post-install Job from T062).

---

## Phase 6: Track D — Migration Tooling

**Story goal**: NEW `platform-cli vault` Typer sub-app per FR-693 + spec User Story 2; idempotent migration with SHA-256 manifest (NEVER plaintext per Rule 31); rollback via mode-flag flip per FR-699.

### `platform-cli vault` Typer sub-app scaffolding

- [ ] T074 [W15D] [US2] Create `apps/ops-cli/src/platform_cli/commands/vault.py` (NEW Typer sub-app per plan.md research R7): `vault_app = typer.Typer(help="Manage Vault integration: migrate, verify, status, flush-cache, rotate-token.", no_args_is_help=True)`. 5 subcommand stubs: `migrate-from-k8s`, `verify-migration`, `status`, `flush-cache`, `rotate-token`. Each is a `@vault_app.command()` with full type annotations + Typer `Annotated` parameters.
- [ ] T075 [W15D] [US2] Modify `apps/ops-cli/src/platform_cli/main.py` per plan.md research R7 lines 72-78: add `from platform_cli.commands.vault import vault_app` and `app.add_typer(vault_app, name="vault")`. Verify `platform-cli vault --help` lists all 5 subcommands.

### Migration core logic

- [ ] T076 [W15D] [US2] Create `apps/ops-cli/src/platform_cli/secrets/__init__.py` + `migration.py`: scans all platform namespaces (configurable; default `platform`, `platform-runtime`, `platform-reasoning`, etc.) for K8s Secrets matching the canonical-name regex `musematic-(production|staging|dev)-(oauth|model-providers|notifications|ibor|audit-chain|connectors|accounts)-.+`. For each match: extract the canonical Vault path via the inverse mapping from T047; compute the SHA-256 of each Secret value; emit a manifest entry. Dry-run mode prints the manifest without writing to Vault.
- [ ] T077 [W15D] [US2] Implement `--apply` mode in `migration.py`: writes each K8s Secret value to Vault via `VaultSecretProvider.put(path, {"value": secret_value})` with CAS conflict handling (3 retries on conflict). On success, emits `{success: true, value_sha256: "..."}` to the manifest. On failure, emits `{success: false, reason: "..."}` and continues (does NOT abort the entire migration).
- [ ] T078 [W15D] [US2] Implement idempotency per spec User Story 2 acceptance scenario 3: before writing, call `vault_provider.get(path)` and compute SHA-256 of the current value; if it matches the K8s Secret's SHA-256, emit `{success: true, already_migrated: true}` and skip the write. Reports `already_migrated_count` + `new_count` at the end.

### Migration manifest + verification

- [ ] T079 [W15D] [US2] Create `apps/ops-cli/src/platform_cli/secrets/manifest.py`: emits the JSON manifest at `vault-migration-{timestamp}.json` per spec Key Entities. Schema: `{"timestamp": "...", "env": "...", "entries": [{"k8s_secret_namespace": "...", "k8s_secret_name": "...", "k8s_secret_key": "...", "vault_path": "...", "value_sha256": "...", "success": true|false, "reason": "...", "already_migrated": true|false}]}`. Total at end: `success_count`, `failure_count`, `already_migrated_count`, `new_count`. NEVER includes plaintext values per Rule 31.
- [ ] T080 [W15D] [US2] Implement `verify-migration` subcommand: reads the manifest path from `--manifest`; for each entry, reads the value from Vault via `VaultSecretProvider.get()`; computes SHA-256; compares to the manifest's `value_sha256`; reports per-entry pass/fail. Used by operators for post-migration audit per FR-699.

### Utility subcommands

- [ ] T081 [P] [W15D] [US4] Implement `status` subcommand: invokes the Track E `GET /api/v1/admin/vault/status` endpoint via the existing `platform-cli` HTTP-client utilities (super-admin auth from local kubeconfig token-binding); pretty-prints the panel data via Rich tables. Used as the CLI fallback per spec User Story 4 if UPD-036's UI page is delayed.
- [ ] T082 [P] [W15D] [US4] Implement `flush-cache` subcommand: invokes the Track E `POST /api/v1/admin/vault/cache-flush` endpoint with `--pod=<name>` (single pod) or `--all-pods` (iterates all platform pods). Reports per-pod success/failure.
- [ ] T083 [P] [W15D] [US4] Implement `rotate-token` subcommand: forces immediate token renewal on the calling pod (or via a synthetic invocation against the admin endpoint). Useful for incident response when the operator suspects a leaked token.

### Track D pytest tests

- [ ] T084 [W15D] [US2] Create `apps/ops-cli/tests/commands/test_vault.py` (NEW pytest test file): ~15 test cases covering migration dry-run + apply + idempotency + manifest emission + verify-migration + rollback path + error handling (Vault unreachable during migration, K8s Secret with malformed name, CAS conflict). Uses a `kind-cluster` fixture or mocks the K8s + Vault clients via `pytest-mock`.

---

## Phase 7: Track E — Admin Contracts + Observability

**Story goal**: 3 NEW `/api/v1/admin/vault/*` endpoints (consumed by UPD-036's UI page per FR-698 + by Track D's CLI per User Story 4); 4 Prometheus alert rules in observability bundle; Grafana dashboard.

### 3 admin REST endpoints (FR-698)

- [ ] T085 [W15E] [US4] Create `apps/control-plane/src/platform/admin/routers/vault.py` (NEW per plan.md design Track E day 6): FastAPI router with 3 endpoints — `GET /status` (returns `HealthStatus` schema), `POST /cache-flush` (clears the per-pod cache; emits audit-chain entry), `POST /connectivity-test` (synthetic write+read at `secret/data/musematic/{env}/_internal/connectivity-test/<random>`). All depend on `Depends(require_superadmin)` per Rule 30. Mounted at `/api/v1/admin/vault` in main.py.
- [ ] T086 [W15E] [US4] Create `apps/control-plane/src/platform/admin/services/vault_admin_service.py` (NEW): backing service aggregating: connection state from `VaultSecretProvider.health_check()`, auth method from settings, token expiry from the renewal-loop accountant, lease count from `client.sys.list_leases()` (if policy allows), recent failures from a ring buffer, per-BC read rates from Prometheus metric introspection (or via direct counter access per `prometheus_client.REGISTRY.collect()`), cache hit rate from the metrics counter.
- [ ] T087 [W15E] [US4] Create `apps/control-plane/src/platform/admin/schemas/vault.py` (NEW): Pydantic schemas — `VaultStatusResponse` (mirrors `HealthStatus` dataclass), `CacheFlushRequest` (`path: str | None`), `CacheFlushResponse` (`flushed_count: int`), `ConnectivityTestResponse` (`success: bool`, `latency_ms: float`, `error: str | None`). Verify NO `token` / `secret_id` / `kv_value` fields in any response per Rule 31.
- [ ] T088 [W15E] [US4] Modify `apps/control-plane/src/platform/main.py` to register the new `vault_admin_router` under `/api/v1/admin`. Verify the router's metadata flows into the OpenAPI spec (consumed by UPD-039's API Reference if it has landed).

### Audit-chain integration (Rule 30)

- [ ] T089 [W15E] [US4] Wire the `/cache-flush` and `/connectivity-test` endpoints to emit audit-chain entries via the existing UPD-024 audit-chain plumbing: events `vault.cache_flushed` and `vault.connectivity_test`. Each entry includes the admin principal, timestamp, action result. NEVER includes token/secret values per Rule 31.
- [ ] T090 [W15E] Author a static-analysis check at `scripts/check-admin-role-gates.py` (NEW per plan.md Constitutional Anchors row Rule 30): scans `apps/control-plane/src/platform/admin/routers/*.py`; for every method, asserts a `Depends(require_admin)` or `Depends(require_superadmin)` is in the dependencies. Exit code 1 on any missing gate. Wire into CI per the existing `check-secret-access.py` pattern from T025.

### Prometheus alert rules (FR-697)

- [ ] T091 [W15E] [US1, US5] Create `deploy/helm/observability/templates/alerts/vault.yaml` per plan.md research R8: a `PrometheusRule` resource with `metadata.name: platform-vault-alerts`, `spec.groups[0].name: platform.vault`, `spec.groups[0].interval: 1m`. 4 rules per spec Key Entities:
  - `VaultUnreachable` — `vault_auth_failure_total[5m] > 5 OR up{job=~"musematic-platform.*"} == 0`, for=1m, severity=critical.
  - `VaultAuthFailureRate` — `rate(vault_auth_failure_total[5m]) > 0.01`, for=5m, severity=warning.
  - `VaultLeaseRenewalFailing` — `vault_renewal_failure_total > 0`, for=any, severity=warning.
  - `VaultStalenessHigh` — `vault_serving_stale_total > 0`, for=5m, severity=warning.
- [ ] T092 [P] [W15E] Run `promtool check rules deploy/helm/observability/templates/alerts/vault.yaml` to validate; commit only if it passes.

### Grafana dashboard

- [ ] T093 [W15E] [US4] Create `deploy/helm/observability/dashboards/vault-overview.json` (NEW Grafana dashboard JSON per plan.md design Track E day 7): panels (sized 24-column grid):
  - Connection state (single-stat panel from `vault_lease_count` query)
  - Token expiry countdown (single-stat from `vault_token_expiry_seconds`)
  - Lease count (timeseries from `vault_lease_count`)
  - Per-BC read rate (multi-line timeseries from `rate(vault_read_total[1m])` grouped by `domain`)
  - Cache hit ratio (gauge from `vault_cache_hit_ratio`)
  - Auth failure rate (timeseries from `rate(vault_auth_failure_total[1m])` grouped by `auth_method`)
  - Staleness gauge (single-stat from `vault_serving_stale_total`)
  - Policy-denied counter (timeseries from `rate(vault_policy_denied_total[1m])` grouped by `path`)
- [ ] T094 [P] [W15E] Validate the dashboard JSON loads in a Grafana instance; verify all panel queries return live data on a kind cluster running the platform.

### UPD-036 contract handoff

- [ ] T095 [W15E] [US4] Document the 3 admin endpoint contracts at `specs/090-hashicorp-vault-integration/contracts/admin-vault-endpoints.md` (NEW file): full schemas, example requests/responses, error codes. Hand off to feature 086 (Administrator Workbench) as the integration spec for the `/admin/security/vault` UI page.
- [ ] T096 [W15E] [US4] Coordinate with UPD-036's owner: confirm the UI page is on their roadmap (or scheduled for a follow-up wave); document the coordination outcome in `specs/090-hashicorp-vault-integration/contracts/cross-feature-deps.md` (extends T004).
- [ ] T097 [W15E] If UPD-036 has not landed AND the `/admin/security/vault` UI page is deferred per T096, ensure `platform-cli vault status` is the documented operator-facing fallback per spec User Story 4. Update the CLI's help text to clarify it provides the same data the UI page would.

---

## Phase 8: E2E Coverage + Matrix CI

**Story goal**: 8 NEW E2E tests at `tests/e2e/suites/secrets/`; matrix CI runs J01 + J11 journey tests against `mock` / `kubernetes` / `vault` modes per spec SC-020.

### kind cluster + suite scaffolding

- [ ] T098 [W15F] [US1, US5] Modify `tests/e2e/cluster/kind-config.yaml` per plan.md research R10: append a new port mapping `containerPort: 30085`, `hostPort: ${PORT_VAULT}`, `protocol: TCP` to the control-plane node's `extraPortMappings` block. Update the kind-bootstrap script `tests/e2e/cluster/bootstrap.sh` to export `PORT_VAULT` (default 30085) and run `helm install vault deploy/helm/vault/ --namespace platform-security --create-namespace --values deploy/helm/vault/values-dev.yaml` after the platform install.
- [ ] T099 [W15F] [US1] Create `tests/e2e/suites/secrets/__init__.py` + `conftest.py` (NEW pytest fixtures): `vault_dev_pod` (waits for the dev pod's `vault status` to return ready), `vault_root_token` (reads the dev mode root token from the kind cluster), `kubernetes_secret_seed` (pre-populates K8s Secrets at canonical names for the migration test), `mock_mode_temp_file` (creates a `.vault-secrets.json` test fixture). All fixtures are `scope="session"` to avoid setup overhead.

### 8 E2E test files (per plan.md design Phase 6)

- [ ] T100 [W15F] [US1] Create `tests/e2e/suites/secrets/test_vault_round_trip.py`: 4 test functions covering `VaultSecretProvider.get/put/delete_version/list_versions/health_check` end-to-end against the kind dev-mode Vault pod. Verifies metric emission (queries Prometheus on `:9090/api/v1/query?query=vault_read_total`) per FR-697.
- [ ] T101 [P] [W15F] [US2] Create `tests/e2e/suites/secrets/test_kubernetes_mode.py`: 3 test functions covering `KubernetesSecretProvider` round-trip against a kind cluster's K8s API. Verifies the canonical-path → K8s-Secret-name mapping from T047.
- [ ] T102 [P] [W15F] [US1] Create `tests/e2e/suites/secrets/test_mock_mode_regression.py` per spec SC-020: 5 test functions covering the existing `MockSecretProvider` semantics (verify byte-for-byte parity with pre-UPD-040 `_resolve_mock` behaviour). Uses the `mock_mode_temp_file` fixture.
- [ ] T103 [P] [W15F] [US2] Create `tests/e2e/suites/secrets/test_migration_k8s_to_vault.py`: 6 test functions covering the migration CLI (dry-run, apply, idempotency re-run, manifest verification, rollback via mode-flag flip, malformed K8s Secret handling). Uses the `kubernetes_secret_seed` fixture.
- [ ] T104 [P] [W15F] [US3] Create `tests/e2e/suites/secrets/test_rotation_via_vault.py`: 4 test functions covering UPD-024 rotation flow via KV v2 versioning (rotate, verify v1+v2 both readable for dual-credential window, verify v1 destroyed at window expiry, verify audit-chain entry contains no plaintext). Uses the `RotatableSecretProvider` rewired in T012.
- [ ] T105 [P] [W15F] [US5] Create `tests/e2e/suites/secrets/test_vault_unreachable.py` per spec User Story 5 + FR-688: 5 test functions — (a) populate cache with 100 reads; (b) apply NetworkPolicy denying egress to Vault namespace; (c) verify cached reads continue for 60s; (d) verify stale reads serve up to 300s; (e) verify critical reads (login flow) fail with HTTP 503 after staleness window; (f) restore network; verify recovery within 5 minutes; verify alert fires + clears.
- [ ] T106 [P] [W15F] [US1] Create `tests/e2e/suites/secrets/test_auth_method_kubernetes.py`: 3 test functions covering kubernetes auth path (SA token rotation transparent, lease renewal at 50% TTL, SIGTERM lease revocation).
- [ ] T107 [P] [W15F] [US1] Create `tests/e2e/suites/secrets/test_auth_method_approle.py`: 3 test functions covering approle auth path (SecretID expiry handling, RoleID + SecretID login, lease renewal).

### Matrix CI

- [ ] T108 [W15F] [US1, US2, US5] Modify `.github/workflows/ci.yml` per plan.md design Phase 6 day 9: add a new matrix-CI job `journey-tests` with `strategy.matrix.secret_mode: [mock, kubernetes, vault]`. Each matrix entry sets `PLATFORM_VAULT_MODE` accordingly + runs the existing J01 (Administrator) + J11 (Security Officer) journey suites under `tests/e2e/journeys/`. Failure in any mode fails the PR. Reuses the kind-bootstrap script + parallel-execution flags from feature 071 / 085's harness. Estimated runtime: ~15 minutes per mode = ~45 minutes total (parallelized to ~20 minutes wall-clock with 3 GitHub runners).

---

## Phase 9: SC Verification + Documentation Polish

**Story goal**: All 20 spec SCs pass; UPD-039 docs auto-flow integration; release notes; final review.

### SC sweep

- [ ] T109 [W15G] Run the full SC verification sweep per plan.md design Phase 7 day 9 afternoon: SC-001 through SC-020. For each SC, document the actual measurement (e.g., SC-001's "30 minutes from `helm install`" — measured wall-clock time on a synthetic kind cluster; SC-010's "≥ 80% cache hit ratio within 5 minutes" — measured via Prometheus metric). Capture the verification record at `specs/090-hashicorp-vault-integration/contracts/sc-verification.md` (NEW file).

### FR document section 113

- [ ] T110 [W15G] [US1] Modify `docs/functional-requirements-revised-v6.md` per spec correction §6: append section 113 "HashiCorp Vault Integration" with FR-683 through FR-700 — verbatim text from spec.md "Functional Requirements" section. Insert after the existing FR-682 (verified during T001 inventory). Update the table of contents at the top of the FR doc to include section 113.
- [ ] T111 [W15G] Run UPD-039's `scripts/check-doc-references.py` (if UPD-039 has landed) against the modified FR doc to verify no broken FR references; if UPD-039 has not landed, manually grep for `FR-68[0-9]\|FR-69[0-9]\|FR-700` references in the docs tree and verify.

### Operator runbook library (UPD-039 / FR-617 integration)

- [ ] T112 [W15G] [US2] Create `docs/operator-guide/runbooks/vault-migration-from-k8s.md` (deliverable here if UPD-039 has not landed; otherwise UPD-039 owns and merges). Sections: Symptom (operator wants to adopt Vault), Diagnosis (verify current `PLATFORM_VAULT_MODE`), Remediation (step-by-step migration flow), Verification (`platform-cli vault verify-migration`), Rollback (mode-flag flip).
- [ ] T113 [P] [W15G] [US3] Create `docs/operator-guide/runbooks/vault-rotation.md`: rotation flow via UPD-024 + Vault KV v2 versioning.
- [ ] T114 [P] [W15G] [US4] Create `docs/operator-guide/runbooks/vault-cache-flush.md`: when + how to trigger cache flush (per-pod via CLI, all-pods via UI page or repeat CLI calls).
- [ ] T115 [P] [W15G] Create `docs/operator-guide/runbooks/vault-token-rotation.md`: forced token rotation during incident response (`platform-cli vault rotate-token`).

### Developer guide pages (UPD-039 integration)

- [ ] T116 [P] [W15G] Create `docs/developer-guide/secret-provider-protocol.md`: Protocol surface (5 methods), 3 modes (mock/kubernetes/vault), error taxonomy, when to use `critical=True`. Code examples.
- [ ] T117 [P] [W15G] Create `docs/developer-guide/adding-a-new-secret.md`: recipe for adding a new BC-owned secret — choose canonical path, add column to model, wire callsite, add policy entry to `deploy/vault/policies/platform-{bc}.hcl`, regenerate auto-docs.

### Auto-doc verification (UPD-039 / FR-610 + FR-700 integration)

- [ ] T118 [W15G] If UPD-039 has landed, run `python scripts/generate-env-docs.py` to verify the new `PLATFORM_VAULT_*` env vars are auto-listed with the `sensitive` classification per FR-700. Verify the deny-list logic from UPD-039's script correctly classifies `PLATFORM_VAULT_TOKEN`, `PLATFORM_VAULT_APPROLE_SECRET_ID`, `PLATFORM_VAULT_APPROLE_ROLE_ID` as `sensitive`. CI fails any drift. If UPD-039 has not landed, document the requirement so it's wired in when UPD-039 lands.

### Release notes + final review

- [ ] T119 [W15G] Create `docs/release-notes/v1.3.0/vault-integration.md` (or extend the existing v1.3.0 release notes file): document the new `PLATFORM_VAULT_*` env vars, the deprecated `CONNECTOR_VAULT_MODE` alias (one-release deprecation), the migration tool, the 3 sizing presets, the breaking-change notice that `notifications/channel_router.py:SecretProvider` is re-exported (deprecated; remove in v1.4.0).
- [ ] T120 [W15G] Final review pass: address PR review feedback; run `pytest apps/control-plane/`, `go test ./services/...`, `pytest tests/e2e/suites/secrets/` one final time; verify all 20 SCs pass; verify the matrix CI green for all 3 modes; verify zero plaintext-secret regex hits in 24-hour kind-cluster log capture per User Story 1 acceptance scenario 5; merge.

---

## Dependencies & Execution Order

### Phase Dependencies

- **W15.0 Setup (T001-T004)**: No dependencies — can start immediately.
- **W15A Track A SecretProvider (T005-T028)**: Depends on W15.0 — KEYSTONE — blocks W15B / W15D / W15E.
- **W15B Track B Vault clients (T029-T053)**: Depends on W15A T005-T010 (Protocol + MockSecretProvider available); can start mid-Track-A. Python (T029-T048) and Go (T049-T053) are parallel.
- **W15C Track C Helm sub-chart (T054-T073)**: Fully INDEPENDENT — can start day 1 in parallel with W15.0 + W15A.
- **W15D Track D Migration tooling (T074-T084)**: Depends on W15B T031-T032 (`VaultSecretProvider.get/put` available) and T046-T047 (`KubernetesSecretProvider` available).
- **W15E Track E Admin contracts + observability (T085-T097)**: Depends on W15A T005 (Protocol) + W15B T032 (`health_check`).
- **W15F Phase 6 E2E + matrix CI (T098-T108)**: Depends on ALL OTHER PHASES — convergent.
- **W15G Phase 7 Polish (T109-T120)**: Depends on W15F.

### User Story Dependencies

- **US1 (P1 — HA install)**: T001-T028 (Track A) + T029-T053 (Track B) + T054-T073 (Track C) + T100, T106-T107 (E2E). Independently testable post-T108.
- **US2 (P1 — migration)**: T046-T047 (K8s mode) + T074-T084 (Track D) + T101, T103 (E2E). Depends on US1 backend.
- **US3 (P2 — rotation)**: T012 (RotatableSecretProvider rewire) + T104 (E2E rotation). Depends on US1.
- **US4 (P2 — admin status)**: T081-T083 (CLI) + T085-T097 (Track E). Depends on US1.
- **US5 (P1 — graceful degradation)**: T040-T041 (stale-read + critical-path refusal) + T091 (alert) + T105 (E2E). Depends on US1.

### Within Each Track

- Within Track A: T005 (Protocol module) → T006-T007 (re-export) → T008-T010 (MockSecretProvider extraction) → T011-T017 (rewires) → T018-T022 (Go interface) → T023-T026 (CI deny-list) → T027-T028 (VaultSettings).
- Within Track B Python: T029-T030 (deps + pin) → T031-T032 (core) → T033-T035 (auth methods, parallel) → T036-T038 (token lifecycle) → T039-T042 (cache) → T043-T045 (metrics + log discipline) → T046-T047 (K8s mode) → T048 (tests).
- Within Track B Go: T049 (deps) → T050 (core) → T051-T053 (auth + cache + metrics, parallel).
- Within Track C: T054-T056 (chart scaffolding) → T057-T060 (preset values, parallel) → T061-T063 (post-install Jobs, parallel) → T064-T070 (HCL policies, parallel) → T071-T073 (platform chart integration, parallel).
- Within Track D: T074-T075 (Typer scaffolding) → T076-T078 (migration core) → T079-T080 (manifest + verify) → T081-T083 (utility subcommands, parallel) → T084 (tests).
- Within Track E: T085-T088 (REST endpoints) → T089-T090 (audit + role gates) → T091-T092 (alerts) → T093-T094 (dashboard) → T095-T097 (UPD-036 handoff).

### Parallel Opportunities

- **Day 1**: T001-T004 (Setup, all parallel) + T005 (Track A start) + T054 (Track C start, fully independent).
- **Day 2-3**: Track A T006-T028 sequential; Track C T055-T070 highly parallel (many [P] tasks across 3-4 devs).
- **Day 4-5**: Track A complete; Track B Python T029-T048 + Track B Go T049-T053 in parallel (different devs).
- **Day 6-7**: Track D T074-T084 + Track E T085-T097 in parallel (depend on Track A+B subset).
- **Day 8-9**: Phase 6 E2E (sequential — depends on ALL other tracks).
- **Day 10-12**: Phase 7 Polish (mostly parallel — many runbook/developer-guide pages can be authored simultaneously).

---

## Implementation Strategy

### MVP First (User Story 1 Only — HA Install)

1. Complete Phase 1 (W15.0) Setup.
2. Complete Phase 2 (W15A) Track A — KEYSTONE.
3. Complete Phase 3 + Phase 4 (W15B) Track B — Python + Go.
4. Complete Phase 5 (W15C) Track C — Helm sub-chart.
5. Run T100 + T106-T107 (E2E for US1).
6. **STOP and VALIDATE**: a fresh kind cluster reaches `vault.mode=ha` working state in ≤ 30 minutes per SC-001.

### Incremental Delivery

1. MVP (US1) → demo HA install + write/read a secret.
2. + US2 (Track D) → demo migration tool on a synthetic K8s-Secret-populated cluster.
3. + US5 (T040-T042 stale-read fallback + T105 E2E) → demo graceful degradation under network partition.
4. + US3 (T012 rotation rewire) + US4 (T081-T097 admin contracts) → demo rotation + status panel.
5. Full feature complete after Phase 6 (E2E) + Phase 7 (Polish).

### Parallel Team Strategy

With 3 devs:

- **Dev A (Track A + Track D)**: Day 1-3 Track A keystone; Day 6-7 Track D migration tooling; Day 8-9 Phase 6 E2E lead; Day 10-12 Phase 7 polish.
- **Dev B (Track B Python + Track E)**: Day 4-5 Track B Python + cache + metrics; Day 6-7 Track E admin contracts; Day 8-9 Phase 6 E2E support.
- **Dev C (Track B Go + Track C)**: Day 1-2 Track C Helm sub-chart (independent — can start day 1); Day 4-5 Track B Go mirror; Day 8-9 Phase 6 E2E support.

Wall-clock: **5-6 days for MVP** (US1 only); **8-10 days for full feature** with 3 devs in parallel.

---

## Notes

- [P] tasks = different files, no dependencies; safe to parallelize across devs.
- [Story] label maps task to specific user story for traceability (US1-US5).
- [W15X] label maps task to wave-15 sub-track (W15.0 / W15A-G).
- The plan's effort estimate (15-17 dev-days) supersedes the brownfield's 10-day understatement; tasks below total ~120 entries, consistent with that estimate.
- Track A is the keystone; rushing it risks rework in Tracks B/D/E. Plan ≥ 3 dev-days.
- The `mock` mode regression test (T009 + T102) is the canary for SC-020; run it on every PR.
- Constitutional Rule 31 (no plaintext in logs/manifests) is enforced both by static analysis (T044-T045) and by code review on every commit touching Track B / Track D.
- The 7 BC HCL policies (T064-T070) are the canonical contract for FR-695's deny-by-default discipline. Each policy file is reviewed by the BC owner during PR.
- Per-BC ServiceAccount separation is OUT OF SCOPE for MVP per design D9; planned as a follow-up feature (UPD-042 or later).
- Cluster-wide cache flush via Kafka broadcast is OUT OF SCOPE per Phase 0 R12; per-pod flush via CLI iteration is the workaround.
- The deprecated `CONNECTOR_VAULT_MODE` alias and the `notifications/channel_router.py:SecretProvider` re-export are removed in v1.4.0 (one release after UPD-040); the removal is announced in T119's release notes.
