from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.governance.dependencies import get_governance_service
from platform.governance.models import ActionType, VerdictType
from platform.governance.router import router
from platform.governance.schemas import (
    EnforcementActionListResponse,
    EnforcementActionRead,
    GovernanceVerdictDetail,
    GovernanceVerdictRead,
    VerdictListQuery,
    VerdictListResponse,
)
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI


class _GovernanceServiceStub:
    def __init__(self, workspace_id: UUID, fleet_id: UUID) -> None:
        now = datetime.now(UTC)
        self.workspace_id = workspace_id
        self.fleet_id = fleet_id
        self.verdict_id = uuid4()
        self.action_id = uuid4()
        self.queries: list[VerdictListQuery] = []
        self.action_queries: list[object] = []
        self.verdict = GovernanceVerdictRead(
            id=self.verdict_id,
            judge_agent_fqn="platform:judge-1",
            verdict_type=VerdictType.VIOLATION,
            policy_id=uuid4(),
            rationale="observer threshold breached",
            recommended_action="block",
            source_event_id=uuid4(),
            fleet_id=fleet_id,
            workspace_id=workspace_id,
            created_at=now,
        )
        self.action = EnforcementActionRead(
            id=self.action_id,
            enforcer_agent_fqn="platform:enforcer-1",
            verdict_id=self.verdict_id,
            action_type=ActionType.block,
            target_agent_fqn="finance:target-agent",
            outcome={"status": "blocked"},
            workspace_id=workspace_id,
            created_at=now + timedelta(seconds=5),
        )

    async def list_verdicts(self, query: VerdictListQuery) -> VerdictListResponse:
        self.queries.append(query)
        assert query.fleet_id == self.fleet_id
        assert query.verdict_type is VerdictType.VIOLATION
        return VerdictListResponse(items=[self.verdict], total=1, next_cursor=None)

    async def get_verdict(self, verdict_id: UUID) -> GovernanceVerdictDetail:
        assert verdict_id == self.verdict_id
        return GovernanceVerdictDetail(
            **self.verdict.model_dump(),
            evidence={"observer_fqn": "platform:observer", "value": 0.97},
            enforcement_action=self.action,
        )

    async def list_enforcement_actions(self, query) -> EnforcementActionListResponse:
        self.action_queries.append(query)
        assert query.workspace_id == self.workspace_id
        return EnforcementActionListResponse(items=[self.action], total=1, next_cursor=None)


def _build_app(service: _GovernanceServiceStub, user_roles: list[dict[str, str]]) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: {"sub": str(uuid4()), "roles": user_roles}
    app.dependency_overrides[get_governance_service] = lambda: service
    return app


@pytest.mark.integration
@pytest.mark.asyncio
async def test_governance_api_lists_verdicts_and_enforcement_actions() -> None:
    workspace_id = uuid4()
    fleet_id = uuid4()
    service = _GovernanceServiceStub(workspace_id, fleet_id)
    app = _build_app(service, [{"role": "auditor"}])

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        verdicts = await client.get(
            "/api/v1/governance/verdicts",
            params={"fleet_id": str(fleet_id), "verdict_type": "VIOLATION"},
        )
        actions = await client.get(
            "/api/v1/governance/enforcement-actions",
            params={"workspace_id": str(workspace_id)},
        )

    assert verdicts.status_code == 200
    assert verdicts.json()["total"] == 1
    assert verdicts.json()["items"][0]["id"] == str(service.verdict_id)
    assert actions.status_code == 200
    assert actions.json()["items"][0]["action_type"] == "block"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_governance_api_returns_verdict_detail_with_nested_action() -> None:
    workspace_id = uuid4()
    fleet_id = uuid4()
    service = _GovernanceServiceStub(workspace_id, fleet_id)
    app = _build_app(service, [{"role": "auditor"}])

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(f"/api/v1/governance/verdicts/{service.verdict_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(service.verdict_id)
    assert body["enforcement_action"]["id"] == str(service.action_id)
    assert body["evidence"]["observer_fqn"] == "platform:observer"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_governance_api_denies_non_auditor_user() -> None:
    service = _GovernanceServiceStub(uuid4(), uuid4())
    app = _build_app(service, [{"role": "viewer"}])

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/governance/verdicts")

    assert response.status_code == 403
