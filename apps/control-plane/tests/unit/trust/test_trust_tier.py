from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.trust.models import (
    CertificationStatus,
    GuardrailLayer,
    TrustBlockedActionRecord,
    TrustTierName,
)

import pytest

from tests.trust_support import build_certification, build_signal, build_trust_bundle, stamp


@pytest.mark.asyncio
async def test_trust_tier_get_tier_creates_default_untrusted() -> None:
    bundle = build_trust_bundle()

    response = await bundle.trust_tier_service.get_tier("agent-1")

    assert response.tier == TrustTierName.untrusted
    assert response.trust_score == 0.0


@pytest.mark.asyncio
async def test_trust_tier_recompute_calculates_weighted_score_and_publishes_event() -> None:
    bundle = build_trust_bundle()
    certification = build_certification(status=CertificationStatus.active)
    bundle.repository.certifications.append(certification)
    recent = datetime.now(UTC) - timedelta(days=1)
    bundle.repository.signals.extend(
        [
            build_signal(
                signal_type="guardrail.allowed",
                score_contribution=Decimal("1.0000"),
                source_id="allowed",
                created_at=recent,
            ),
            build_signal(
                signal_type="behavioral_conformance",
                score_contribution=Decimal("0.9000"),
                source_id="beh-1",
                created_at=recent,
            ),
            build_signal(
                signal_type="behavioral_conformance",
                score_contribution=Decimal("0.6000"),
                source_id="beh-2",
                created_at=recent,
            ),
        ]
    )

    response = await bundle.trust_tier_service.recompute("agent-1")

    assert response.tier == TrustTierName.certified
    assert response.trust_score >= 0.8
    assert bundle.producer.events[-1]["event_type"] == "trust_tier.updated"


@pytest.mark.asyncio
async def test_trust_tier_handles_event_and_manual_upsert() -> None:
    bundle = build_trust_bundle()
    bundle.repository.certifications.append(
        build_certification(status=CertificationStatus.pending, agent_revision_id="rev-pending")
    )
    bundle.repository.blocked_actions.append(
        stamp(
            TrustBlockedActionRecord(
                agent_id="agent-1",
                agent_fqn="fleet:agent-1",
                layer=GuardrailLayer.prompt_injection,
                policy_basis="blocked",
                input_context_hash="hash",
            )
        )
    )

    manual = await bundle.trust_tier_service.upsert_tier(
        "agent-2",
        TrustTierName.provisional,
        0.6,
        {
            "certification_component": 0.5,
            "guardrail_component": 0.5,
            "behavioral_component": 1.0,
        },
    )
    await bundle.trust_tier_service.handle_trust_event({"payload": {"agent_id": "agent-1"}})
    recomputed = await bundle.repository.get_tier("agent-1")

    assert manual.tier == TrustTierName.provisional
    assert recomputed is not None
    assert recomputed.tier in {TrustTierName.provisional, TrustTierName.untrusted}


@pytest.mark.asyncio
async def test_trust_tier_ignores_events_without_agent_id() -> None:
    bundle = build_trust_bundle()

    await bundle.trust_tier_service.handle_trust_event({"payload": {}})

    assert bundle.producer.events == []


def test_trust_tier_static_helpers_cover_remaining_branches() -> None:
    assert (
        build_trust_bundle().trust_tier_service._certification_component(
            CertificationStatus.superseded
        )
        == Decimal("0.2500")
    )
    assert build_trust_bundle().trust_tier_service._certification_component(None) == Decimal(
        "0.0000"
    )
    assert (
        build_trust_bundle().trust_tier_service._tier_from_score(Decimal("0.5000"))
        == TrustTierName.provisional
    )
    assert (
        build_trust_bundle().trust_tier_service._tier_from_score(Decimal("0.4999"))
        == TrustTierName.untrusted
    )
