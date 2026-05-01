from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from platform.admin.schemas.vault import (
    CacheFlushRequest,
    TokenRotationRequest,
)
from platform.admin.services import vault_admin_service as module
from platform.admin.services.vault_admin_service import VaultAdminService, health_status_to_dict
from platform.common.config import PlatformSettings
from platform.common.secret_provider import HealthStatus, InvalidVaultPathError
from types import SimpleNamespace

import pytest


class _ProviderStub:
    def __init__(self) -> None:
        self.health = HealthStatus(
            status="green",
            auth_method="token",
            token_expiry_at=datetime(2026, 5, 1, tzinfo=UTC),
            lease_count=3,
            recent_failures=["RuntimeError: previous"],
            cache_hit_rate=0.75,
        )
        self.flushed: list[str | None] = []
        self.put_values: dict[str, dict[str, str]] = {}
        self.deleted: list[tuple[str, int]] = []
        self._authenticated = True
        self._renewal_task = SimpleNamespace(cancel=lambda: None)

    async def health_check(self) -> HealthStatus:
        return self.health

    async def flush_cache(self, path: str | None = None) -> int:
        self.flushed.append(path)
        return 5

    async def put(self, path: str, values: dict[str, str]) -> None:
        self.put_values[path] = values

    async def get(self, path: str, key: str = "value", *, critical: bool = False) -> str:
        assert critical
        return self.put_values[path][key]

    async def list_versions(self, path: str) -> list[int]:
        assert path in self.put_values
        return [1, 3, 2]

    async def delete_version(self, path: str, version: int) -> None:
        self.deleted.append((path, version))


class _FailingProvider(_ProviderStub):
    async def get(self, path: str, key: str = "value", *, critical: bool = False) -> str:
        del path, key, critical
        raise RuntimeError("vault unavailable")


class _Sample:
    def __init__(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        self.name = name
        self.value = value
        self.labels = labels or {}


class _Metric:
    def __init__(self, *samples: _Sample) -> None:
        self.samples = list(samples)


class _Registry:
    def collect(self) -> list[_Metric]:
        return [
            _Metric(
                _Sample("vault_read_total", 2, {"domain": "oauth"}),
                _Sample("vault_read_total", 3, {"domain": "oauth"}),
                _Sample("vault_auth_failure_total", 1, {"auth_method": "token"}),
                _Sample("vault_policy_denied_total", 4, {"path": "secret/data/x"}),
                _Sample("vault_serving_stale_total", 5),
                _Sample("vault_renewal_success_total", 6),
                _Sample("vault_renewal_failure_total", 7),
                _Sample("vault_cache_hit_total", 8),
                _Sample("vault_cache_miss_total", 9),
                _Sample("ignored", 99),
            )
        ]


@pytest.mark.asyncio
async def test_vault_admin_status_flush_connectivity_and_rotation(monkeypatch) -> None:
    provider = _ProviderStub()
    settings = PlatformSettings(vault={"mode": "vault"})
    service = VaultAdminService(provider, settings)
    monkeypatch.setattr(module, "REGISTRY", _Registry())
    monkeypatch.setenv("PLATFORM_ENVIRONMENT", "ci")

    status = await service.status()
    assert status.status == "green"
    assert status.mode == "vault"
    assert status.read_counts_by_domain == {"oauth": 5.0}
    assert status.auth_failure_counts_by_method == {"token": 1.0}
    assert status.policy_denied_counts_by_path == {"secret/data/x": 4.0}
    assert status.serving_stale_total == 5.0
    assert status.renewal_success_total == 6.0
    assert status.renewal_failure_total == 7.0
    assert status.cache_hit_total == 8.0
    assert status.cache_miss_total == 9.0

    flushed = await service.flush_cache(
        CacheFlushRequest(
            path="secret/data/musematic/dev/oauth/google",
            pod="api-0",
            all_pods=True,
        )
    )
    assert flushed.flushed_count == 5
    assert provider.flushed == ["secret/data/musematic/dev/oauth/google"]
    with pytest.raises(InvalidVaultPathError):
        await service.flush_cache(CacheFlushRequest(path="not/canonical"))

    connectivity = await service.connectivity_test()
    assert connectivity.success
    assert provider.deleted
    assert provider.deleted[0][1] == 3
    assert next(iter(provider.put_values)).startswith(
        "secret/data/musematic/ci/_platform/_internal/"
    )

    rotated = await service.rotate_token(TokenRotationRequest(pod="api-0"))
    assert rotated.success
    assert rotated.pod == "api-0"
    assert provider._authenticated is False


@pytest.mark.asyncio
async def test_vault_admin_error_and_fallback_paths(monkeypatch) -> None:
    settings = PlatformSettings(vault={"mode": "mock"})
    service = VaultAdminService(_FailingProvider(), settings)
    monkeypatch.setattr(module, "REGISTRY", None)
    monkeypatch.setenv("ENV", "definitely-not-valid")

    assert (await service.status()).read_counts_by_domain == {}
    assert service._environment() == "dev"
    failed = await service.connectivity_test()
    assert not failed.success
    assert "RuntimeError" in (failed.error or "")

    provider = _ProviderStub()

    async def no_versions(_path: str) -> list[int]:
        return []

    provider.list_versions = no_versions  # type: ignore[method-assign]
    await VaultAdminService(provider, settings)._best_effort_delete_latest(
        "secret/data/musematic/dev/oauth/google"
    )
    assert provider.deleted == []

    health = HealthStatus(status="yellow", auth_method="mock", error="slow")
    assert health_status_to_dict(health) == {
        "status": "yellow",
        "auth_method": "mock",
        "token_expiry_at": None,
        "lease_count": None,
        "recent_failures": [],
        "cache_hit_rate": 0.0,
        "error": "slow",
    }

    task = asyncio.create_task(asyncio.sleep(30))
    provider._renewal_task = task
    try:
        await VaultAdminService(provider, settings).rotate_token(TokenRotationRequest())
        assert task.cancelled() or task.cancelling()
    finally:
        task.cancel()
