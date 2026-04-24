from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(slots=True)
class ProviderResponse:
    payload: dict[str, Any]
    status_code: int


class ProviderError(RuntimeError):
    """Base class for provider transport errors."""


class ProviderOutage(ProviderError):  # noqa: N818
    """Provider returned a 5xx response."""


class ProviderTimeout(ProviderError):  # noqa: N818
    """Provider call timed out."""


class RateLimitedError(ProviderError):
    """Provider returned HTTP 429."""


class ProviderAuthError(ProviderError):
    """Provider rejected credentials."""


async def call(
    *,
    base_url: str,
    api_key: str,
    model_id: str,
    messages: list[dict[str, Any]],
    response_format: dict[str, Any] | None,
    timeout: float,  # noqa: ASYNC109 - contract uses OpenAI-compatible timeout arg
) -> ProviderResponse:
    body: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
    }
    if response_format is not None:
        body["response_format"] = response_format

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(base_url, json=body, headers=headers)
    except httpx.TimeoutException as exc:
        raise ProviderTimeout(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise ProviderOutage(str(exc)) from exc

    if response.status_code == 429:
        raise RateLimitedError(response.text)
    if response.status_code in {401, 403}:
        raise ProviderAuthError(response.text)
    if response.status_code >= 500:
        raise ProviderOutage(response.text)
    response.raise_for_status()
    return ProviderResponse(payload=response.json(), status_code=response.status_code)
