from __future__ import annotations

from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.composition.dependencies import get_composition_service
from platform.composition.router import _workspace_id, router
from platform.composition.schemas import (
    AgentBlueprintResponse,
    CompositionAuditEntryResponse,
    CompositionAuditListResponse,
    CompositionRequestListResponse,
    CompositionRequestResponse,
    CompositionValidationResponse,
    FleetBlueprintResponse,
)
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class FakeCompositionService:
    def __init__(self) -> None:
        self.workspace_id = uuid4()
        self.request_id = uuid4()
        self.agent_blueprint_id = uuid4()
        self.fleet_blueprint_id = uuid4()

    async def generate_agent_blueprint(self, payload, actor_id):
        assert actor_id
        self.workspace_id = payload.workspace_id
        return self.agent_response()

    async def get_agent_blueprint(self, blueprint_id, workspace_id):
        assert blueprint_id == self.agent_blueprint_id
        assert workspace_id == self.workspace_id
        return self.agent_response()

    async def override_agent_blueprint(self, blueprint_id, payload, actor_id, workspace_id):
        assert payload.overrides
        assert actor_id
        assert workspace_id == self.workspace_id
        return self.agent_response(version=2)

    async def validate_agent_blueprint(self, blueprint_id, workspace_id, actor_id):
        assert actor_id
        assert blueprint_id == self.agent_blueprint_id
        assert workspace_id == self.workspace_id
        return self.validation_response(self.agent_blueprint_id)

    async def generate_fleet_blueprint(self, payload, actor_id):
        assert actor_id
        self.workspace_id = payload.workspace_id
        return self.fleet_response()

    async def get_fleet_blueprint(self, blueprint_id, workspace_id):
        assert blueprint_id == self.fleet_blueprint_id
        assert workspace_id == self.workspace_id
        return self.fleet_response()

    async def override_fleet_blueprint(self, blueprint_id, payload, actor_id, workspace_id):
        assert payload.overrides
        assert actor_id
        assert workspace_id == self.workspace_id
        return self.fleet_response(version=2)

    async def validate_fleet_blueprint(self, blueprint_id, workspace_id, actor_id):
        assert actor_id
        assert blueprint_id == self.fleet_blueprint_id
        assert workspace_id == self.workspace_id
        return self.validation_response(self.fleet_blueprint_id, cycle=True)

    async def list_audit_entries(self, request_id, workspace_id, **kwargs):
        assert request_id == self.request_id
        assert workspace_id == self.workspace_id
        assert kwargs["limit"] == 10
        return CompositionAuditListResponse(
            items=[
                CompositionAuditEntryResponse(
                    entry_id=uuid4(),
                    request_id=request_id,
                    event_type="blueprint_generated",
                    actor_id=None,
                    payload={},
                    created_at=datetime.now(UTC),
                )
            ],
            next_cursor=None,
        )

    async def get_request(self, request_id, workspace_id):
        assert request_id == self.request_id
        assert workspace_id == self.workspace_id
        return self.request_response()

    async def list_requests(self, workspace_id, **kwargs):
        assert workspace_id == self.workspace_id
        assert kwargs["request_type"] == "agent"
        assert kwargs["status"] == "completed"
        return CompositionRequestListResponse(items=[self.request_response()], next_cursor=None)

    def agent_response(self, version: int = 1) -> AgentBlueprintResponse:
        return AgentBlueprintResponse(
            request_id=self.request_id,
            blueprint_id=self.agent_blueprint_id,
            version=version,
            workspace_id=self.workspace_id,
            description="agent",
            model_config_data={"model_id": "gpt-test"},
            tool_selections=[],
            connector_suggestions=[],
            policy_recommendations=[],
            context_profile={},
            maturity_estimate="developing",
            maturity_reasoning="ok",
            confidence_score=0.8,
            low_confidence=False,
            follow_up_questions=[],
            llm_reasoning_summary="",
            alternatives_considered=[],
            generation_time_ms=10,
            created_at=datetime.now(UTC),
        )

    def fleet_response(self, version: int = 1) -> FleetBlueprintResponse:
        return FleetBlueprintResponse(
            request_id=self.request_id,
            blueprint_id=self.fleet_blueprint_id,
            version=version,
            workspace_id=self.workspace_id,
            description="fleet",
            topology_type="sequential",
            member_count=1,
            member_roles=[],
            orchestration_rules=[],
            delegation_rules=[],
            escalation_rules=[],
            single_agent_suggestion=False,
            confidence_score=0.8,
            low_confidence=False,
            follow_up_questions=[],
            llm_reasoning_summary="",
            alternatives_considered=[],
            generation_time_ms=10,
            created_at=datetime.now(UTC),
        )

    def validation_response(
        self,
        blueprint_id: UUID,
        *,
        cycle: bool = False,
    ) -> CompositionValidationResponse:
        check = {"passed": True, "details": {}}
        return CompositionValidationResponse.model_validate(
            {
                "validation_id": uuid4(),
                "blueprint_id": blueprint_id,
                "overall_valid": True,
                "tools_check": check,
                "model_check": check,
                "connectors_check": check,
                "policy_check": check,
                "cycle_check": check if cycle else None,
                "validated_at": datetime.now(UTC),
            }
        )

    def request_response(self) -> CompositionRequestResponse:
        now = datetime.now(UTC)
        return CompositionRequestResponse(
            request_id=self.request_id,
            workspace_id=self.workspace_id,
            request_type="agent",
            description="agent",
            requested_by=uuid4(),
            status="completed",
            llm_model_used="test",
            generation_time_ms=10,
            created_at=now,
            updated_at=now,
        )


