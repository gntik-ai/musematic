from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.composition.exceptions import LLMServiceUnavailableError
from platform.composition.llm.client import LLMCompositionClient
from typing import Any, ClassVar

import httpx
import pytest
from pydantic import BaseModel


class ParsedPayload(BaseModel):
    value: str


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self.payload = payload or {}

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeAsyncClient:
    calls: ClassVar[list[dict[str, Any]]] = []
    responses: ClassVar[list[FakeResponse | Exception]] = []

    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, url: str, json: dict[str, Any]) -> FakeResponse:
        self.calls.append({"url": url, "json": json, "timeout": self.timeout})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _settings() -> PlatformSettings:
    return PlatformSettings(
        COMPOSITION_LLM_API_URL="http://llm.local/chat",
        COMPOSITION_LLM_MODEL="test-model",
        COMPOSITION_LLM_TIMEOUT_SECONDS=3.0,
        COMPOSITION_LLM_MAX_RETRIES=2,
    )


def _chat(content: object) -> dict[str, Any]:
    return {"choices": [{"message": {"content": content}}]}


@pytest.mark.asyncio
async def test_generate_success_parses_json_string() -> None:
    FakeAsyncClient.calls = []
    FakeAsyncClient.responses = [FakeResponse(200, _chat('{"value": "ok"}'))]
    client = LLMCompositionClient(_settings(), http_client_factory=FakeAsyncClient)

    result = await client.generate("system", "user", ParsedPayload)

    assert result.value == "ok"
    assert FakeAsyncClient.calls[0]["url"] == "http://llm.local/chat"
    assert FakeAsyncClient.calls[0]["json"]["model"] == "test-model"
    assert FakeAsyncClient.calls[0]["json"]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_generate_success_parses_dict_content() -> None:
    FakeAsyncClient.responses = [FakeResponse(200, _chat({"value": "dict"}))]
    client = LLMCompositionClient(_settings(), http_client_factory=FakeAsyncClient)

    result = await client.generate("system", "user", ParsedPayload)

    assert result.value == "dict"


@pytest.mark.asyncio
async def test_generate_retries_503_then_succeeds() -> None:
    FakeAsyncClient.calls = []
    FakeAsyncClient.responses = [
        FakeResponse(503, {"error": "busy"}),
        FakeResponse(200, _chat('{"value": "retried"}')),
    ]
    client = LLMCompositionClient(_settings(), http_client_factory=FakeAsyncClient)

    result = await client.generate("system", "user", ParsedPayload)

    assert result.value == "retried"
    assert len(FakeAsyncClient.calls) == 2


@pytest.mark.asyncio
async def test_generate_raises_on_timeout_after_retries() -> None:
    FakeAsyncClient.responses = [
        httpx.TimeoutException("slow"),
        httpx.TimeoutException("slow"),
        httpx.TimeoutException("slow"),
    ]
    client = LLMCompositionClient(_settings(), http_client_factory=FakeAsyncClient)

    with pytest.raises(LLMServiceUnavailableError):
        await client.generate("system", "user", ParsedPayload)


@pytest.mark.asyncio
async def test_generate_raises_on_non_2xx_and_bad_json() -> None:
    client = LLMCompositionClient(_settings(), http_client_factory=FakeAsyncClient)
    FakeAsyncClient.responses = [FakeResponse(500, {"error": "nope"})]
    with pytest.raises(LLMServiceUnavailableError):
        await client.generate("system", "user", ParsedPayload)

    FakeAsyncClient.responses = [FakeResponse(200, _chat("not-json"))]
    with pytest.raises(LLMServiceUnavailableError):
        await client.generate("system", "user", ParsedPayload)
