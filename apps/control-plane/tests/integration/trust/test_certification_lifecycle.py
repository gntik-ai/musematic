from __future__ import annotations

from platform.trust.models import TrustTierName
from platform.trust.router import (
    activate_certification,
    add_certification_evidence,
    create_certification,
    get_agent_tier,
    list_agent_certifications,
    revoke_certification,
)
from platform.trust.schemas import CertificationRevoke, EvidenceRefCreate

import pytest

from tests.trust_support import build_certification_create, build_trust_bundle, trust_certifier_user


@pytest.mark.integration
@pytest.mark.asyncio
async def test_certification_lifecycle_endpoints() -> None:
    bundle = build_trust_bundle()
    current_user = trust_certifier_user()

    created = await create_certification(
        build_certification_create(),
        current_user=current_user,
        certification_service=bundle.certification_service,
    )
    evidence = await add_certification_evidence(
        created.id,
        EvidenceRefCreate(
            evidence_type="test_results",
            source_ref_type="suite",
            source_ref_id="suite-1",
            summary="passed",
        ),
        current_user=current_user,
        certification_service=bundle.certification_service,
    )
    activated = await activate_certification(
        created.id,
        current_user=current_user,
        certification_service=bundle.certification_service,
    )
    tier = await get_agent_tier(
        created.agent_id,
        trust_tier_service=bundle.trust_tier_service,
    )
    listed = await list_agent_certifications(
        created.agent_id,
        certification_service=bundle.certification_service,
    )
    revoked = await revoke_certification(
        created.id,
        CertificationRevoke(reason="manual review"),
        current_user=current_user,
        certification_service=bundle.certification_service,
    )

    assert evidence.source_ref_id == "suite-1"
    assert activated.status.value == "active"
    assert tier.tier == TrustTierName.untrusted
    assert listed.total == 1
    assert revoked.status.value == "revoked"
