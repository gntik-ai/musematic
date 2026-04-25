from __future__ import annotations

import json
from platform.common.clients.model_router import ModelRouter
from platform.common.config import PlatformSettings
from platform.composition.exceptions import LLMServiceUnavailableError
from platform.composition.schemas import LLMChatResponse
from typing import Any, TypeVar
from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMCompositionClient:
    """OpenAI-compatible JSON-mode LLM client for blueprint generation."""

    def __init__(
        self,
        settings: PlatformSettings,
        *,
        http_client_factory: type[httpx.AsyncClient] = httpx.AsyncClient,
        model_router: ModelRouter | None = None,
        workspace_id: UUID | None = None,
        model_binding: str | None = None,
    ) -> None:
        self.settings = settings
        self.http_client_factory = http_client_factory
        self.model_router = model_router
        self.workspace_id = workspace_id
        self.model_binding = model_binding

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[T],
    ) -> T:
        """Generate and parse a structured LLM response."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response_format = {"type": "json_object"}
        if self.settings.model_catalog.router_enabled:
            if self.model_router is None or self.workspace_id is None:
                raise LLMServiceUnavailableError(
                    "Model router is enabled but no router/workspace was configured"
                )
            try:
                routed = await self.model_router.complete(
                    workspace_id=self.workspace_id,
                    step_binding=self.model_binding or self.settings.composition.llm_model,
                    messages=messages,
                    response_format=response_format,
                    timeout_seconds=self.settings.composition.llm_timeout_seconds,
                )
                return _parse_llm_response(
                    {"choices": [{"message": {"content": routed.content}}]},
                    response_schema,
                )
            except Exception as exc:
                raise LLMServiceUnavailableError(f"Model router failed: {exc}") from exc

        last_error: Exception | None = None
        for attempt in range(self.settings.composition.llm_max_retries + 1):
            try:
                payload = {
                    "model": self.settings.composition.llm_model,
                    "messages": messages,
                    "response_format": response_format,
                }
                async with self.http_client_factory(
                    timeout=self.settings.composition.llm_timeout_seconds
                ) as client:
                    response = await client.post(
                        self.settings.composition.llm_api_url,
                        json=payload,
                    )
                if (
                    response.status_code == 503
                    and attempt < self.settings.composition.llm_max_retries
                ):
                    continue
                if response.status_code < 200 or response.status_code >= 300:
                    raise LLMServiceUnavailableError(
                        f"LLM service returned HTTP {response.status_code}"
                    )
                return _parse_llm_response(response.json(), response_schema)
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as exc:
                last_error = exc
                if attempt < self.settings.composition.llm_max_retries:
                    continue
                break
            except (json.JSONDecodeError, KeyError, TypeError, ValueError, ValidationError) as exc:
                last_error = exc
                break
        message = "LLM service unavailable"
        if last_error is not None:
            message = f"{message}: {last_error}"
        raise LLMServiceUnavailableError(message)


def _parse_llm_response[T: BaseModel](data: dict[str, Any], response_schema: type[T]) -> T:
    chat_response = LLMChatResponse.model_validate(data)
    content = chat_response.choices[0].message.get("content")
    if isinstance(content, str):
        parsed = json.loads(content)
    elif isinstance(content, dict):
        parsed = content
    else:
        raise ValueError("LLM response content must be JSON object content")
    return response_schema.model_validate(parsed)
