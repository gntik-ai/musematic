from __future__ import annotations

from datetime import UTC, datetime
from platform.agentops.dependencies import get_agentops_service
from platform.agentops.router import router
from platform.agentops.schemas import CiCdGateResultListResponse, CiCdGateResultResponse
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI


class _GateRouterServiceStub:
    def __init__(self, workspace_id: UUID, *, certification_passed: bool) -> None:
        now = datetime.now(UTC)
        self.workspace_id = workspace_id
        self.requested_by = uuid4()
        self.certification_passed = certification_passed
        self.last_requested_by: UUID | None = None
        self.last_revision_id: UUID | None = None
        self.result = CiCdGateResultResponse(
            id=uuid4(),
            workspace_id=workspace_id,
            agent_fqn="finance:agent",
            revision_id=uuid4(),
            requested_by=self.requested_by,
            overall_passed=certification_passed,
            policy_gate_passed=True,
            policy_gate_detail={"passed": True, "violations": []},
            policy_gate_remediation=None,
            evaluation_gate_passed=True,
            evaluation_gate_detail={"aggregate_score": 0.91, "threshold": 0.8, "passed": True},
            evaluation_gate_remediation=None,
            certification_gate_passed=certification_passed,
            certification_gate_detail={"status": "active" if certification_passed else "expired"},
            certification_gate_remediation=None
            if certification_passed
            else "Renew or activate certification before deployment.",
            regression_gate_passed=True,
            regression_gate_detail={"active_alert_count": 0, "alerts": []},
            regression_gate_remediation=None,
            trust_tier_gate_passed=True,
            trust_tier_gate_detail={"tier": 2, "score": 0.88},
            trust_tier_gate_remediation=None,
            evaluated_at=now,
            evaluation_duration_ms=12,
            created_at=now,
            updated_at=now,
        )

    async def evaluate_gate_check(
        self,
        agent_fqn: str,
        revision_id: UUID,
        workspace_id: UUID,
        requested_by: UUID,
    ) -> CiCdGateResultResponse:
        assert agent_fqn == "finance:agent"
        assert workspace_id == self.workspace_id
        self.last_revision_id = revision_id
        self.last_requested_by = requested_by
        self.result.revision_id = revision_id
        self.result.requested_by = requested_by
        self.result.overall_passed = self.certification_passed
        self.result.certification_gate_passed = self.certification_passed
        self.result.certification_gate_detail = {
            "status": "active" if self.certification_passed else "expired"
        }
        return self.result

    async def list_gate_checks(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        revision_id: UUID | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> CiCdGateResultListResponse:
        del cursor, limit
        assert agent_fqn == "finance:agent"
        assert workspace_id == self.workspace_id
        if revision_id is not None:
            self.result.revision_id = revision_id
        return CiCdGateResultListResponse(items=[self.result], next_cursor=None)


def _build_app(service: _GateRouterServiceStub, workspace_id: UUID, actor_id: UUID) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(actor_id),
        "workspace_id": str(workspace_id),
    }
    app.dependency_overrides[get_agentops_service] = lambda: service
    return app


@pytest.mark.asyncio
async def test_post_gate_check_returns_overall_pass_when_all_checks_pass() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _GateRouterServiceStub(workspace_id, certification_passed=True)
    app = _build_app(service, workspace_id, actor_id)
    revision_id = uuid4()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/agentops/finance:agent/gate-check",
            json={"revision_id": str(revision_id), "workspace_id": str(workspace_id)},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["overall_passed"] is True
    assert body["certification_gate_passed"] is True
    assert service.last_requested_by == actor_id
    assert service.last_revision_id == revision_id


@pytest.mark.asyncio
async def test_post_gate_check_returns_failed_report_when_certification_fails() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _GateRouterServiceStub(workspace_id, certification_passed=False)
    app = _build_app(service, workspace_id, actor_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/agentops/finance:agent/gate-check",
            json={"revision_id": str(uuid4()), "workspace_id": str(workspace_id)},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["overall_passed"] is False
    assert body["certification_gate_passed"] is False
    assert body["certification_gate_detail"]["status"] == "expired"


@pytest.mark.asyncio
async def test_get_gate_check_history_returns_results() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _GateRouterServiceStub(workspace_id, certification_passed=True)
    app = _build_app(service, workspace_id, actor_id)
    revision_id = uuid4()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/agentops/finance:agent/gate-checks",
            params={"revision_id": str(revision_id)},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["agent_fqn"] == "finance:agent"
