from __future__ import annotations

from platform.trust.exceptions import ModerationProviderError
from platform.trust.services.moderation_providers.google_perspective import (
    GooglePerspectiveProvider,
)
from typing import Any

import pytest


class ResponseStub:
    status_code = 200

    def json(self) -> dict[str, Any]:
        return {
            "attributeScores": {
                "TOXICITY": {"summaryScore": {"value": 0.73}},
                "IDENTITY_ATTACK": {"summaryScore": {"value": 0.64}},
                "THREAT": {"summaryScore": {"value": 0.21}},
            }
        }


class ErrorResponseStub:
    status_code = 403

    def json(self) -> dict[str, Any]:
        return {"error": "secret-token"}


class ClientStub:
    def __init__(self, response: object) -> None:
        self.response = response
        self.last_params: dict[str, str] = {}
        self.last_payload: dict[str, Any] = {}

    async def post(self, *args: Any, **kwargs: Any) -> object:
        del args
        self.last_params = dict(kwargs["params"])
        self.last_payload = dict(kwargs["json"])
        return self.response


@pytest.mark.asyncio
async def test_google_perspective_adapter_maps_native_attributes() -> None:
    client = ClientStub(ResponseStub())
    provider = GooglePerspectiveProvider(api_key="secret-token", http_client=client)  # type: ignore[arg-type]

    verdict = await provider.score(
        "screen this",
        language="en",
        categories={"toxicity", "hate_speech"},
    )

    assert verdict.provider == "google_perspective"
    assert verdict.scores == {"toxicity": 0.73, "hate_speech": 0.64}
    assert client.last_params == {"key": "secret-token"}
    assert client.last_payload["languages"] == ["en"]


@pytest.mark.asyncio
async def test_google_perspective_http_error_hides_secret_material() -> None:
    provider = GooglePerspectiveProvider(
        api_key="secret-token",
        http_client=ClientStub(ErrorResponseStub()),  # type: ignore[arg-type]
    )

    with pytest.raises(ModerationProviderError) as exc_info:
        await provider.score("screen this", language=None, categories=None)

    assert "secret-token" not in str(exc_info.value)
