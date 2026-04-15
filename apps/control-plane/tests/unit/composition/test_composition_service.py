from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.composition.events import CompositionEventPublisher
from platform.composition.exceptions import (
    BlueprintNotFoundError,
    CompositionRequestNotFoundError,
    DescriptionTooLongError,
    InvalidOverridePathError,
    LLMServiceUnavailableError,
)
from platform.composition.models import (
    AgentBlueprint,
    CompositionAuditEntry,
    CompositionRequest,
    CompositionValidation,
    FleetBlueprint,
)
from platform.composition.repository import CompositionRepository
from platform.composition.schemas import (
    AgentBlueprintGenerateRequest,
    AgentBlueprintOverrideRequest,
    AgentBlueprintRaw,
    BlueprintOverrideItem,
    CheckResult,
    FleetBlueprintGenerateRequest,
    FleetBlueprintOverrideRequest,
    FleetBlueprintRaw,
)
from platform.composition.service import CompositionService, WorkspaceServices
from uuid import UUID, uuid4

import pytest


class FakeSession:
    async def flush(self) -> None:
        return None


class FakeRepository:
    def __init__(self) -> None:
        self.session = FakeSession()
        self.requests: dict[UUID, CompositionRequest] = {}
        self.agents: dict[UUID, AgentBlueprint] = {}
        self.fleets: dict[UUID, FleetBlueprint] = {}
        self.validations: dict[UUID, CompositionValidation] = {}
        self.audit: list[CompositionAuditEntry] = []
        self.clock = datetime(2026, 1, 1, tzinfo=UTC)

    def _stamp(self, obj) -> None:
        obj.id = uuid4()
        obj.created_at = self.clock
        if hasattr(obj, "updated_at"):
            obj.updated_at = self.clock
        self.clock += timedelta(seconds=1)

    async def create_request(self, request: CompositionRequest) -> CompositionRequest:
        self._stamp(request)
        self.requests[request.id] = request
        return request

    async def create_agent_blueprint(self, blueprint: AgentBlueprint) -> AgentBlueprint:
        self._stamp(blueprint)
        blueprint.request = self.requests[blueprint.request_id]
        self.agents[blueprint.id] = blueprint
        return blueprint

    async def create_fleet_blueprint(self, blueprint: FleetBlueprint) -> FleetBlueprint:
        self._stamp(blueprint)
        blueprint.request = self.requests[blueprint.request_id]
        self.fleets[blueprint.id] = blueprint
        return blueprint

    async def get_agent_blueprint(
        self,
        blueprint_id: UUID,
        workspace_id: UUID,
    ) -> AgentBlueprint | None:
        item = self.agents.get(blueprint_id)
        return item if item is not None and item.workspace_id == workspace_id else None

    async def get_fleet_blueprint(
        self,
        blueprint_id: UUID,
        workspace_id: UUID,
    ) -> FleetBlueprint | None:
        item = self.fleets.get(blueprint_id)
        return item if item is not None and item.workspace_id == workspace_id else None

    async def get_latest_agent_blueprint(
        self,
        request_id: UUID,
        workspace_id: UUID,
    ) -> AgentBlueprint | None:
        matches = [
            item
            for item in self.agents.values()
            if item.request_id == request_id and item.workspace_id == workspace_id
        ]
        return max(matches, key=lambda item: item.version) if matches else None

    async def get_latest_fleet_blueprint(
        self,
        request_id: UUID,
        workspace_id: UUID,
    ) -> FleetBlueprint | None:
        matches = [
            item
            for item in self.fleets.values()
            if item.request_id == request_id and item.workspace_id == workspace_id
        ]
        return max(matches, key=lambda item: item.version) if matches else None

    async def insert_validation(self, validation: CompositionValidation) -> CompositionValidation:
        self._stamp(validation)
        self.validations[validation.id] = validation
        return validation

    async def insert_audit_entry(self, audit_entry: CompositionAuditEntry) -> CompositionAuditEntry:
        self._stamp(audit_entry)
        self.audit.append(audit_entry)
        return audit_entry

    async def request_exists(self, request_id: UUID, workspace_id: UUID) -> bool:
        item = self.requests.get(request_id)
        return item is not None and item.workspace_id == workspace_id

    async def get_audit_entries(
        self,
        request_id: UUID,
        workspace_id: UUID,
        *,
        event_type_filter: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ):
        del cursor
        items = [
            entry
            for entry in self.audit
            if entry.request_id == request_id
            and entry.workspace_id == workspace_id
            and (event_type_filter is None or entry.event_type == event_type_filter)
        ]
        return items[:limit], None

    async def get_request(self, request_id: UUID, workspace_id: UUID):
        item = self.requests.get(request_id)
        return item if item is not None and item.workspace_id == workspace_id else None

    async def list_requests(
        self,
        workspace_id: UUID,
        *,
        request_type: str | None = None,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ):
        del cursor
        items = [
            item
            for item in self.requests.values()
            if item.workspace_id == workspace_id
            and (request_type is None or item.request_type == request_type)
            and (status is None or item.status == status)
        ]
        return items[:limit], None


