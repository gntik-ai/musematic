from __future__ import annotations

import base64
import re
from datetime import timedelta
from email.utils import format_datetime
from platform.common import secret_provider as module
from platform.common.secret_provider import (
    CredentialPolicyDeniedError,
    CredentialUnavailableError,
    HealthStatus,
    InvalidVaultPathError,
    KubernetesSecretProvider,
    MockSecretProvider,
    VaultSecretProvider,
    k8s_secret_name_to_vault_path,
    vault_log_processor,
    vault_path_to_k8s_secret_name,
)
from types import SimpleNamespace

import pytest


def _settings(**overrides):
    values = {
        "addr": "http://vault.test",
        "namespace": "",
        "auth_method": "token",
        "token": "root",
        "kv_mount": "secret",
        "retry_timeout_seconds": 1,
        "retry_attempts": 3,
        "cache_ttl_seconds": 60,
        "cache_max_staleness_seconds": 300,
        "lease_renewal_threshold": 0.5,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _FakeKVv2:
    def __init__(self) -> None:
        self.store = {"musematic/dev/oauth/google": {1: {"value": "google-secret"}}}
        self.fail_reads = False
        self.forbid_reads = False
        self.destroyed: list[tuple[str, list[int]]] = []

    def read_secret_version(self, *, path, version=None, mount_point):
        assert mount_point == "secret"
        if self.forbid_reads:
            raise module.hvac_exceptions.Forbidden("denied")
        if self.fail_reads:
            raise RuntimeError("vault down")
        versions = self.store[path]
        selected = version or max(versions)
        return {"data": {"data": versions[selected]}}

    def create_or_update_secret(self, *, path, secret, mount_point, cas=None):
        assert mount_point == "secret"
        versions = self.store.setdefault(path, {})
        current = max(versions) if versions else 0
        assert cas in {None, current}
        versions[current + 1] = dict(secret)

    def destroy_secret_versions(self, *, path, versions, mount_point):
        assert mount_point == "secret"
        self.destroyed.append((path, list(versions)))

    def read_secret_metadata(self, *, path, mount_point):
        assert mount_point == "secret"
        versions = self.store.get(path, {})
        current = max(versions) if versions else 0
        return {
            "data": {
                "current_version": current,
                "versions": {str(version): {} for version in versions},
            }
        }


class _FakeVaultClient:
    def __init__(self) -> None:
        self.kv = _FakeKVv2()
        self.token = ""
        self.revoked = False
        self.secrets = SimpleNamespace(kv=SimpleNamespace(v2=self.kv))
        self.auth = SimpleNamespace(
            token=SimpleNamespace(
                lookup_self=lambda: {"data": {"ttl": 3600}},
                renew_self=lambda: {"auth": {"lease_duration": 3600}},
                revoke_self=self._revoke,
            ),
            kubernetes=SimpleNamespace(
                login=lambda role, jwt: {
                    "auth": {"client_token": f"{role}:{jwt}", "lease_duration": 3600}
                }
            ),
            approle=SimpleNamespace(
                login=lambda role_id, secret_id: {
                    "auth": {"client_token": f"{role_id}:{secret_id}", "lease_duration": 3600}
                }
            ),
        )
        self.sys = SimpleNamespace(
            read_health_status=lambda method="GET": {"sealed": False},
            list_leases=lambda prefix="": {"data": {"keys": ["one", "two"]}},
        )

    def _revoke(self) -> None:
        self.revoked = True


class _NoWritePath:
    @property
    def parent(self) -> _NoWritePath:
        return self

    def mkdir(self, **_kwargs) -> None:
        raise PermissionError("readonly")


@pytest.fixture
def fake_vault(monkeypatch):
    client = _FakeVaultClient()
    monkeypatch.setattr(module.hvac, "Client", lambda **_kwargs: client)
    return client


async def _close(provider: VaultSecretProvider) -> None:
    task = getattr(provider, "_renewal_task", None)
    if task is not None:
        task.cancel()


def test_vault_kubernetes_secret_name_mapping_round_trips() -> None:
    path = "secret/data/musematic/production/oauth/google"

    name = vault_path_to_k8s_secret_name(path)

    assert name == "musematic-production-oauth-google"
    assert k8s_secret_name_to_vault_path(name) == path
    nested_path = "secret/data/musematic/dev/oauth/google/client-secret"
    nested_name = vault_path_to_k8s_secret_name(nested_path)
    assert nested_name == ("musematic-dev-oauth-x-676f6f676c652f636c69656e742d736563726574")
    assert re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", nested_name)
    assert k8s_secret_name_to_vault_path(nested_name) == nested_path
    assert (
        k8s_secret_name_to_vault_path("musematic-dev-model-providers/openai".replace("/", "-"))
        == "secret/data/musematic/dev/model-providers/openai"
    )


def test_metric_helpers_and_invalid_secret_name_edges(monkeypatch) -> None:
    noop = module._NoopMetric()
    assert noop.labels("domain") is noop
    assert noop.inc() is None
    assert noop.set(1) is None

    monkeypatch.setattr(module, "REGISTRY", None)
    assert isinstance(module._metric(None, "no_metric", "documentation"), module._NoopMetric)

    existing_metric = object()

    def duplicate_metric(*_args, **_kwargs):
        raise ValueError("duplicated timeseries")

    monkeypatch.setattr(
        module,
        "REGISTRY",
        SimpleNamespace(_names_to_collectors={"existing_total": existing_metric}),
    )
    assert module._metric(duplicate_metric, "existing", "documentation") is existing_metric
    event = {"event": "vault.read", "path": "secret/data/musematic/dev/oauth/google"}
    assert vault_log_processor(None, "info", event) is event

    with pytest.raises(InvalidVaultPathError):
        k8s_secret_name_to_vault_path("not-musematic-dev-oauth-google")
    with pytest.raises(InvalidVaultPathError):
        k8s_secret_name_to_vault_path("musematic-prod-oauth-google")
    with pytest.raises(InvalidVaultPathError):
        k8s_secret_name_to_vault_path("musematic-dev-unknown-google")
    assert module._resource_from_k8s_suffix("x-not-hex") == "x-not-hex"


def test_validate_secret_path_accepts_tenant_and_platform_scoped_paths() -> None:
    module.validate_secret_path("secret/data/musematic/dev/oauth/google/client-secret")
    module.validate_secret_path("secret/data/musematic/dev/tenants/acme/oauth/google/client-secret")
    module.validate_secret_path("secret/data/musematic/dev/_platform/_internal/cert-manager")

    with pytest.raises(InvalidVaultPathError):
        module.validate_secret_path("secret/data/musematic/dev/tenants/Api/oauth/client")

    assert (
        vault_path_to_k8s_secret_name(
            "secret/data/musematic/dev/tenants/acme/oauth/google/client-secret"
        )
        == "musematic-dev-oauth-x-676f6f676c652f636c69656e742d736563726574"
    )


@pytest.mark.asyncio
async def test_mock_provider_default_fallback_and_noop_version_paths(monkeypatch, tmp_path) -> None:
    path = "secret/data/musematic/dev/oauth/google"
    fallback = tmp_path / "fallback-secrets.json"
    fallback.write_text(
        '{"secret/data/musematic/dev/oauth/google": {"value": "fallback"}}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MUSEMATIC_MOCK_SECRETS_FILE", str(fallback))
    provider = MockSecretProvider(SimpleNamespace(connectors=SimpleNamespace()))

    assert await provider.get(path) == "fallback"
    assert await provider.flush_cache(path) == 0
    await provider.delete_version(path, 99)

    provider._candidate_paths = lambda: [_NoWritePath()]  # type: ignore[method-assign]
    with pytest.raises(PermissionError):
        await provider.put(path, {"value": "blocked"})


@pytest.mark.asyncio
async def test_mock_provider_noncanonical_write_and_non_mapping_file_edges(
    monkeypatch,
    tmp_path,
) -> None:
    legacy_file = tmp_path / "legacy-secrets.json"
    legacy_provider = MockSecretProvider(
        SimpleNamespace(connectors=SimpleNamespace(vault_mock_secrets_file=str(legacy_file))),
        validate_paths=False,
    )

    await legacy_provider.put("legacy/path", {"value": "legacy"})

    assert await legacy_provider.get("legacy/path") == "legacy"
    assert await legacy_provider.list_versions("legacy/path") == [1]

    list_file = tmp_path / "list-secrets.json"
    list_file.write_text("[]", encoding="utf-8")
    monkeypatch.setenv(
        "CONNECTOR_SECRET_VALUE_SECRET_DATA_MUSEMATIC_DEV_OAUTH_GOOGLE",
        "from-env",
    )
    provider = MockSecretProvider(
        SimpleNamespace(connectors=SimpleNamespace(vault_mock_secrets_file=str(list_file))),
    )
    assert await provider.get("secret/data/musematic/dev/oauth/google") == "from-env"


@pytest.mark.asyncio
async def test_vault_provider_reads_and_caches(fake_vault) -> None:
    provider = VaultSecretProvider(_settings())
    try:
        first = await provider.get("secret/data/musematic/dev/oauth/google")
        fake_vault.kv.store["musematic/dev/oauth/google"][1]["value"] = "changed"
        second = await provider.get("secret/data/musematic/dev/oauth/google")

        assert first == "google-secret"
        assert second == "google-secret"
    finally:
        await _close(provider)


@pytest.mark.asyncio
async def test_vault_provider_serves_stale_when_noncritical(fake_vault) -> None:
    provider = VaultSecretProvider(_settings(cache_ttl_seconds=0))
    try:
        assert await provider.get("secret/data/musematic/dev/oauth/google") == "google-secret"
        fake_vault.kv.fail_reads = True

        assert await provider.get("secret/data/musematic/dev/oauth/google") == "google-secret"
        with pytest.raises(CredentialUnavailableError):
            await provider.get("secret/data/musematic/dev/oauth/google", critical=True)
    finally:
        await _close(provider)


@pytest.mark.asyncio
async def test_vault_provider_put_list_delete_and_versions(fake_vault) -> None:
    provider = VaultSecretProvider(_settings())
    try:
        await provider.put("secret/data/musematic/dev/oauth/google", {"value": "new"})
        assert await provider.list_versions("secret/data/musematic/dev/oauth/google") == [1, 2]
        assert (
            await provider.get_version("secret/data/musematic/dev/oauth/google", 1)
            == "google-secret"
        )
        assert await provider.get("secret/data/musematic/dev/oauth/google") == "new"

        await provider.delete_version("secret/data/musematic/dev/oauth/google", 1)

        assert fake_vault.kv.destroyed == [("musematic/dev/oauth/google", [1])]
    finally:
        await _close(provider)


@pytest.mark.asyncio
async def test_vault_provider_policy_denied_and_health(fake_vault) -> None:
    provider = VaultSecretProvider(_settings())
    try:
        health = await provider.health_check()
        assert isinstance(health, HealthStatus)
        assert health.status == "green"
        assert health.lease_count == 2

        fake_vault.kv.forbid_reads = True
        with pytest.raises(CredentialPolicyDeniedError):
            await provider.get("secret/data/musematic/dev/oauth/google")
    finally:
        await _close(provider)


@pytest.mark.asyncio
async def test_vault_provider_authentication_and_cache_helper_edges(fake_vault, tmp_path) -> None:
    token_path = tmp_path / "token"
    token_path.write_text("jwt-token\n", encoding="utf-8")
    provider = VaultSecretProvider(
        _settings(
            auth_method="kubernetes",
            service_account_token_path=str(token_path),
            kubernetes_role="status-page",
        )
    )
    try:
        await provider._ensure_authenticated()
        assert fake_vault.token == "status-page:jwt-token"
        await provider._ensure_authenticated()
    finally:
        await _close(provider)

    secret_id_path = tmp_path / "secret-id"
    secret_id_path.write_text("approle-secret\n", encoding="utf-8")
    approle_provider = VaultSecretProvider(
        _settings(
            auth_method="approle",
            approle_role_id="role-id",
            approle_secret_id_secret_ref=str(secret_id_path),
        )
    )
    try:
        await approle_provider._ensure_authenticated()
        assert fake_vault.token == "role-id:approle-secret"
    finally:
        await _close(approle_provider)

    token_provider = VaultSecretProvider(_settings(token=""))
    try:
        with pytest.raises(CredentialUnavailableError):
            await token_provider._authenticate_token()
    finally:
        await _close(token_provider)

    helper_provider = VaultSecretProvider(_settings(auth_method="unsupported"))
    try:
        with pytest.raises(CredentialUnavailableError):
            await helper_provider._ensure_authenticated()
        with pytest.raises(CredentialUnavailableError):
            helper_provider._apply_auth_response({"auth": {}})
        with pytest.raises(InvalidVaultPathError):
            helper_provider._split_kv_path("kv/data/musematic/dev/oauth/google")

        helper_provider._token_expiry_at = None
        helper_provider._set_token_expiry_metric()
        helper_provider._renewal_task = SimpleNamespace(done=lambda: False, cancel=lambda: None)
        helper_provider._start_renewal_loop()
        helper_provider._cache_ttl_seconds = 0
        helper_provider._cache_set("secret#value", "cached")
        assert helper_provider._cache_get("secret#value") is None
        helper_provider._cache_max_staleness_seconds = 0
        helper_provider._stale_cache["secret#value"] = (
            module._now() - timedelta(seconds=5),
            "stale",
        )
        assert helper_provider._stale_value("secret#value") is None
        assert helper_provider._stale_age_seconds("secret#value") >= 5
        helper_provider._stale_cache.clear()
        assert helper_provider._stale_age_seconds("secret#value") == 0
        helper_provider._record_cache_hit()
        helper_provider._record_cache_miss()
        assert helper_provider._cache_hit_rate() == 0.5
    finally:
        await _close(helper_provider)


@pytest.mark.asyncio
async def test_vault_provider_remaining_low_level_edges(fake_vault, monkeypatch) -> None:
    monkeypatch.setattr(module, "hvac", None)
    with pytest.raises(RuntimeError, match="hvac is required"):
        VaultSecretProvider(_settings())
    monkeypatch.setattr(module, "hvac", SimpleNamespace(Client=lambda **_kwargs: fake_vault))

    provider = VaultSecretProvider(_settings())
    try:
        provider._cache_set("secret/data/musematic/dev/oauth/google#value", "cached")
        provider._stale_cache["secret/data/musematic/dev/oauth/google#value"] = (
            module._now(),
            "stale",
        )
        provider._last_successful_read["secret/data/musematic/dev/oauth/google#value"] = (
            module._now()
        )
        assert await provider.flush_cache() == 2
        assert provider._cache == {}
        assert provider._stale_cache == {}

        if module.hvac_exceptions is not None:
            with pytest.raises(CredentialUnavailableError):
                provider._translate_vault_error(module.hvac_exceptions.InvalidPath("missing"), "x")

        provider._on_sigterm(15, None)
        assert fake_vault.revoked

        fake_vault.sys.list_leases = lambda prefix="": (_ for _ in ()).throw(
            RuntimeError("leases down")
        )
        assert await provider._read_lease_count() is None

        provider._cache.clear()
        for index in range(1001):
            provider._cache_set(f"key-{index}", "value")
        assert len(provider._cache) == 1000
        assert "key-0" not in provider._cache

        future = (module._now() + timedelta(seconds=60)).replace(tzinfo=None)
        provider._detect_clock_skew({"headers": {"Date": format_datetime(future)}})
        assert abs(provider._clock_skew_seconds) > 30
    finally:
        await _close(provider)


@pytest.mark.asyncio
async def test_kubernetes_secret_provider_import_fallback_path(monkeypatch) -> None:
    loaded = {"kube_config": False}

    class ConfigModule:
        @staticmethod
        def load_incluster_config() -> None:
            raise RuntimeError("not in a pod")

        @staticmethod
        async def load_kube_config() -> None:
            loaded["kube_config"] = True

    monkeypatch.setitem(
        __import__("sys").modules,
        "kubernetes_asyncio",
        SimpleNamespace(client=SimpleNamespace(CoreV1Api=lambda: "api"), config=ConfigModule),
    )
    provider = KubernetesSecretProvider(_settings(), api=None)

    assert await provider._get_api() == "api"
    assert await provider._get_api() == "api"
    assert loaded["kube_config"]


@pytest.mark.asyncio
async def test_vault_provider_read_write_and_health_error_edges(fake_vault, monkeypatch) -> None:
    path = "secret/data/musematic/dev/oauth/google"
    provider = VaultSecretProvider(_settings(cache_ttl_seconds=0, cache_max_staleness_seconds=-1))
    try:
        assert await provider.get(path) == "google-secret"
        fake_vault.kv.fail_reads = True
        with pytest.raises(CredentialUnavailableError):
            await provider.get(path)
        fake_vault.kv.fail_reads = False

        missing_key_path = "secret/data/musematic/dev/oauth/missing-key"
        fake_vault.kv.store["musematic/dev/oauth/missing-key"] = {1: {"other": "value"}}
        with pytest.raises(CredentialUnavailableError):
            await provider.get(missing_key_path)

        def metadata_down(**_kwargs):
            raise RuntimeError("metadata down")

        monkeypatch.setattr(fake_vault.kv, "read_secret_metadata", metadata_down)
        with pytest.raises(RuntimeError, match="metadata down"):
            await provider._read_metadata(path)
        assert await provider._latest_version(path) is None

        def write_down(**_kwargs):
            raise RuntimeError("cas conflict")

        monkeypatch.setattr(fake_vault.kv, "create_or_update_secret", write_down)
        with pytest.raises(CredentialUnavailableError):
            await provider.put(path, {"value": "new"})

        fake_vault.sys.read_health_status = lambda method="GET": (_ for _ in ()).throw(
            RuntimeError("sealed")
        )
        health = await provider.health_check()
        assert health.status == "red"
        assert "sealed" in (health.error or "")
    finally:
        await _close(provider)


def test_vault_log_processor_rejects_secret_fields() -> None:
    with pytest.raises(AssertionError):
        vault_log_processor(None, "info", {"event": "vault.authenticated", "token": "x"})


class _K8sSecret:
    def __init__(self, data):
        self.data = data


class _K8sApi:
    def __init__(self) -> None:
        self.patched = None
        self.created = None

    async def read_namespaced_secret(self, *, name, namespace):
        assert name == "musematic-dev-oauth-google"
        assert namespace == "platform"
        return _K8sSecret({"value": base64.b64encode(b"k8s-secret").decode("ascii")})

    async def patch_namespaced_secret(self, *, name, namespace, body):
        self.patched = (name, namespace, body.data)

    async def create_namespaced_secret(self, *, namespace, body):
        self.created = (namespace, body.data)

    async def list_namespaced_secret(self, *, namespace, limit):
        assert namespace == "platform"
        assert limit == 1
        return SimpleNamespace(items=[])


class _K8sCreateApi(_K8sApi):
    async def patch_namespaced_secret(self, *, name, namespace, body):
        del name, namespace, body
        raise RuntimeError("missing")


class _K8sMissingApi(_K8sApi):
    async def read_namespaced_secret(self, *, name, namespace):
        del name, namespace
        return _K8sSecret({})

    async def list_namespaced_secret(self, *, namespace, limit):
        del namespace, limit
        raise RuntimeError("api unavailable")


@pytest.mark.asyncio
async def test_kubernetes_secret_provider_round_trip_with_fake_api() -> None:
    api = _K8sApi()
    provider = KubernetesSecretProvider(_settings(), api=api)
    path = "secret/data/musematic/dev/oauth/google"

    assert await provider.get(path) == "k8s-secret"
    await provider.put(path, {"value": "written"})
    assert await provider.list_versions(path) == [1]
    assert (await provider.health_check()).status == "green"
    assert api.patched is not None


@pytest.mark.asyncio
async def test_kubernetes_secret_provider_writes_nested_paths_with_safe_names() -> None:
    api = _K8sApi()
    provider = KubernetesSecretProvider(_settings(), api=api)
    path = "secret/data/musematic/dev/oauth/google/client-secret"

    await provider.put(path, {"value": "written"})

    assert api.patched is not None
    assert api.patched[0] == vault_path_to_k8s_secret_name(path)
    assert "_" not in api.patched[0]


@pytest.mark.asyncio
async def test_kubernetes_secret_provider_error_and_create_paths() -> None:
    path = "secret/data/musematic/dev/oauth/google"
    create_api = _K8sCreateApi()
    create_provider = KubernetesSecretProvider(_settings(), api=create_api)

    await create_provider.put(path, {"value": "created"})
    assert create_api.created == ("platform", {"value": base64.b64encode(b"created").decode()})
    assert await create_provider.flush_cache(path) == 0
    await create_provider.delete_version(path, 1)

    missing_provider = KubernetesSecretProvider(_settings(), api=_K8sMissingApi())
    with pytest.raises(CredentialUnavailableError):
        await missing_provider.get(path)
    assert (await missing_provider.health_check()).status == "red"
