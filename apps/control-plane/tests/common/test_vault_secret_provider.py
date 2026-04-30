from __future__ import annotations

import base64
from platform.common import secret_provider as module
from platform.common.secret_provider import (
    CredentialPolicyDeniedError,
    CredentialUnavailableError,
    HealthStatus,
    KubernetesSecretProvider,
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
    assert (
        k8s_secret_name_to_vault_path("musematic-dev-model-providers/openai".replace("/", "-"))
        == "secret/data/musematic/dev/model-providers/openai"
    )


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
