from __future__ import annotations

from platform.common.exceptions import AuthorizationError, ValidationError
from platform.trust.router import (
    _require_roles,
    _require_service_account,
    get_blocked_action,
    get_certification,
    get_guardrail_config,
    list_ate_configs,
    list_circuit_breaker_configs,
    list_prescreener_rule_sets,
)
from uuid import uuid4

import httpx
import pytest

from tests.trust_support import (
    admin_user,
    build_certification,
    build_trust_app,
    build_trust_bundle,
    trust_certifier_user,
    workspace_member_user,
)


@pytest.mark.asyncio
async def test_trust_router_requires_auth_with_real_middleware() -> None:
    app, _bundle = build_trust_app(require_auth_middleware=True)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/trust/agents/agent-1/tier")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_trust_router_direct_handlers_cover_missing_branches() -> None:
    bundle = build_trust_bundle()
    certification = build_certification()
    bundle.repository.certifications.append(certification)

    with pytest.raises(AuthorizationError):
        _require_roles({"roles": []}, {"platform_admin"})
    with pytest.raises(AuthorizationError):
        _require_service_account({"roles": [], "type": "human"})
    _require_service_account({"roles": [{"role": "platform_service"}], "type": "human"})

    fetched = await get_certification(
        certification.id,
        certification_service=bundle.certification_service,
    )
    assert fetched.id == certification.id

    with pytest.raises(ValidationError):
        await get_blocked_action(
            uuid4(),
            current_user=trust_certifier_user(),
            guardrail_service=bundle.guardrail_service,
        )
    with pytest.raises(ValidationError):
        await get_guardrail_config(
            workspace_id="workspace-404",
            fleet_id=None,
            guardrail_service=bundle.guardrail_service,
        )

    rule_sets = await list_prescreener_rule_sets(
        current_user=admin_user(),
        prescreener_service=bundle.prescreener_service,
    )
    ate_configs = await list_ate_configs(
        workspace_id="workspace-1",
        current_user=workspace_member_user(),
        ate_service=bundle.ate_service,
    )
    cb_configs = await list_circuit_breaker_configs(
        workspace_id="workspace-1",
        current_user=admin_user(),
        circuit_breaker_service=bundle.circuit_breaker_service,
    )

    assert rule_sets.total == 0
    assert ate_configs.total == 0
    assert cb_configs.total == 0