class FakePublisher(CompositionEventPublisher):
    def __init__(self) -> None:
        super().__init__(None)
        self.events: list[tuple[str, UUID, UUID, dict[str, object]]] = []

    async def publish(
        self,
        event_type,
        request_id,
        workspace_id,
        payload,
        actor_id=None,
        correlation_ctx=None,
    ):
        del actor_id, correlation_ctx
        self.events.append((event_type, request_id, workspace_id, payload))


class FakeAgentGenerator:
    def __init__(self, raw: AgentBlueprintRaw | Exception) -> None:
        self.raw = raw

    async def generate(self, description, workspace_id, workspace_context):
        del description, workspace_id, workspace_context
        if isinstance(self.raw, Exception):
            raise self.raw
        return self.raw


class FakeFleetGenerator:
    def __init__(self, raw: FleetBlueprintRaw | Exception) -> None:
        self.raw = raw

    async def generate(self, description, workspace_id, workspace_context):
        del description, workspace_id, workspace_context
        if isinstance(self.raw, Exception):
            raise self.raw
        return self.raw


class FakeValidator:
    async def validate_agent(self, blueprint, workspace_id):
        del blueprint, workspace_id
        ok = CheckResult(passed=True, details={})
        return {
            "overall_valid": True,
            "tools_check": ok,
            "model_check": ok,
            "connectors_check": ok,
            "policy_check": ok,
            "cycle_check": None,
        }

    async def validate_fleet(self, blueprint, workspace_id):
        del blueprint, workspace_id
        ok = CheckResult(passed=True, details={})
        return {
            "overall_valid": True,
            "tools_check": ok,
            "model_check": ok,
            "connectors_check": ok,
            "policy_check": ok,
            "cycle_check": CheckResult(passed=True, details={"cycles_found": []}),
        }


class ContextRegistry:
    async def get_available_tools(self, workspace_id):
        del workspace_id
        return [{"name": "browser", "capability_description": "browse", "api_key": "hidden"}]

    async def get_available_models(self, workspace_id):
        del workspace_id
        return [{"identifier": "gpt-test", "provider": "local", "tier": "dev"}]


class ContextConnector:
    async def list_workspace_connectors(self, workspace_id):
        del workspace_id
        return [{"connector_name": "slack", "connector_type": "chat", "secret": "hidden"}]


class ContextPolicy:
    async def list_active_policies(self, workspace_id):
        del workspace_id
        return [{"name": "safe", "description": "safe output", "scope": "workspace"}]


def _agent_raw(confidence: float = 0.9) -> AgentBlueprintRaw:
    return AgentBlueprintRaw.model_validate(
        {
            "model_config": {"model_id": "gpt-test"},
            "tool_selections": [{"tool_name": "browser"}],
            "connector_suggestions": [{"connector_name": "slack", "connector_type": "chat"}],
            "policy_recommendations": [{"policy_name": "safe"}],
            "context_profile": {"assembly_strategy": "standard", "memory_scope": "workspace"},
            "maturity_estimate": "developing",
            "maturity_reasoning": "ready",
            "confidence_score": confidence,
            "llm_reasoning_summary": "summary",
        }
    )


def _fleet_raw() -> FleetBlueprintRaw:
    return FleetBlueprintRaw.model_validate(
        {
            "topology_type": "sequential",
            "member_roles": [{"role_name": "fetch", "purpose": "fetch"}],
            "orchestration_rules": [{"rule_type": "routing", "action": "send"}],
            "delegation_rules": [],
            "escalation_rules": [],
            "confidence_score": 0.8,
        }
    )


