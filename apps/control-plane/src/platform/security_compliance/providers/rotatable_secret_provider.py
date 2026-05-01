from __future__ import annotations

from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.secret_provider import MockSecretProvider, SecretProvider
from platform.common.tenant_context import current_tenant
from platform.tenants.vault_paths import tenant_vault_path
from typing import Any


class RotatableSecretProvider:
    def __init__(
        self,
        settings: PlatformSettings,
        redis_client: AsyncRedisClient | None = None,
        secret_provider: SecretProvider | None = None,
    ) -> None:
        self.settings = settings
        self.redis_client = redis_client
        self._secret_provider = secret_provider or MockSecretProvider(
            settings, validate_paths=False
        )

    async def get_current(self, secret_name: str) -> str:
        cached = await self._cached(secret_name)
        if isinstance(cached.get("current"), str):
            return str(cached["current"])
        path = self._secret_path(secret_name)
        try:
            value = await self._secret_provider.get(path)
        except Exception as exc:
            raise RuntimeError(f"Required secret {secret_name!r} is missing") from exc
        if not value:
            raise RuntimeError(f"Required secret {secret_name!r} is missing")
        return value

    async def get_previous(self, secret_name: str) -> str | None:
        cached = await self._cached(secret_name)
        if isinstance(cached.get("previous"), str):
            return str(cached["previous"])
        path = self._secret_path(secret_name)
        try:
            versions = await self._secret_provider.list_versions(path)
        except Exception:
            return None
        if not versions:
            return None
        latest = max(versions)
        previous_versions = [version for version in versions if version < latest]
        if not previous_versions:
            return None
        previous = max(previous_versions)
        get_version = getattr(self._secret_provider, "get_version", None)
        if get_version is None:
            return None
        try:
            return str(await get_version(path, previous))
        except Exception:
            return None

    async def validate_either(self, secret_name: str, presented: str) -> bool:
        current = await self.get_current(secret_name)
        if presented == current:
            return True
        previous = await self.get_previous(secret_name)
        return previous is not None and presented == previous

    async def cache_rotation_state(
        self,
        secret_name: str,
        state: dict[str, Any],
        *,
        ttl_seconds: int = 60,
    ) -> None:
        if self.redis_client is not None:
            await self.redis_client.cache_set(
                "rotation-state",
                secret_name,
                state,
                ttl_seconds=ttl_seconds,
            )

    async def _cached(self, secret_name: str) -> dict[str, Any]:
        if self.redis_client is None:
            return {}
        cached = await self.redis_client.cache_get("rotation-state", secret_name)
        return cached or {}

    def _secret_path(self, secret_name: str) -> str:
        if secret_name.startswith("secret/data/musematic/"):
            return secret_name
        profile = getattr(self.settings, "profile", "dev")
        environment = (
            profile if profile in {"production", "staging", "dev", "test", "ci"} else "dev"
        )
        resource = "".join(
            char if char.isalnum() or char in {"/", "_", "-"} else "-"
            for char in secret_name.strip("/")
        )
        tenant = current_tenant.get(None)
        return tenant_vault_path(
            environment,
            tenant.slug if tenant is not None else "default",
            "audit-chain",
            resource,
        )
