from __future__ import annotations

import os
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.connectors.security import VaultResolver
from typing import Any


class RotatableSecretProvider:
    def __init__(
        self,
        settings: PlatformSettings,
        redis_client: AsyncRedisClient | None = None,
        vault: VaultResolver | None = None,
    ) -> None:
        self.settings = settings
        self.redis_client = redis_client
        self.vault = vault or VaultResolver(settings)

    async def get_current(self, secret_name: str) -> str:
        cached = await self._cached(secret_name)
        if isinstance(cached.get("current"), str):
            return str(cached["current"])
        value = self._read_secret(secret_name, "current")
        if value is None:
            raise RuntimeError(f"Required secret {secret_name!r} is missing")
        return value

    async def get_previous(self, secret_name: str) -> str | None:
        cached = await self._cached(secret_name)
        if isinstance(cached.get("previous"), str):
            return str(cached["previous"])
        return self._read_secret(secret_name, "previous", required=False)

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

    def _read_secret(self, secret_name: str, slot: str, *, required: bool = True) -> str | None:
        env_key = f"ROTATING_SECRET_{secret_name}_{slot}".upper().replace("-", "_")
        env_value = os.environ.get(env_key)
        if env_value:
            return env_value
        try:
            return self.vault.resolve(
                f"secret/data/musematic/{self.settings.profile}/rotating/{secret_name}",
                slot,
            )
        except Exception:
            if required:
                raise
            return None
