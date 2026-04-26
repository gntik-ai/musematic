from __future__ import annotations

from platform.trust.exceptions import ModerationProviderTimeoutError
from platform.trust.services.moderation_providers.openai_moderation import (
    OpenAIModerationProvider,
)
from typing import Any

import httpx
import pytest


class ResponseStub:
    status_code = 200

    def json(self) -> dict[str, Any]:
        return {
            "results": [
                {
                    "category_scores": {
                        "harassment": 0.4,
                        "hate": 0.81,
                        "violence": 0.2,
                        "sexual": 0.1,
                    }
                }
            ]
        }


class ClientStub:
    def __init__(self) -> None:
        self.last_headers: dict[str, str] = {}

    async def post(self, *args: Any, **kwargs: Any) -> ResponseStub:
        del args
        self.last_headers = dict(kwargs["headers"])
        return ResponseStub()


class TimeoutClientStub:
    async def post(self, *args: Any, **kwargs: Any) -> ResponseStub:
        del args, kwargs
        raise httpx.TimeoutException("secret-token")


class SecretProviderStub:
    async def get_secret(self, path: str) -> dict[str, str]:
        assert path.endswith("/openai/default")
        return {"api_key": "secret-token"}


@pytest.mark.asyncio
async def test_openai_adapter_maps_native_categories_and_uses_secret() -> None:
    client = ClientStub()
    provider = OpenAIModerationProvider(
        secret_provider=SecretProviderStub(),
        http_client=client,  # type: ignore[arg-type]
    )

    verdict = await provider.score(
        "screen this",
        language="en",
        categories={"toxicity", "hate_speech"},
    )

    assert verdict.provider == "openai"
    assert verdict.scores == {"toxicity": 0.4, "hate_speech": 0.81}
    assert client.last_headers["Authorization"] == "Bearer secret-token"


@pytest.mark.asyncio
async def test_openai_adapter_timeout_hides_secret_material() -> None:
    provider = OpenAIModerationProvider(
        api_key="secret-token",
        http_client=TimeoutClientStub(),  # type: ignore[arg-type]
    )

    with pytest.raises(ModerationProviderTimeoutError) as exc_info:
        await provider.score("screen this", language=None, categories=None)

    assert "secret-token" not in str(exc_info.value)
