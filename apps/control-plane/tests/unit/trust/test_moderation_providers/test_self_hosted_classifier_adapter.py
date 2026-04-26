from __future__ import annotations

from platform.trust.services.moderation_providers.self_hosted_classifier import (
    SelfHostedClassifierProvider,
)
from typing import Any

import pytest


def classifier_factory(*args: Any, **kwargs: Any) -> object:
    assert args == ("text-classification",)
    assert kwargs["truncation"] is True

    def classify(text: str) -> list[dict[str, float | str]]:
        assert text == "screen this"
        return [
            {"label": "toxicity", "score": 0.82},
            {"label": "identity_attack", "score": 0.33},
            {"label": "sexual", "score": 0.2},
        ]

    return classify


def failing_factory(*args: Any, **kwargs: Any) -> object:
    del args, kwargs
    raise RuntimeError("model unavailable")


@pytest.mark.asyncio
async def test_self_hosted_adapter_lazy_loads_and_normalises_scores() -> None:
    provider = SelfHostedClassifierProvider(
        model_name="unit-test-model",
        pipeline_factory=classifier_factory,
    )

    verdict = await provider.score(
        "screen this",
        language=None,
        categories={"toxicity", "hate_speech"},
    )

    assert verdict.provider == "self_hosted"
    assert verdict.scores == {"toxicity": 0.82, "hate_speech": 0.33}


@pytest.mark.asyncio
async def test_self_hosted_adapter_fails_open_when_model_cannot_load() -> None:
    provider = SelfHostedClassifierProvider(
        model_name="unit-test-failing-model",
        pipeline_factory=failing_factory,
    )

    verdict = await provider.score("screen this", language="en", categories=None)

    assert verdict.scores == {}
    assert verdict.metadata == {"provider_failed": True, "failure_action": "fail_open"}
