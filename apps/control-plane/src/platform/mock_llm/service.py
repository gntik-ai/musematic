from __future__ import annotations

from platform.mock_llm.provider import MockLLMProvider
from platform.mock_llm.schemas import MockLLMRequest, MockLLMResponse
from typing import Any


class MockLLMService:
    def __init__(self, provider: MockLLMProvider | None = None) -> None:
        self.provider = provider or MockLLMProvider()

    async def preview(
        self,
        input_text: str,
        context: dict[str, Any] | None = None,
    ) -> MockLLMResponse:
        return await self.provider.complete(
            MockLLMRequest(input_text=input_text, context=context)
        )
