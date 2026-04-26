from __future__ import annotations

import time
from platform.trust.exceptions import ModerationProviderError, ModerationProviderTimeoutError
from platform.trust.services.moderation_providers.base import ProviderVerdict
from platform.trust.services.moderation_providers.openai_moderation import _resolve_secret
from typing import Any

import httpx

PERSPECTIVE_ATTRIBUTE_MAP = {
    "TOXICITY": "toxicity",
    "SEVERE_TOXICITY": "toxicity",
    "IDENTITY_ATTACK": "hate_speech",
    "THREAT": "violence_self_harm",
    "SEXUALLY_EXPLICIT": "sexually_explicit",
}


class GooglePerspectiveProvider:
    name = "google_perspective"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        deployment: str = "default",
        secret_provider: Any | None = None,
        base_url: str = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze",
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
            f"secret/data/trust/moderation-providers/google_perspective/{self.deployment}",
        )
        params = {"key": api_key} if api_key else {}
        attributes: dict[str, dict[str, object]] = {
            name: {} for name in PERSPECTIVE_ATTRIBUTE_MAP
        }
        payload = {
            "comment": {"text": text},
            "languages": [language] if language else None,
            "requestedAttributes": attributes,
        }
        payload = {key: value for key, value in payload.items() if value is not None}
        try:
            if self.http_client is not None:
                response = await self.http_client.post(
                    self.base_url,
                    params=params,
                    json=payload,
                    timeout=self.timeout_ms / 1000,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout_ms / 1000) as client:
                    response = await client.post(self.base_url, params=params, json=payload)
        except httpx.TimeoutException as exc:
            raise ModerationProviderTimeoutError(self.name) from exc
        except httpx.HTTPError as exc:
            raise ModerationProviderError(self.name) from exc
        if response.status_code >= 400:
            raise ModerationProviderError(self.name)
        raw_scores = response.json().get("attributeScores") or {}
        scores = _map_scores(raw_scores, categories)
        return ProviderVerdict(
            provider=self.name,
            scores=scores,
            triggered_categories=[name for name, score in scores.items() if score > 0],
            language=language,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


def _map_scores(raw_scores: dict[str, Any], categories: set[str] | None) -> dict[str, float]:
    scores: dict[str, float] = {}
    for native, data in raw_scores.items():
        canonical = PERSPECTIVE_ATTRIBUTE_MAP.get(native)
        if canonical is None:
            continue
        if categories is not None and canonical not in categories:
            continue
        value = ((data or {}).get("summaryScore") or {}).get("value", 0)
        scores[canonical] = max(float(value), scores.get(canonical, 0.0))
    return scores
