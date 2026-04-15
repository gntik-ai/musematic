from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.composition.dependencies import get_composition_service
from platform.composition.exceptions import BlueprintNotFoundError, LLMServiceUnavailableError
from platform.composition.router import router
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


class IntegrationCompositionService:
    def __init__(self) -> None:
        self.workspace_id = uuid4()
        self.request_id = uuid4()
        self.agent_blueprint_id = uuid4()
        self.fleet_blueprint_id = uuid4()
        self.unavailable = False

    async def generate_agent_blueprint(self, payload, actor_id):
        del actor_id
        if self.unavailable:
            raise LLMServiceUnavailableError("down")
        self.workspace_id = payload.workspace_id
        return self.agent_response()

    async def get_agent_blueprint(self, blueprint_id, workspace_id):
        if blueprint_id != self.agent_blueprint_id or workspace_id != self.workspace_id:
            raise BlueprintNotFoundError(blueprint_id)
        return self.agent_response()

    async def override_agent_blueprint(self, blueprint_id, payload, actor_id, workspace_id):
        del payload, actor_id
        if blueprint_id != self.agent_blueprint_id or workspace_id != self.workspace_id:
            raise BlueprintNotFoundError(blueprint_id)
        return self.agent_response(version=2, model_id="claude-sonnet-4-6")

    async def validate_agent_blueprint(self, blueprint_id, workspace_id, actor_id):
        del actor_id
        if blueprint_id != self.agent_blueprint_id or workspace_id != self.workspace_id:
            raise BlueprintNotFoundError(blueprint_id)
        return self.validation_response(blueprint_id)

    async def generate_fleet_blueprint(self, payload, actor_id):
        del actor_id
        self.workspace_id = payload.workspace_id
        return self.fleet_response(single_agent=payload.description == "single")

    async def get_fleet_blueprint(self, blueprint_id, workspace_id):
        if blueprint_id != self.fleet_blueprint_id or workspace_id != self.workspace_id:
            raise BlueprintNotFoundError(blueprint_id)
        return self.fleet_response()

    async def override_fleet_blueprint(self, blueprint_id, payload, actor_id, workspace_id):
        del payload, actor_id
        if blueprint_id != self.fleet_blueprint_id or workspace_id != self.workspace_id:
            raise BlueprintNotFoundError(blueprint_id)
        return self.fleet_response(version=2)

    async def validate_fleet_blueprint(self, blueprint_id, workspace_id, actor_id):
        del actor_id
        if blueprint_id != self.fleet_blueprint_id or workspace_id != self.workspace_id:
            raise BlueprintNotFoundError(blueprint_id)
        return self.validation_response(blueprint_id, cycle=True)

    async def list_audit_entries(self, request_id, workspace_id, **kwargs):
        del kwargs
        if request_id != self.request_id or workspace_id != self.workspace_id:
            raise BlueprintNotFoundError(request_id)
        return CompositionAuditListResponse(
            items=[
                CompositionAuditEntryResponse(
                    entry_id=uuid4(),
                    request_id=request_id,
                    event_type="blueprint_generated",
                    actor_id=None,
                    payload={},
                    created_at=datetime.now(UTC),
                ),
                CompositionAuditEntryResponse(
                    entry_id=uuid4(),
                    request_id=request_id,
                    event_type="blueprint_validated",
                    actor_id=None,
                    payload={},
                    created_at=datetime.now(UTC),
                ),
            ],
            next_cursor=None,
        )

    async def get_request(self, request_id, workspace_id):
        if request_id != self.request_id or workspace_id != self.workspace_id:
            raise BlueprintNotFoundError(request_id)
        return self.request_response()

    async def list_requests(self, workspace_id, **kwargs):
        del kwargs
        if workspace_id != self.workspace_id:
            return CompositionRequestListResponse(items=[], next_cursor=None)
        return CompositionRequestListResponse(items=[self.request_response()], next_cursor=None)

    def agent_response(
        self,
        *,
        version: int = 1,
        model_id: str = "gpt-test",
    ) -> AgentBlueprintResponse:
        return AgentBlueprintResponse(
            request_id=self.request_id,
            blueprint_id=self.agent_blueprint_id,
            version=version,
            workspace_id=self.workspace_id,
            description="agent",
            model_config_data={"model_id": model_id},
            tool_selections=[{"tool_name": "browser"}],
            connector_suggestions=[],
            policy_recommendations=[],
            context_profile={},
            maturity_estimate="developing",
            maturity_reasoning="ok",
            confidence_score=0.8,
            low_confidence=False,
            follow_up_questions=[],
            llm_reasoning_summary="summary",
            alternatives_considered=[],
            generation_time_ms=10,
            created_at=datetime.now(UTC),
        )

    def fleet_response(
        self,
        *,
        version: int = 1,
        single_agent: bool = False,
    ) -> FleetBlueprintResponse:
        return FleetBlueprintResponse(
            request_id=self.request_id,
            blueprint_id=self.fleet_blueprint_id,
            version=version,
            workspace_id=self.workspace_id,
            description="fleet",
            topology_type="sequential",
            member_count=1 if single_agent else 3,
            member_roles=[{"role_name": "fetch"}],
            orchestration_rules=[],
            delegation_rules=[{"from_role": "fetch", "to_role": "report"}],
            escalation_rules=[],
            single_agent_suggestion=single_agent,
            confidence_score=0.8,
            low_confidence=False,
            follow_up_questions=[],
            llm_reasoning_summary="summary",
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
        ok = {"passed": True, "details": {}}
        cycle_check = (
            {"passed": False, "details": {"cycles_found": [{"path": ["a", "b", "a"]}]}}
            if cycle
            else None
        )
        return CompositionValidationResponse.model_validate(
            {
                "validation_id": uuid4(),
                "blueprint_id": blueprint_id,
                "overall_valid": not cycle,
                "tools_check": ok,
                "model_check": ok,
                "connectors_check": ok,
                "policy_check": ok,
                "cycle_check": cycle_check,
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
            llm_model_used="test-model",
            generation_time_ms=10,
            created_at=now,
            updated_at=now,
        )


@pytest.fixture
def composition_client() -> Iterator[tuple[TestClient, IntegrationCompositionService]]:
    service = IntegrationCompositionService()
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.dependency_overrides[get_composition_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(uuid4()),
        "workspace_id": str(service.workspace_id),
    }
    with TestClient(app) as client:
        yield client, service
