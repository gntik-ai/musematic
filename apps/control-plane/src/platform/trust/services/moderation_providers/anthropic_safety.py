from __future__ import annotations

import json
import time
from platform.trust.exceptions import ModerationProviderError, ModerationProviderTimeoutError
from platform.trust.services.moderation_providers.base import ProviderVerdict
from typing import Any


class AnthropicSafetyProvider:
    name = "anthropic"

    def __init__(
        self,
        *,
        model_router: Any | None = None,
        deployment: str = "default",
        secret_provider: Any | None = None,
        timeout_ms: int = 2000,
    ) -> None:
        self.model_router = model_router
        self.deployment = deployment
        self.secret_provider = secret_provider
        self.timeout_ms = timeout_ms

    async def score(
        self,
        text: str,
        *,
        language: str | None,
        categories: set[str] | None,
    ) -> ProviderVerdict:
        started = time.perf_counter()
        router = self.model_router
        if router is None:
            raise ModerationProviderError(self.name, "Model router unavailable")
        prompt = (
            "Classify this text for content safety. Return only JSON with canonical "
            "category scores for toxicity, hate_speech, violence_self_harm, "
            f"sexually_explicit, pii_leakage: {text}"
        )
        try:
            caller = (
                getattr(router, "moderate", None)
                or getattr(router, "complete", None)
                or getattr(router, "chat", None)
            )
            if caller is None:
                raise ModerationProviderError(
                    self.name, "Model router has no classification method"
                )
            result = caller(prompt=prompt, provider="anthropic", timeout_ms=self.timeout_ms)
            if hasattr(result, "__await__"):
                result = await result
        except TimeoutError as exc:
            raise ModerationProviderTimeoutError(self.name) from exc
        except ModerationProviderError:
            raise
        except Exception as exc:
            raise ModerationProviderError(self.name) from exc
        scores = _extract_scores(result, categories)
        return ProviderVerdict(
            provider=self.name,
            scores=scores,
            triggered_categories=[name for name, score in scores.items() if score > 0],
            language=language,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


def _extract_scores(result: Any, categories: set[str] | None) -> dict[str, float]:
    if isinstance(result, dict):
        payload = result.get("scores") or result.get("moderation") or result
    else:
        content = str(getattr(result, "content", result))
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ModerationProviderError(
                "anthropic", "Malformed safety classification"
            ) from exc
    scores: dict[str, float] = {}
    if not isinstance(payload, dict):
        raise ModerationProviderError("anthropic", "Malformed safety classification")
    for key, value in payload.items():
        if categories is not None and str(key) not in categories:
            continue
        try:
            scores[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return scores
