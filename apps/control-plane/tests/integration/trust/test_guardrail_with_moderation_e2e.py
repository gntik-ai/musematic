from __future__ import annotations

from platform.trust.models import GuardrailLayer
from platform.trust.schemas import GuardrailEvaluationRequest, ModerationVerdict
from uuid import uuid4

import pytest

from tests.trust_support import build_trust_bundle


class ModeratorStub:
    def __init__(self, verdict: ModerationVerdict) -> None:
        self.verdict = verdict

    async def moderate_output(self, **_kwargs: object) -> ModerationVerdict:
        return self.verdict


def _request(content: str) -> GuardrailEvaluationRequest:
    return GuardrailEvaluationRequest(
        agent_id=str(uuid4()),
        agent_fqn="fleet:moderated-agent",
        execution_id=str(uuid4()),
        interaction_id=str(uuid4()),
        workspace_id=str(uuid4()),
        layer=GuardrailLayer.output_moderation,
        payload={"content": content},
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guardrail_pipeline_content_moderator_block_and_legacy_no_policy() -> None:
    bundle = build_trust_bundle()
    bundle.guardrail_service.content_moderator = ModeratorStub(
        ModerationVerdict(action="block", content="blocked replacement")
    )

    blocked = await bundle.guardrail_service.evaluate_full_pipeline(_request("toxic output"))

    legacy = build_trust_bundle()
    allowed = await legacy.guardrail_service.evaluate_full_pipeline(_request("safe output"))

    assert blocked.allowed is False
    assert blocked.policy_basis == "output_moderation:block"
    assert allowed.allowed is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guardrail_pipeline_regex_floor_runs_after_flag_verdict() -> None:
    bundle = build_trust_bundle()
    bundle.guardrail_service.content_moderator = ModeratorStub(
        ModerationVerdict(action="flag", content="Contains a credit card number")
    )

    response = await bundle.guardrail_service.evaluate_full_pipeline(
        _request("Contains a credit card number")
    )

    assert response.allowed is False
    assert response.policy_basis == "output_moderation:pattern_2"
