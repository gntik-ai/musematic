from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.agentops.dependencies import get_agentops_service
from platform.agentops.router import router
from platform.agentops.schemas import (
    GovernanceEventListResponse,
    GovernanceEventResponse,
    GovernanceSummaryResponse,
    RegressionAlertResponse,
    RetirementWorkflowResponse,
)
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI


class _GovernanceRouterServiceStub:
    def __init__(self, workspace_id: UUID) -> None:
        now = datetime.now(UTC)
        self.workspace_id = workspace_id
        self.events = [
            GovernanceEventResponse(
                id=uuid4(),
                workspace_id=workspace_id,
                agent_fqn="finance:agent",
                revision_id=uuid4(),
                event_type="agentops.recertification.triggered",
                actor_id=None,
                payload={"trigger_reason": "policy_changed"},
                created_at=now - timedelta(minutes=5),
            ),
            GovernanceEventResponse(
                id=uuid4(),
                workspace_id=workspace_id,
                agent_fqn="finance:agent",
                revision_id=uuid4(),
                event_type="agentops.retirement.initiated",
                actor_id=uuid4(),
                payload={"trigger_reason": "sustained_degradation"},
                created_at=now,
            ),
        ]

    async def list_governance_events(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        event_type: str | None = None,
        since: datetime | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> GovernanceEventListResponse:
        del cursor, limit
        assert agent_fqn == "finance:agent"
        assert workspace_id == self.workspace_id
        items = self.events
        if event_type is not None:
            items = [item for item in items if item.event_type == event_type]
        if since is not None:
            items = [item for item in items if item.created_at >= since]
        items = sorted(items, key=lambda item: item.created_at)
        return GovernanceEventListResponse(items=items, next_cursor=None)

    async def get_governance_summary(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> GovernanceSummaryResponse:
        assert agent_fqn == "finance:agent"
        assert workspace_id == self.workspace_id
        now = datetime.now(UTC)
        return GovernanceSummaryResponse(
            agent_fqn=agent_fqn,
            workspace_id=workspace_id,
            certification_status="pending",
            trust_tier=1,
            pending_triggers=[{"trigger_type": "policy_changed"}],
            upcoming_expirations=[{"expires_at": (now + timedelta(days=7)).isoformat()}],
            active_alerts=[
                RegressionAlertResponse(
                    id=uuid4(),
                    workspace_id=workspace_id,
                    agent_fqn=agent_fqn,
                    new_revision_id=uuid4(),
                    baseline_revision_id=uuid4(),
                    status="active",
                    regressed_dimensions=["quality"],
                    statistical_test="welch_t_test",
                    p_value=0.01,
                    effect_size=0.9,
                    significance_threshold=0.05,
                    sample_sizes={"quality": 32},
                    detected_at=now,
                    resolved_at=None,
                    resolved_by=None,
                    resolution_reason=None,
                    triggered_rollback=False,
                    created_at=now,
                    updated_at=now,
                )
            ],
            active_retirement=RetirementWorkflowResponse(
                id=uuid4(),
                workspace_id=workspace_id,
                agent_fqn=agent_fqn,
                revision_id=uuid4(),
                trigger_reason="manual",
                trigger_detail={"reason": "manual"},
                status="grace_period",
                dependent_workflows=[],
                high_impact_flag=False,
                operator_confirmed=False,
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
            ),
        )


def _build_app(service: _GovernanceRouterServiceStub, workspace_id: UUID) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(uuid4()),
        "workspace_id": str(workspace_id),
    }
    app.dependency_overrides[get_agentops_service] = lambda: service
    return app


@pytest.mark.asyncio
async def test_get_governance_events_returns_chronological_list() -> None:
    workspace_id = uuid4()
    app = _build_app(_GovernanceRouterServiceStub(workspace_id), workspace_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/agentops/finance:agent/governance-events")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    assert items[0]["created_at"] <= items[1]["created_at"]


@pytest.mark.asyncio
async def test_get_governance_summary_returns_current_state() -> None:
    workspace_id = uuid4()
    app = _build_app(_GovernanceRouterServiceStub(workspace_id), workspace_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/agentops/finance:agent/governance")

    assert response.status_code == 200
    body = response.json()
    assert body["certification_status"] == "pending"
    assert body["trust_tier"] == 1
    assert len(body["pending_triggers"]) == 1
    assert len(body["upcoming_expirations"]) == 1
