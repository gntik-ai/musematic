from __future__ import annotations

import time
from platform.trust.exceptions import ModerationProviderError, ModerationProviderTimeoutError
from platform.trust.services.moderation_providers.base import ProviderVerdict
from typing import Any

import httpx

OPENAI_CATEGORY_MAP = {
    "harassment": "toxicity",
    "harassment/threatening": "toxicity",
    "hate": "hate_speech",
    "hate/threatening": "hate_speech",
    "violence": "violence_self_harm",
    "violence/graphic": "violence_self_harm",
    "self-harm": "violence_self_harm",
    "self-harm/intent": "violence_self_harm",
    "self-harm/instructions": "violence_self_harm",
    "sexual": "sexually_explicit",
    "sexual/minors": "sexually_explicit",
}


class OpenAIModerationProvider:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        deployment: str = "default",
        secret_provider: Any | None = None,
        base_url: str = "https://api.openai.com/v1/moderations",
        http_client: httpx.AsyncClient | None = None,
        timeout_ms: int = 2000,
    ) -> None:
        self.api_key = api_key
        self.deployment = deployment
        self.secret_provider = secret_provider
        self.base_url = base_url
        self.http_client = http_client
        self.timeout_ms = timeout_ms

    async def score(
        self,
        text: str,
        *,
        language: str | None,
        categories: set[str] | None,
    ) -> ProviderVerdict:
        started = time.perf_counter()
        api_key = await _resolve_secret(
            self.secret_provider,
            self.api_key,
            f"secret/data/trust/moderation-providers/openai/{self.deployment}",
        )
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        try:
            if self.http_client is not None:
                response = await self.http_client.post(
                    self.base_url,
                    headers=headers,
                    json={"input": text},
                    timeout=self.timeout_ms / 1000,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout_ms / 1000) as client:
                    response = await client.post(
                        self.base_url,
                        headers=headers,
                        json={"input": text},
                    )
        except httpx.TimeoutException as exc:
            raise ModerationProviderTimeoutError(self.name) from exc
        except httpx.HTTPError as exc:
            raise ModerationProviderError(self.name) from exc
        if response.status_code >= 400:
            raise ModerationProviderError(self.name)
        body = response.json()
        raw_scores = (body.get("results") or [{}])[0].get("category_scores") or {}
        scores = _map_scores(raw_scores, categories)
        triggered = [category for category, score in scores.items() if score > 0]
        return ProviderVerdict(
            provider=self.name,
            scores=scores,
            triggered_categories=triggered,
            language=language,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


def _map_scores(raw_scores: dict[str, Any], categories: set[str] | None) -> dict[str, float]:
    scores: dict[str, float] = {}
    for native, value in raw_scores.items():
        canonical = OPENAI_CATEGORY_MAP.get(native)
        if canonical is None:
            continue
        if categories is not None and canonical not in categories:
            continue
        scores[canonical] = max(float(value), scores.get(canonical, 0.0))
    return scores


async def _resolve_secret(secret_provider: Any | None, inline: str | None, path: str) -> str | None:
    if inline:
        return inline
    if secret_provider is None:
        return None
    getter = getattr(secret_provider, "get_secret", None) or getattr(secret_provider, "get", None)
    if getter is None:
        return None
    value = getter(path)
    if hasattr(value, "__await__"):
        value = await value
    if isinstance(value, dict):
        resolved = value.get("api_key") or value.get("token") or value.get("value")
        return str(resolved) if resolved is not None else None
    return str(value) if value is not None else None
