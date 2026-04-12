from __future__ import annotations

from platform.trust.router import (
    create_oje_config,
    deactivate_oje_config,
    get_oje_config,
    list_oje_configs,
)

import pytest

from tests.trust_support import admin_user, build_oje_config_create, build_trust_bundle


@pytest.mark.integration
@pytest.mark.asyncio
async def test_oje_pipeline_config_endpoints() -> None:
    bundle = build_trust_bundle()
    bundle.registry_service.known_fqns.update({"observer:one", "judge:one", "enforcer:one"})

    created = await create_oje_config(
        build_oje_config_create(),
        current_user=admin_user(),
        oje_service=bundle.oje_service,
    )
    listed = await list_oje_configs(
        workspace_id="00000000-0000-0000-0000-000000000001",
        current_user=admin_user(),
        oje_service=bundle.oje_service,
    )
    fetched = await get_oje_config(
        created.id,
        current_user=admin_user(),
        oje_service=bundle.oje_service,
    )
    deleted = await deactivate_oje_config(
        created.id,
        current_user=admin_user(),
        oje_service=bundle.oje_service,
    )

    assert created.id == fetched.id
    assert listed.total == 1
    assert deleted.is_active is False
