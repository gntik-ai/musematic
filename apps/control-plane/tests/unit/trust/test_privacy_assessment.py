from __future__ import annotations

from platform.trust.privacy_assessment import PrivacyAssessmentService
from platform.trust.schemas import PrivacyAssessmentRequest

import pytest

from tests.trust_support import PolicyEngineStub


@pytest.mark.asyncio
async def test_privacy_assessment_without_engine_defaults_to_compliant() -> None:
    service = PrivacyAssessmentService(policy_engine=None)

    response = await service.assess(
        PrivacyAssessmentRequest(
            context_assembly_id="assembly-1",
            workspace_id="workspace-1",
            agent_id="agent-1",
        )
    )

    assert response.compliant is True
    assert response.blocked is False


@pytest.mark.asyncio
async def test_privacy_assessment_maps_dict_and_bool_results() -> None:
    request = PrivacyAssessmentRequest(
        context_assembly_id="assembly-1",
        workspace_id="workspace-1",
        agent_id="agent-1",
    )
    dict_service = PrivacyAssessmentService(
        policy_engine=PolicyEngineStub(
            privacy_result={
                "compliant": False,
                "blocked": True,
                "violations": [{"rule": "pii"}],
            }
        )
    )
    bool_service = PrivacyAssessmentService(policy_engine=PolicyEngineStub(privacy_result=False))

    mapped = await dict_service.assess(request)
    mapped_bool = await bool_service.assess(request)

    assert mapped.compliant is False
    assert mapped.blocked is True
    assert mapped.violations == [{"rule": "pii"}]
    assert mapped_bool.compliant is False
    assert mapped_bool.blocked is True
