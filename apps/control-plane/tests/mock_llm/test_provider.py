from __future__ import annotations

from pathlib import Path
from platform.mock_llm.provider import MockLLMProvider
from platform.mock_llm.schemas import CannedResponse, MockLLMRequest, MockLLMResponse

import pytest
from pydantic import ValidationError


@pytest.mark.asyncio
async def test_provider_returns_deterministic_fixture_response() -> None:
    provider = MockLLMProvider()
    request = MockLLMRequest(input_text="customer support refund request")

    first = await provider.complete(request)
    for _ in range(100):
        assert await provider.complete(request) == first

    assert first.was_fallback is False
    assert first.completion_metadata["scenario"] == "customer-support"


@pytest.mark.asyncio
async def test_provider_returns_generic_fallback_and_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    class FakeLogger:
        def info(self, event: str, **fields: object) -> None:
            events.append((event, fields))

    monkeypatch.setattr("platform.mock_llm.provider.LOGGER", FakeLogger())
    provider = MockLLMProvider()

    response = await provider.complete(MockLLMRequest(input_text="unmatched creator preview"))

    assert response.was_fallback is True
    assert response.completion_metadata["scenario"] == "generic-fallback"
    assert events[0][0] == "mock_llm.fallback_used"


def test_input_hash_uses_sha256_first_16_chars() -> None:
    assert MockLLMProvider.input_hash("customer support refund request") == "7da3ea817b92643a"


def test_fixture_file_missing_refuses_to_start(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        MockLLMProvider(tmp_path / "missing.yaml")


def test_fixture_file_loads_from_disk() -> None:
    provider = MockLLMProvider()
    assert provider.input_hash("review this code for security issues") in provider._responses


def test_mock_llm_request_validation_rejects_blank_input() -> None:
    with pytest.raises(ValidationError):
        MockLLMRequest(input_text=" ")


def test_schema_models_validate() -> None:
    canned = CannedResponse(
        input_hash="0123456789abcdef",
        output_text="ok",
        completion_metadata={"model": "mock"},
    )
    response = MockLLMResponse(
        output_text=canned.output_text,
        completion_metadata=canned.completion_metadata,
    )
    assert response.output_text == "ok"
    assert response.was_fallback is False