def _client(service: FakeCompositionService) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_composition_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(uuid4()),
        "workspace_id": str(service.workspace_id),
    }
    return TestClient(app)


def test_agent_blueprint_routes() -> None:
    service = FakeCompositionService()
    client = _client(service)
    workspace_id = str(service.workspace_id)

    created = client.post(
        "/api/v1/compositions/agent-blueprint",
        json={"workspace_id": workspace_id, "description": "agent"},
    )
    fetched = client.get(f"/api/v1/compositions/agent-blueprints/{service.agent_blueprint_id}")
    patched = client.patch(
        f"/api/v1/compositions/agent-blueprints/{service.agent_blueprint_id}",
        params={"workspace_id": workspace_id},
        json={"overrides": [{"field_path": "model_config.model_id", "new_value": "new"}]},
    )
    validated = client.post(
        f"/api/v1/compositions/agent-blueprints/{service.agent_blueprint_id}/validate",
        params={"workspace_id": workspace_id},
    )

    assert created.status_code == 201
    assert created.json()["model_config"]["model_id"] == "gpt-test"
    assert fetched.status_code == 200
    assert patched.json()["version"] == 2
    assert validated.json()["cycle_check"] is None


def test_workspace_id_requires_query_or_user_claim() -> None:
    assert _workspace_id({"workspace": "00000000-0000-0000-0000-000000000001"}, None)
    with pytest.raises(ValueError, match="workspace_id"):
        _workspace_id({}, None)


def test_fleet_request_and_audit_routes() -> None:
    service = FakeCompositionService()
    client = _client(service)
    workspace_id = str(service.workspace_id)

    created = client.post(
        "/api/v1/compositions/fleet-blueprint",
        json={"workspace_id": workspace_id, "description": "fleet"},
    )
    fetched = client.get(
        f"/api/v1/compositions/fleet-blueprints/{service.fleet_blueprint_id}",
        params={"workspace_id": workspace_id},
    )
    patched = client.patch(
        f"/api/v1/compositions/fleet-blueprints/{service.fleet_blueprint_id}",
        params={"workspace_id": workspace_id},
        json={"overrides": [{"field_path": "topology_type", "new_value": "peer"}]},
    )
    validated = client.post(
        f"/api/v1/compositions/fleet-blueprints/{service.fleet_blueprint_id}/validate",
        params={"workspace_id": workspace_id},
    )
    request = client.get(
        f"/api/v1/compositions/requests/{service.request_id}",
        params={"workspace_id": workspace_id},
    )
    requests = client.get(
        "/api/v1/compositions/requests",
        params={"workspace_id": workspace_id, "request_type": "agent", "status": "completed"},
    )
    audit = client.get(
        f"/api/v1/compositions/requests/{service.request_id}/audit",
        params={"workspace_id": workspace_id, "limit": 10},
    )

    assert created.status_code == 201
    assert fetched.status_code == 200
    assert patched.json()["version"] == 2
    assert validated.json()["cycle_check"]["passed"] is True
    assert request.json()["status"] == "completed"
    assert requests.json()["items"][0]["request_type"] == "agent"
    assert audit.json()["items"][0]["event_type"] == "blueprint_generated"
