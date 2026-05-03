"""UPD-050 — fraud-scoring Protocol + fail-soft wrapper tests."""

from __future__ import annotations

from platform.security.abuse_prevention.fraud_scoring import (
    FailSoftFraudScorer,
    NoopFraudScorer,
)
from platform.security.abuse_prevention.schemas import FraudScore

import pytest


@pytest.mark.asyncio
async def test_noop_scorer_always_returns_zero() -> None:
    scorer = NoopFraudScorer()
    score = await scorer.score(
        ip="1.2.3.4", email="alice@example.com", user_agent="ua", country="US"
    )
    assert score.risk == 0.0


@pytest.mark.asyncio
async def test_failsoft_collapses_exception_to_zero_risk() -> None:
    class _Boom:
        async def score(self, **_: object) -> FraudScore:
            raise RuntimeError("provider exploded")

    scorer = FailSoftFraudScorer(_Boom())
    score = await scorer.score(
        ip="1.2.3.4", email="alice@example.com", user_agent="ua", country="US"
    )
    assert score.risk == 0.0
    assert score.evidence == {"fail_soft": True}


@pytest.mark.asyncio
async def test_failsoft_passes_through_normal_results() -> None:
    class _Provider:
        async def score(self, **_: object) -> FraudScore:
            return FraudScore(risk=42.0, evidence={"signal": "ok"})

    scorer = FailSoftFraudScorer(_Provider())
    score = await scorer.score(
        ip="1.2.3.4", email="alice@example.com", user_agent="ua", country="US"
    )
    assert score.risk == 42.0
    assert score.evidence == {"signal": "ok"}
