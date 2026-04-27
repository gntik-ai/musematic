from __future__ import annotations

import hashlib
from pathlib import Path
from platform.common.logging import get_logger
from platform.mock_llm.schemas import CannedResponse, MockLLMRequest, MockLLMResponse
from typing import Any

import yaml

LOGGER = get_logger(__name__)
DEFAULT_FIXTURE_PATH = Path(__file__).with_name("fixtures.yaml")


class MockLLMProvider:
    """Deterministic creator-preview provider that never reaches a real LLM."""

    def __init__(self, fixture_path: Path | str = DEFAULT_FIXTURE_PATH) -> None:
        self.fixture_path = Path(fixture_path)
        self._responses, self._fallback = self._load_fixtures(self.fixture_path)

    @staticmethod
    def input_hash(input_text: str) -> str:
        return hashlib.sha256(input_text.encode("utf-8")).hexdigest()[:16]

    async def complete(self, request: MockLLMRequest) -> MockLLMResponse:
        key = self.input_hash(request.input_text)
        matched = self._responses.get(key)
        if matched is not None:
            return MockLLMResponse(
                output_text=matched.output_text,
                completion_metadata={
                    **matched.completion_metadata,
                    "input_hash": key,
                    "fixture_path": str(self.fixture_path),
                },
                was_fallback=False,
            )

        LOGGER.info(
            "mock_llm.fallback_used",
            input_hash=key,
            fixture_path=str(self.fixture_path),
        )
        return MockLLMResponse(
            output_text=self._fallback.output_text,
            completion_metadata={
                **self._fallback.completion_metadata,
                "input_hash": key,
                "fixture_path": str(self.fixture_path),
            },
            was_fallback=True,
        )

    @staticmethod
    def _load_fixtures(path: Path) -> tuple[dict[str, CannedResponse], CannedResponse]:
        if not path.exists():
            raise FileNotFoundError(f"Mock LLM fixture file not found: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Mock LLM fixture file must contain a mapping")

        responses_raw = raw.get("responses")
        if not isinstance(responses_raw, list):
            raise ValueError("Mock LLM fixture file must contain a responses list")
        responses = {
            item.input_hash: item
            for item in (CannedResponse.model_validate(entry) for entry in responses_raw)
        }
        fallback_raw: Any = raw.get("fallback")
        fallback = CannedResponse.model_validate(fallback_raw)
        return responses, fallback

