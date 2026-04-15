from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.agentops.dependencies import get_agentops_service
from platform.agentops.exceptions import RetirementConflictError
from platform.agentops.router import router
from platform.agentops.schemas import RetirementWorkflowResponse
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI


class _RetirementRouterServiceStub:
    def __init__(self, workspace_id: UUID) -> None:
        self.workspace_id = workspace_id
        self.active: RetirementWorkflowResponse | None = None

    async def initiate_retirement(
        self,
        agent_fqn: str,
        payload,
        *,
        actor: UUID,
    ) -> RetirementWorkflowResponse:
        assert payload.workspace_id == self.workspace_id
        if self.active is not None:
            raise RetirementConflictError(agent_fqn, self.workspace_id)
        now = datetime.now(UTC)
        workflow = RetirementWorkflowResponse(
            id=uuid4(),
            workspace_id=self.workspace_id,
            agent_fqn=agent_fqn,
            revision_id=payload.revision_id,
            trigger_reason=payload.reason,
            trigger_detail={"reason": payload.reason},
            status="grace_period",
            dependent_workflows=[{"workflow_id": "wf-1"}],
            high_impact_flag=True,
            operator_confirmed=payload.operator_confirmed,
            notifications_sent_at=now,
            grace_period_days=14,
            grace_period_starts_at=now,
            grace_period_ends_at=now + timedelta(days=14),
            retired_at=None,
            halted_at=None,
            halted_by=None,
            halt_reason=None,
            created_at=now,
            updated_at=now,
        )
        self.active = workflow
        return workflow

    async def get_retirement(self, workflow_id: UUID) -> RetirementWorkflowResponse:
        assert self.active is not None
        assert self.active.id == workflow_id
        return self.active

    async def confirm_retirement(
        self,
        workflow_id: UUID,
        payload,
        *,
        actor: UUID,
    ) -> RetirementWorkflowResponse:
        del payload, actor
        workflow = await self.get_retirement(workflow_id)
        workflow.operator_confirmed = True
        return workflow

    async def halt_retirement(
        self,
        workflow_id: UUID,
        payload,
        *,
        actor: UUID,
    ) -> RetirementWorkflowResponse:
        workflow = await self.get_retirement(workflow_id)
        workflow.status = "halted"
        workflow.halted_by = actor
        workflow.halt_reason = payload.reason
        workflow.halted_at = datetime.now(UTC)
        self.active = None
        return workflow


def _build_app(
    service: _RetirementRouterServiceStub,
    workspace_id: UUID,
    actor_id: UUID,
) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(actor_id),
        "workspace_id": str(workspace_id),
    }
    app.dependency_overrides[get_agentops_service] = lambda: service
    return app


def _payload(workspace_id: UUID) -> dict[str, object]:
    return {
        "workspace_id": str(workspace_id),
        "revision_id": str(uuid4()),
        "reason": "Sustained degradation",
        "operator_confirmed": False,
    }


@pytest.mark.asyncio
async def test_post_retire_returns_created() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _RetirementRouterServiceStub(workspace_id)
    app = _build_app(service, workspace_id, actor_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/agentops/finance:agent/retire",
            json=_payload(workspace_id),
        )

    assert response.status_code == 201
    assert response.json()["status"] == "grace_period"


@pytest.mark.asyncio
async def test_second_post_retire_returns_conflict() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _RetirementRouterServiceStub(workspace_id)
    app = _build_app(service, workspace_id, actor_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        await client.post("/api/v1/agentops/finance:agent/retire", json=_payload(workspace_id))
        response = await client.post(
            "/api/v1/agentops/finance:agent/retire",
            json=_payload(workspace_id),
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "AGENTOPS_RETIREMENT_CONFLICT"


@pytest.mark.asyncio
async def test_post_confirm_enables_high_impact_retirement() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _RetirementRouterServiceStub(workspace_id)
    app = _build_app(service, workspace_id, actor_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            "/api/v1/agentops/finance:agent/retire",
            json=_payload(workspace_id),
        )
        workflow_id = created.json()["id"]
        response = await client.post(
            f"/api/v1/agentops/retirements/{workflow_id}/confirm",
            json={"confirmed": True, "reason": "Approved"},
        )

    assert response.status_code == 200
    assert response.json()["operator_confirmed"] is True


@pytest.mark.asyncio
async def test_post_halt_sets_status_halted() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _RetirementRouterServiceStub(workspace_id)
    app = _build_app(service, workspace_id, actor_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            "/api/v1/agentops/finance:agent/retire",
            json=_payload(workspace_id),
        )
        workflow_id = created.json()["id"]
        response = await client.post(
            f"/api/v1/agentops/retirements/{workflow_id}/halt",
            json={"reason": "False alarm"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "halted"