def _service(repo: FakeRepository | None = None) -> tuple[CompositionService, FakeRepository]:
    repository = repo or FakeRepository()
    service = CompositionService(
        repository=repository,
        publisher=FakePublisher(),
        llm_client=object(),
        settings=PlatformSettings(),
        services=WorkspaceServices(
            registry=ContextRegistry(),
            policy=ContextPolicy(),
            connector=ContextConnector(),
        ),
        agent_generator=FakeAgentGenerator(_agent_raw()),
        fleet_generator=FakeFleetGenerator(_fleet_raw()),
        validator=FakeValidator(),
    )
    return service, repository


@pytest.mark.asyncio
async def test_generate_agent_blueprint_persists_request_blueprint_audit_and_event() -> None:
    service, repo = _service()
    workspace_id = uuid4()
    actor_id = uuid4()

    response = await service.generate_agent_blueprint(
        AgentBlueprintGenerateRequest(workspace_id=workspace_id, description="research agent"),
        actor_id,
    )

    assert response.version == 1
    assert response.workspace_id == workspace_id
    assert response.model_config_data["model_id"] == "gpt-test"
    assert len(repo.requests) == 1
    assert len(repo.agents) == 1
    assert repo.audit[0].event_type == "blueprint_generated"
    assert len(service.publisher.events) == 1


@pytest.mark.asyncio
async def test_generate_fleet_blueprint_persists_member_count() -> None:
    service, repo = _service()
    workspace_id = uuid4()

    response = await service.generate_fleet_blueprint(
        FleetBlueprintGenerateRequest(workspace_id=workspace_id, description="pipeline team"),
        uuid4(),
    )

    assert response.member_count == 1
    assert response.topology_type == "sequential"
    assert len(repo.fleets) == 1


@pytest.mark.asyncio
async def test_generate_fleet_blueprint_records_failed_request_on_llm_error() -> None:
    repo = FakeRepository()
    service, _repo = _service(repo)
    service.fleet_generator = FakeFleetGenerator(LLMServiceUnavailableError("down"))
    workspace_id = uuid4()

    with pytest.raises(LLMServiceUnavailableError):
        await service.generate_fleet_blueprint(
            FleetBlueprintGenerateRequest(workspace_id=workspace_id, description="fleet"),
            uuid4(),
        )

    request = next(iter(repo.requests.values()))
    assert request.status == "failed"
    assert repo.audit[-1].event_type == "generation_failed"


@pytest.mark.asyncio
async def test_generate_agent_blueprint_records_failed_request_on_llm_error() -> None:
    repo = FakeRepository()
    service, _repo = _service(repo)
    service.agent_generator = FakeAgentGenerator(LLMServiceUnavailableError("down"))
    workspace_id = uuid4()

    with pytest.raises(LLMServiceUnavailableError):
        await service.generate_agent_blueprint(
            AgentBlueprintGenerateRequest(workspace_id=workspace_id, description="agent"),
            uuid4(),
        )

    request = next(iter(repo.requests.values()))
    assert request.status == "failed"
    assert repo.audit[-1].event_type == "generation_failed"


@pytest.mark.asyncio
async def test_description_too_long_is_rejected() -> None:
    service, _repo = _service()
    service.settings = PlatformSettings(COMPOSITION_DESCRIPTION_MAX_CHARS=3)

    with pytest.raises(DescriptionTooLongError):
        await service.generate_agent_blueprint(
            AgentBlueprintGenerateRequest(workspace_id=uuid4(), description="long"),
            uuid4(),
        )


@pytest.mark.asyncio
async def test_override_agent_blueprint_creates_next_version_and_audit() -> None:
    service, repo = _service()
    workspace_id = uuid4()
    original = await service.generate_agent_blueprint(
        AgentBlueprintGenerateRequest(workspace_id=workspace_id, description="research"),
        uuid4(),
    )

    updated = await service.override_agent_blueprint(
        original.blueprint_id,
        AgentBlueprintOverrideRequest(
            overrides=[
                BlueprintOverrideItem(
                    field_path="model_config.model_id",
                    new_value="cheap-model",
                    reason="cost",
                )
            ]
        ),
        uuid4(),
        workspace_id,
    )

    assert updated.version == 2
    assert updated.model_config_data["model_id"] == "cheap-model"
    assert len(repo.agents) == 2
    assert repo.audit[-1].payload["overrides"][0]["old_value"] == "gpt-test"
    assert await service.get_agent_blueprint(updated.blueprint_id, workspace_id) == updated


