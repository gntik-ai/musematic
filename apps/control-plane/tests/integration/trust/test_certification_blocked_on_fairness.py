from __future__ import annotations

from platform.trust.exceptions import CertificationBlockedError
from uuid import uuid4

import pytest

from tests.trust_support import build_certification_create, build_trust_bundle


class FairnessGateStub:
    def __init__(self, latest: object | None, any_age: object | None = None) -> None:
        self.latest = latest
        self.any_age = any_age

    async def get_latest_passing_evaluation(self, **_kwargs: object) -> object | None:
        return self.latest

    async def get_latest_passing_evaluation_any_age(self, **_kwargs: object) -> object | None:
        return self.any_age


@pytest.mark.integration
@pytest.mark.asyncio
async def test_certification_blocks_high_impact_until_current_fairness_eval_passes() -> None:
    bundle = build_trust_bundle()
    service = bundle.certification_service
    agent_id = str(uuid4())
    issuer_id = str(uuid4())

    async def _skip_model_card_gate(_agent_id: str) -> None:
        return None

    service._ensure_bound_model_has_card = _skip_model_card_gate  # type: ignore[method-assign]
    payload = build_certification_create().model_copy(
        update={
            "agent_id": agent_id,
            "agent_revision_id": "rev-1",
            "high_impact_use": True,
        }
    )

    service.fairness_gate = FairnessGateStub(None)
    with pytest.raises(CertificationBlockedError) as required:
        await service.create(payload, issuer_id)

    service.fairness_gate = FairnessGateStub(object())
    created = await service.create(payload, issuer_id)

    service.fairness_gate = FairnessGateStub(None)
    with pytest.raises(CertificationBlockedError) as new_revision:
        await service.create(payload.model_copy(update={"agent_revision_id": "rev-2"}), issuer_id)

    service.fairness_gate = FairnessGateStub(None, any_age=object())
    with pytest.raises(CertificationBlockedError) as stale:
        await service.create(payload, issuer_id)

    assert required.value.details["reason"] == "fairness_evaluation_required"
    assert created.agent_revision_id == "rev-1"
    assert new_revision.value.details["reason"] == "fairness_evaluation_required"
    assert stale.value.details["reason"] == "fairness_evaluation_stale"
