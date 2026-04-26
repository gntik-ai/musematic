from __future__ import annotations

from platform.trust.services.moderation_providers.base import (
    ModerationProvider,
    ProviderVerdict,
)


class ModerationProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ModerationProvider] = {}

    def register(self, name: str, provider: ModerationProvider) -> None:
        self._providers[name] = provider

    def get(self, name: str) -> ModerationProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise KeyError(f"Unknown moderation provider: {name}") from exc

    def has(self, name: str) -> bool:
        return name in self._providers

    def registered_names(self) -> list[str]:
        return sorted(self._providers)


__all__ = ["ModerationProvider", "ModerationProviderRegistry", "ProviderVerdict"]