@pytest.mark.asyncio
async def test_override_fleet_blueprint_and_invalid_path() -> None:
    service, _repo = _service()
    workspace_id = uuid4()
    original = await service.generate_fleet_blueprint(
        FleetBlueprintGenerateRequest(workspace_id=workspace_id, description="fleet"),
        uuid4(),
    )

    updated = await service.override_fleet_blueprint(
        original.blueprint_id,
        FleetBlueprintOverrideRequest(
            overrides=[BlueprintOverrideItem(field_path="topology_type", new_value="peer")]
        ),
        uuid4(),
        workspace_id,
    )

    assert updated.version == 2
    assert updated.topology_type == "peer"
    assert await service.get_fleet_blueprint(updated.blueprint_id, workspace_id) == updated
    with pytest.raises(InvalidOverridePathError):
        await service.override_fleet_blueprint(
            original.blueprint_id,
            FleetBlueprintOverrideRequest(
                overrides=[BlueprintOverrideItem(field_path="unknown.field", new_value="x")]
            ),
            uuid4(),
            workspace_id,
        )


@pytest.mark.asyncio
async def test_validate_blueprints_and_request_audit_queries() -> None:
    service, repo = _service()
    workspace_id = uuid4()
    agent = await service.generate_agent_blueprint(
        AgentBlueprintGenerateRequest(workspace_id=workspace_id, description="agent"),
        uuid4(),
    )
    fleet = await service.generate_fleet_blueprint(
        FleetBlueprintGenerateRequest(workspace_id=workspace_id, description="fleet"),
        uuid4(),
    )

    agent_validation = await service.validate_agent_blueprint(
        agent.blueprint_id,
        workspace_id,
        uuid4(),
    )
    fleet_validation = await service.validate_fleet_blueprint(
        fleet.blueprint_id,
        workspace_id,
        uuid4(),
    )
    request = await service.get_request(agent.request_id, workspace_id)
    audits = await service.list_audit_entries(agent.request_id, workspace_id)
    requests = await service.list_requests(workspace_id, request_type="agent", status="completed")

    assert agent_validation.overall_valid is True
    assert agent_validation.cycle_check is None
    assert fleet_validation.cycle_check is not None
    assert request.status == "completed"
    assert len(audits.items) == 2
    assert len(requests.items) == 1
    assert len(repo.validations) == 2

    latest_agent = await service.get_latest_agent_blueprint(agent.request_id, workspace_id)
    latest_fleet = await service.get_latest_fleet_blueprint(fleet.request_id, workspace_id)
    assert latest_agent is not None
    assert latest_fleet is not None


@pytest.mark.asyncio
async def test_get_missing_blueprint_raises_not_found() -> None:
    service, _repo = _service()

    with pytest.raises(BlueprintNotFoundError):
        await service.get_agent_blueprint(uuid4(), uuid4())

    with pytest.raises(BlueprintNotFoundError):
        await service.get_fleet_blueprint(uuid4(), uuid4())

    with pytest.raises(BlueprintNotFoundError):
        await service.validate_agent_blueprint(uuid4(), uuid4())

    with pytest.raises(BlueprintNotFoundError):
        await service.validate_fleet_blueprint(uuid4(), uuid4())

    with pytest.raises(BlueprintNotFoundError):
        await service.override_agent_blueprint(
            uuid4(),
            AgentBlueprintOverrideRequest(
                overrides=[BlueprintOverrideItem(field_path="model_config.model_id", new_value="x")]
            ),
            uuid4(),
            uuid4(),
        )

    with pytest.raises(BlueprintNotFoundError):
        await service.override_fleet_blueprint(
            uuid4(),
            FleetBlueprintOverrideRequest(
                overrides=[BlueprintOverrideItem(field_path="topology_type", new_value="peer")]
            ),
            uuid4(),
            uuid4(),
        )

    with pytest.raises(CompositionRequestNotFoundError):
        await service.get_request(uuid4(), uuid4())

    with pytest.raises(CompositionRequestNotFoundError):
        await service.list_audit_entries(uuid4(), uuid4())


def test_repository_type_contract_is_compatible() -> None:
    assert hasattr(CompositionRepository, "insert_audit_entry")
    assert not hasattr(CompositionRepository, "update_audit_entry")
    assert not hasattr(CompositionRepository, "delete_audit_entry")
