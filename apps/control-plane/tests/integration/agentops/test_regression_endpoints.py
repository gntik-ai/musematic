from __future__ import annotations

from datetime import UTC, datetime
from platform.agentops.dependencies import get_agentops_service
from platform.agentops.router import router
from platform.agentops.schemas import (
    RegressionAlertListResponse,
    RegressionAlertResponse,
)
from platform.agentops.service import AgentOpsService
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI


class _RegressionRouterServiceStub:
    def __init__(self, workspace_id: UUID) -> None:
        now = datetime.now(UTC)
        self.workspace_id = workspace_id
        self.alert = RegressionAlertResponse(
            id=uuid4(),
            workspace_id=workspace_id,
            agent_fqn="finance:agent",
            new_revision_id=uuid4(),
            baseline_revision_id=uuid4(),
            status="active",
            regressed_dimensions=["quality"],
            statistical_test="welch_t_test",
            p_value=0.002,
            effect_size=1.2,
            significance_threshold=0.05,
            sample_sizes={"quality": 40},
            detected_at=now,
            resolved_at=None,
            resolved_by=None,
            resolution_reason=None,
            triggered_rollback=False,
            created_at=now,
            updated_at=now,
        )
        self.last_status: str | None = None

    async def list_regression_alerts(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> RegressionAlertListResponse:
        del cursor, limit
        assert agent_fqn == "finance:agent"
        assert workspace_id == self.workspace_id
        self.last_status = status
        items = [self.alert] if status in {None, self.alert.status} else []
        return RegressionAlertListResponse(items=items, next_cursor=None)

    async def get_regression_alert(self, alert_id: UUID) -> RegressionAlertResponse:
        assert alert_id == self.alert.id
        return self.alert

    async def resolve_regression_alert(
        self,
        alert_id: UUID,
        *,
        resolution: str,
        reason: str,
        resolved_by: UUID | None,
    ) -> RegressionAlertResponse:
        assert alert_id == self.alert.id
        self.alert.status = resolution
        self.alert.resolution_reason = reason
        self.alert.resolved_by = resolved_by
        self.alert.resolved_at = datetime.now(UTC)
        return self.alert


class _RegressionRepositoryStub:
    def __init__(self, workspace_id: UUID, revision_id: UUID) -> None:
        self.workspace_id = workspace_id
        self.revision_id = revision_id
        self.alert_id = uuid4()

    async def list_regression_alerts(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
        status: str | None = None,
        new_revision_id: UUID | None = None,
    ) -> tuple[list[SimpleNamespace], str | None]:
        del cursor, limit
        if (
            agent_fqn == "finance:agent"
            and workspace_id == self.workspace_id
            and status == "active"
            and new_revision_id == self.revision_id
        ):
            return (
                [
                    SimpleNamespace(
                        id=self.alert_id,
                        status="active",
                        regressed_dimensions=["quality"],
                        p_value=0.003,
                        effect_size=0.9,
                        detected_at=datetime.now(UTC),
                    )
                ],
                None,
            )
        return ([], None)


def _build_app(service: _RegressionRouterServiceStub, workspace_id: UUID) -> FastAPI:
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
async def test_get_regression_alerts_filters_by_status() -> None:
    workspace_id = uuid4()
    service = _RegressionRouterServiceStub(workspace_id)
    app = _build_app(service, workspace_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/agentops/finance:agent/regression-alerts",
            params={"status": "active"},
        )

    assert response.status_code == 200
    assert service.last_status == "active"
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["status"] == "active"


@pytest.mark.asyncio
async def test_post_resolve_changes_status_to_resolved() -> None:
    workspace_id = uuid4()
    service = _RegressionRouterServiceStub(workspace_id)
    app = _build_app(service, workspace_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/agentops/regression-alerts/{service.alert.id}/resolve",
            json={"resolution": "resolved", "reason": "Validated and accepted"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["resolution_reason"] == "Validated and accepted"


@pytest.mark.asyncio
async def test_active_alert_appears_in_agentops_service_interface() -> None:
    workspace_id = uuid4()
    revision_id = uuid4()
    service = AgentOpsService(
        repository=_RegressionRepositoryStub(workspace_id, revision_id),  # type: ignore[arg-type]
        event_publisher=SimpleNamespace(),
        governance_publisher=None,
        trust_service=None,
        eval_suite_service=None,
        policy_service=None,
        workflow_service=None,
        registry_service=None,
    )

    alerts = await service.get_active_regression_alerts(
        "finance:agent",
        revision_id,
        workspace_id,
    )

    assert len(alerts) == 1
    assert alerts[0].id == service.repository.alert_id  # type: ignore[attr-defined]
    assert alerts[0].status == "active"
    assert alerts[0].regressed_dimensions == ["quality"]
    assert alerts[0].p_value == 0.003
    assert alerts[0].effect_size == 0.9
