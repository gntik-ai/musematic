from __future__ import annotations

from platform.trust.router import assess_privacy
from platform.trust.schemas import PrivacyAssessmentRequest

import pytest

from tests.trust_support import build_trust_bundle, service_account_user


@pytest.mark.integration
@pytest.mark.asyncio
async def test_privacy_assessment_endpoint() -> None:
    bundle = build_trust_bundle()
    bundle.policy_engine.privacy_result = {
        "compliant": False,
        "blocked": True,
        "violations": [{"rule": "pii"}],
    }

    response = await assess_privacy(
        PrivacyAssessmentRequest(
            context_assembly_id="assembly-1",
            workspace_id="workspace-1",
            agent_id="agent-1",
        ),
        current_user=service_account_user(),
        privacy_service=bundle.privacy_service,
    )

    assert response.blocked is True
    assert response.violations == [{"rule": "pii"}]
