from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.trust.events import (
    TrustEventPublisher,
    TrustTierUpdatedPayload,
    make_correlation,
    utcnow,
)
from platform.trust.models import CertificationStatus, TrustTierName
from platform.trust.repository import TrustRepository
from platform.trust.schemas import TrustTierResponse
from typing import Any


class TrustTierService:
    def __init__(
        self,
        *,
        repository: TrustRepository,
        settings: Any,
        producer: Any | None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.events = TrustEventPublisher(producer)

    async def get_tier(self, agent_id: str) -> TrustTierResponse:
        tier = await self.repository.get_tier(agent_id)
        if tier is None:
            tier = await self.repository.upsert_trust_tier(
                agent_id=agent_id,
                agent_fqn=agent_id,
                tier=TrustTierName.untrusted,
                trust_score=Decimal("0.0000"),
                certification_component=Decimal("0.0000"),
                guardrail_component=Decimal("0.0000"),
                behavioral_component=Decimal("0.0000"),
                last_computed_at=datetime.now(UTC),
            )
        return TrustTierResponse.model_validate(tier)

    async def recompute(self, agent_id: str) -> TrustTierResponse:
        latest_certification = await self.repository.get_latest_certification_for_agent(agent_id)
        cert_component = self._certification_component(
            latest_certification.status if latest_certification else None
        )
        since = datetime.now(UTC) - timedelta(days=30)
        total_guardrail = await self.repository.count_guardrail_evaluations(agent_id, since=since)
        blocked = await self.repository.count_blocked_actions(agent_id, since=since)
        if total_guardrail <= 0:
            guardrail_component = Decimal("1.0000")
        else:
            guardrail_component = Decimal(max(0.0, 1 - (blocked / total_guardrail))).quantize(
                Decimal("0.0001")
            )
        signals, total_signals = await self.repository.list_trust_signals_for_agent(
            agent_id,
            since=since,
            signal_type="behavioral_conformance",
            limit=500,
        )
        if total_signals <= 0:
            behavioral_component = Decimal("0.0000")
        else:
            total_value = sum(Decimal(str(item.score_contribution)) for item in signals)
            behavioral_component = (total_value / Decimal(total_signals)).quantize(
                Decimal("0.0001")
            )

        score = (
            cert_component * Decimal("0.50")
            + guardrail_component * Decimal("0.35")
            + behavioral_component * Decimal("0.15")
        ).quantize(Decimal("0.0001"))
        tier_name = self._tier_from_score(score)
        tier = await self.repository.upsert_trust_tier(
            agent_id=agent_id,
            agent_fqn=latest_certification.agent_fqn if latest_certification else agent_id,
            tier=tier_name,
            trust_score=score,
            certification_component=cert_component,
            guardrail_component=guardrail_component,
            behavioral_component=behavioral_component,
            last_computed_at=datetime.now(UTC),
        )
        await self.events.publish_trust_tier_updated(
            TrustTierUpdatedPayload(
                agent_id=tier.agent_id,
                agent_fqn=tier.agent_fqn,
                tier=tier.tier.value,
                trust_score=float(tier.trust_score),
                occurred_at=utcnow(),
            ),
            make_correlation(),
        )
        return TrustTierResponse.model_validate(tier)

    async def handle_trust_event(self, event: dict[str, Any]) -> None:
        payload = event.get("payload", event)
        agent_id = payload.get("agent_id")
        if isinstance(agent_id, str) and agent_id:
            await self.recompute(agent_id)

    async def upsert_tier(
        self,
        agent_id: str,
        tier: TrustTierName,
        score: float,
        components: dict[str, float],
        *,
        agent_fqn: str | None = None,
    ) -> TrustTierResponse:
        item = await self.repository.upsert_trust_tier(
            agent_id=agent_id,
            agent_fqn=agent_fqn or agent_id,
            tier=tier,
            trust_score=Decimal(str(score)).quantize(Decimal("0.0001")),
            certification_component=Decimal(
                str(components.get("certification_component", 0.0))
            ).quantize(Decimal("0.0001")),
            guardrail_component=Decimal(str(components.get("guardrail_component", 0.0))).quantize(
                Decimal("0.0001")
            ),
            behavioral_component=Decimal(str(components.get("behavioral_component", 0.0))).quantize(
                Decimal("0.0001")
            ),
            last_computed_at=datetime.now(UTC),
        )
        return TrustTierResponse.model_validate(item)

    @staticmethod
    def _certification_component(status: CertificationStatus | None) -> Decimal:
        if status == CertificationStatus.active:
            return Decimal("1.0000")
        if status == CertificationStatus.pending:
            return Decimal("0.5000")
        if status == CertificationStatus.superseded:
            return Decimal("0.2500")
        return Decimal("0.0000")

    @staticmethod
    def _tier_from_score(score: Decimal) -> TrustTierName:
        if score >= Decimal("0.8000"):
            return TrustTierName.certified
        if score >= Decimal("0.5000"):
            return TrustTierName.provisional
        return TrustTierName.untrusted
