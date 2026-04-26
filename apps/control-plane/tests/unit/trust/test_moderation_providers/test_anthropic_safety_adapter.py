from __future__ import annotations

from platform.trust.exceptions import ModerationProviderError, ModerationProviderTimeoutError
from platform.trust.services.moderation_providers.anthropic_safety import AnthropicSafetyProvider
from typing import Any

import pytest


class RouterStub:
    async def moderate(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["provider"] == "anthropic"
        assert kwargs["timeout_ms"] == 2000
        return {"scores": {"toxicity": 0.8, "pii_leakage": 0.3, "ignored": 1.0}}


class TimeoutRouterStub:
    async def moderate(self, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        raise TimeoutError


@pytest.mark.asyncio
async def test_anthropic_adapter_uses_model_router_and_filters_categories() -> None:
    provider = AnthropicSafetyProvider(model_router=RouterStub())

    verdict = await provider.score("screen this", language="es", categories={"toxicity"})

    assert verdict.provider == "anthropic"
    assert verdict.language == "es"
    assert verdict.scores == {"toxicity": 0.8}


@pytest.mark.asyncio
async def test_anthropic_adapter_timeout_is_provider_timeout() -> None:
    provider = AnthropicSafetyProvider(model_router=TimeoutRouterStub())

    with pytest.raises(ModerationProviderTimeoutError):
        await provider.score("screen this", language=None, categories=None)


@pytest.mark.asyncio
async def test_anthropic_adapter_rejects_malformed_router_output() -> None:
    class MalformedRouter:
        async def moderate(self, **kwargs: Any) -> str:
            del kwargs
            return "not-json"

    provider = AnthropicSafetyProvider(model_router=MalformedRouter())

    with pytest.raises(ModerationProviderError):
        await provider.score("screen this", language=None, categories=None)
