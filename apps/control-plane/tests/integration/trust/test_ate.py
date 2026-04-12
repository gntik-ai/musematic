from __future__ import annotations

from platform.trust.models import CertificationStatus
from platform.trust.router import create_ate_config, get_ate_config, get_ate_run, start_ate_run
from platform.trust.schemas import ATERunRequest

import pytest

from tests.trust_support import (
    admin_user,
    build_ate_config_create,
    build_certification,
    build_trust_bundle,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ate_endpoints() -> None:
    bundle = build_trust_bundle()
    certification = build_certification(status=CertificationStatus.active)
    bundle.repository.certifications.append(certification)

    created = await create_ate_config(
        workspace_id="workspace-1",
        payload=build_ate_config_create(),
        current_user=admin_user(),
        ate_service=bundle.ate_service,
    )
    run = await start_ate_run(
        ATERunRequest(ate_config_id=created.id, certification_id=certification.id),
        current_user=admin_user(),
        ate_service=bundle.ate_service,
    )
    await bundle.ate_service.handle_simulation_completed(
        {
            "simulation_id": run.simulation_id,
            "scenario_results": [{"summary": "Scenario A passed"}],
        }
    )
    fetched = await get_ate_config(
        created.id,
        current_user=admin_user(),
        ate_service=bundle.ate_service,
    )
    status = await get_ate_run(
        run.simulation_id,
        current_user=admin_user(),
        ate_service=bundle.ate_service,
    )

    assert created.id == fetched.id
    assert status.status == "completed"
