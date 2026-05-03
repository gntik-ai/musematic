"""Pluggable fraud-scoring adapter (UPD-050 T059).

Per research R7 this iteration ships only the Protocol + a
``NoopFraudScorer`` that always returns risk=0. Provider implementations
(MaxMind minFraud, Sift) are out of scope for this branch.

Fail-soft is non-negotiable per FR-019: any exception inside the
adapter is wrapped in ``FraudScoringFailedSoftly`` and the caller is
expected to fall back to a risk=0 score. The wrapper service in this
module provides that fallback so call sites don't need to handle it.
"""

from __future__ import annotations

from platform.common.logging import get_logger
from platform.security.abuse_prevention.schemas import FraudScore
from typing import Protocol

LOGGER = get_logger(__name__)


class FraudScoringProvider(Protocol):
    """Provider-agnostic shape. ``score`` returns a ``FraudScore`` whose
    ``risk`` is in [0, 100]; higher is riskier."""

    async def score(
        self,
        *,
        ip: str | None,
        email: str,
        user_agent: str | None,
        country: str | None,
    ) -> FraudScore: ...


class NoopFraudScorer:
    """Default provider — always returns risk=0.

    Used when the ``fraud_scoring_provider`` setting is ``"disabled"``.
    """

    async def score(
        self,
        *,
        ip: str | None,
        email: str,
        user_agent: str | None,
        country: str | None,
    ) -> FraudScore:
        return FraudScore(risk=0.0, evidence={})


class FailSoftFraudScorer:
    """Wrap a provider in a fail-soft try/except per FR-019.

    Any exception out of the wrapped provider collapses to risk=0; the
    caller never sees it. The fail-soft path still emits a structured
    log so operators see the third-party signal is missing.
    """

    def __init__(self, inner: FraudScoringProvider) -> None:
        self._inner = inner

    async def score(
        self,
        *,
        ip: str | None,
        email: str,
        user_agent: str | None,
        country: str | None,
    ) -> FraudScore:
        try:
            return await self._inner.score(
                ip=ip, email=email, user_agent=user_agent, country=country
            )
        except Exception:
            LOGGER.exception(
                "abuse.fraud_scoring.fail_soft",
                extra={"provider": type(self._inner).__name__},
            )
            return FraudScore(risk=0.0, evidence={"fail_soft": True})
