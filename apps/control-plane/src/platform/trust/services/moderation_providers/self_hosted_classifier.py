from __future__ import annotations

import time
from platform.trust.services.moderation_providers.base import ProviderVerdict
from typing import Any

_PIPELINES: dict[str, Any] = {}


class SelfHostedClassifierProvider:
    name = "self_hosted"

    def __init__(
        self,
        *,
        model_name: str = "unitary/multilingual-toxic-xlm-roberta",
        pipeline_factory: Any | None = None,
    ) -> None:
        self.model_name = model_name
        self.pipeline_factory = pipeline_factory

    async def score(
        self,
        text: str,
        *,
        language: str | None,
        categories: set[str] | None,
    ) -> ProviderVerdict:
        started = time.perf_counter()
        classifier = self._classifier()
        if classifier is None:
            return ProviderVerdict(
                provider=self.name,
                scores={},
                triggered_categories=[],
                language=language,
                latency_ms=int((time.perf_counter() - started) * 1000),
                metadata={"provider_failed": True, "failure_action": "fail_open"},
            )
        result = classifier(text)
        scores = _normalise_scores(result, categories)
        return ProviderVerdict(
            provider=self.name,
            scores=scores,
            triggered_categories=[name for name, score in scores.items() if score > 0],
            language=language,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    def _classifier(self) -> Any | None:
        if self.model_name in _PIPELINES:
            return _PIPELINES[self.model_name]
        try:
            factory = self.pipeline_factory
            if factory is None:
                from transformers import pipeline  # type: ignore[import-not-found]

                factory = pipeline
            classifier = factory(
                "text-classification",
                model=self.model_name,
                top_k=None,
                truncation=True,
            )
        except Exception:
            return None
        _PIPELINES[self.model_name] = classifier
        return classifier


def _normalise_scores(result: Any, categories: set[str] | None) -> dict[str, float]:
    if isinstance(result, list) and result and isinstance(result[0], list):
        items = result[0]
    elif isinstance(result, list):
        items = result
    else:
        items = []
    scores: dict[str, float] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).lower()
        canonical = "toxicity"
        if "hate" in label or "identity" in label:
            canonical = "hate_speech"
        elif "sexual" in label:
            canonical = "sexually_explicit"
        elif "violence" in label or "self" in label or "threat" in label:
            canonical = "violence_self_harm"
        if categories is not None and canonical not in categories:
            continue
        scores[canonical] = max(float(item.get("score", 0.0)), scores.get(canonical, 0.0))
    return scores
