from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.common.events.envelope import CorrelationContext
from platform.common.exceptions import PlatformError, ValidationError, platform_exception_handler
from platform.fleets.dependencies import (
    _get_producer,
    _get_redis,
    _get_runtime_controller,
    _get_settings,
    build_fleet_service,
    build_governance_service,
    build_health_service,
    build_orchestration_modifier_service,
    get_fleet_service,
    get_governance_service,
    get_health_service,
)
from platform.fleets.events import (
    FleetCreatedPayload,
    FleetEventType,
    FleetHealthUpdatedPayload,
    publish_fleet_event,
    register_fleet_event_types,
)
from platform.fleets.models import FleetMemberRole
from platform.fleets.repository import (
    FleetGovernanceChainRepository,
    FleetMemberRepository,
    FleetOrchestrationRulesRepository,
    FleetPolicyBindingRepository,
    FleetRepository,
    FleetTopologyVersionRepository,
    ObserverAssignmentRepository,
)
from platform.fleets.router import _workspace_id as fleet_workspace_id
from platform.fleets.router import router
from platform.fleets.service import FleetService
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, Request

from tests.auth_support import FakeAsyncRedisClient, RecordingProducer
from tests.fleet_support import (
    OJEPipelineServiceStub,
    QueryResultStub,
    RuntimeControllerStub,
    SessionStub,
    build_fleet,
    build_fleet_create,
    build_fleet_service_stack,
    build_governance_chain,
    build_member,
    build_observer_assignment,
    build_orchestration_rules,
    build_policy_binding,
    build_rules_create,
    build_topology_version,
)


def _request_with_state(app: FastAPI) -> Request:
    return Request({"type": "http", "app": app, "headers": []})


def _request_with_headers(*headers: tuple[bytes, bytes]) -> Request:
    return Request({"type": "http", "app": FastAPI(), "headers": list(headers)})


@pytest.mark.asyncio
async def test_fleets_router_end_to_end() -> None:
    workspace_id = uuid4()
    user_id = uuid4()
    service, deps = build_fleet_service_stack(
        known_fqns={
            "agent:lead",
            "agent:worker-1",
            "agent:worker-2",
            "agent:worker-3",
            "observer:quality",
        }
    )
    governance_service = build_governance_service(
        session=SessionStub(),
        producer=deps.producer,
        oje_service=OJEPipelineServiceStub(),
    )
    governance_service.fleet_repo = deps.fleet_repo  # type: ignore[assignment]
    governance_service.governance_repo = deps.governance_repo  # type: ignore[assignment]

    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)

    async def _current_user() -> dict[str, str]:
        return {"sub": str(user_id), "workspace_id": str(workspace_id)}

    async def _fleet_service() -> FleetService:
        return service

    async def _health_service():
        return deps.health_service

    async def _governance_service():
        return governance_service

    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_fleet_service] = _fleet_service
    app.dependency_overrides[get_health_service] = _health_service
    app.dependency_overrides[get_governance_service] = _governance_service

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            "/api/v1/fleets",
            json=build_fleet_create().model_dump(mode="json"),
        )
        fleet_id = created.json()["id"]
        listed = await client.get("/api/v1/fleets")
        fetched = await client.get(f"/api/v1/fleets/{fleet_id}")
        updated = await client.put(f"/api/v1/fleets/{fleet_id}", json={"quorum_min": 3})
        health = await client.get(f"/api/v1/fleets/{fleet_id}/health")
        members = await client.get(f"/api/v1/fleets/{fleet_id}/members")
        added_member = await client.post(
            f"/api/v1/fleets/{fleet_id}/members",
            json={"agent_fqn": "agent:worker-3", "role": "worker"},
        )
        updated_member = await client.put(
            f"/api/v1/fleets/{fleet_id}/members/{added_member.json()['id']}/role",
            json={"role": "observer"},
        )
        topology = await client.put(
            f"/api/v1/fleets/{fleet_id}/topology",
            json={"topology_type": "peer_to_peer", "config": {}},
        )
        topology_history = await client.get(f"/api/v1/fleets/{fleet_id}/topology/history")
        binding = await client.post(
            f"/api/v1/fleets/{fleet_id}/policies",
            json={"policy_id": str(uuid4())},
        )
        unbound = await client.delete(f"/api/v1/fleets/{fleet_id}/policies/{binding.json()['id']}")
        observer = await client.post(
            f"/api/v1/fleets/{fleet_id}/observers",
            json={"observer_fqn": "observer:quality"},
        )
        observer_removed = await client.delete(
            f"/api/v1/fleets/{fleet_id}/observers/{observer.json()['id']}"
        )
        rules = await client.get(f"/api/v1/fleets/{fleet_id}/orchestration-rules")
        rules_updated = await client.put(
            f"/api/v1/fleets/{fleet_id}/orchestration-rules",
            json=build_rules_create(max_parallelism=5).model_dump(mode="json"),
        )
        rules_history = await client.get(f"/api/v1/fleets/{fleet_id}/orchestration-rules/history")
        chain = await client.get(f"/api/v1/fleets/{fleet_id}/governance-chain")
        chain_updated = await client.put(
            f"/api/v1/fleets/{fleet_id}/governance-chain",
            json={
                "observer_fqns": ["observer:new"],
                "judge_fqns": ["judge:new"],
                "enforcer_fqns": ["enforcer:new"],
                "policy_binding_ids": [],
            },
        )
        chain_history = await client.get(f"/api/v1/fleets/{fleet_id}/governance-chain/history")
        removed_member = await client.delete(
            f"/api/v1/fleets/{fleet_id}/members/{added_member.json()['id']}"
        )
        archived = await client.post(f"/api/v1/fleets/{fleet_id}/archive")

    assert created.status_code == 201
    assert listed.json()["total"] == 1
    assert fetched.status_code == 200
    assert updated.json()["quorum_min"] == 3
    assert health.status_code == 200
    assert members.json()["total"] == 3
    assert added_member.status_code == 201
    assert updated_member.json()["role"] == "observer"
    assert topology.json()["version"] == 2
    assert topology_history.json()["total"] == 2
    assert unbound.status_code == 204
    assert observer_removed.status_code == 204
    assert rules.json()["version"] == 1
    assert rules_updated.json()["version"] == 2
    assert rules_history.json()["total"] == 2
    assert chain.status_code == 200
    assert chain_updated.json()["version"] == 2
    assert chain_history.json()["total"] == 2
    assert removed_member.status_code == 204
    assert archived.json()["status"] == "archived"


@pytest.mark.asyncio
async def test_fleets_dependencies_and_events() -> None:
    app = FastAPI()
    redis_client = FakeAsyncRedisClient()
    producer = RecordingProducer()
    runtime_controller = RuntimeControllerStub()
    app.state.settings = build_fleet_service_stack()[0].settings
    app.state.clients = {
        "redis": redis_client,
        "kafka": producer,
        "runtime_controller": runtime_controller,
    }
    request = _request_with_state(app)
    session = SessionStub()
    registry_service = SimpleNamespace()

    assert _get_settings(request) is app.state.settings
    assert _get_producer(request) is producer
    assert _get_redis(request) is redis_client
    assert _get_runtime_controller(request) is runtime_controller

    modifier_service = build_orchestration_modifier_service(session=session)
    health_service = build_health_service(
        session=session,
        redis_client=redis_client,
        producer=producer,
    )
    governance_service = build_governance_service(
        session=session,
        producer=producer,
        oje_service=OJEPipelineServiceStub(),
    )
    fleet_service = build_fleet_service(
        session=session,
        settings=app.state.settings,
        producer=producer,
        registry_service=registry_service,
        modifier_service=modifier_service,
        health_service=health_service,
        runtime_controller=runtime_controller,
    )
    resolved_health = await get_health_service(request, session=session)
    resolved_governance = await get_governance_service(
        request,
        session=session,
        oje_service=OJEPipelineServiceStub(),
    )
    resolved_fleet = await get_fleet_service(
        request,
        session=session,
        registry_service=registry_service,
        health_service=health_service,
    )

    register_fleet_event_types()
    correlation = CorrelationContext(correlation_id=uuid4(), workspace_id=uuid4())
    await publish_fleet_event(
        producer,
        FleetEventType.fleet_created,
        FleetCreatedPayload(
            fleet_id=uuid4(),
            workspace_id=uuid4(),
            name="Fleet",
            topology_type="hierarchical",
        ),
        correlation,
    )
    await publish_fleet_event(
        producer,
        FleetEventType.fleet_health_updated,
        FleetHealthUpdatedPayload(
            fleet_id=uuid4(),
            workspace_id=uuid4(),
            health_pct=1.0,
            quorum_met=True,
            status="active",
            available_count=2,
            total_count=2,
            member_statuses=[],
        ),
        correlation,
    )

    assert modifier_service is not None
    assert health_service is not None
    assert governance_service is not None
    assert isinstance(fleet_service, FleetService)
    assert resolved_health is not None
    assert resolved_governance is not None
    assert isinstance(resolved_fleet, FleetService)
    assert producer.events[0]["topic"] == "fleet.events"
    assert producer.events[1]["topic"] == "fleet.health"


@pytest.mark.asyncio
async def test_fleet_repositories_cover_crud_helpers() -> None:
    workspace_id = uuid4()
    fleet = build_fleet(workspace_id=workspace_id)
    other_fleet = build_fleet(workspace_id=workspace_id, name="Other")
    member = build_member(fleet_id=fleet.id, workspace_id=workspace_id, role=FleetMemberRole.lead)
    topology = build_topology_version(fleet_id=fleet.id)
    binding = build_policy_binding(fleet_id=fleet.id, workspace_id=workspace_id)
    observer = build_observer_assignment(fleet_id=fleet.id, workspace_id=workspace_id)
    chain = build_governance_chain(fleet_id=fleet.id, workspace_id=workspace_id, is_current=True)
    rules = build_orchestration_rules(fleet_id=fleet.id, workspace_id=workspace_id, is_current=True)
    previous_rules = build_orchestration_rules(
        fleet_id=fleet.id,
        workspace_id=workspace_id,
        version=2,
        is_current=False,
    )

    fleet_session = SessionStub(
        execute_results=[
            QueryResultStub(one=fleet),
            QueryResultStub(one=other_fleet),
            QueryResultStub(many=[fleet, other_fleet]),
            QueryResultStub(many=[fleet]),
            QueryResultStub(many=[fleet]),
        ],
        scalar_results=[2],
    )
    fleet_repo = FleetRepository(fleet_session)
    created = await fleet_repo.create(fleet)
    fetched = await fleet_repo.get_by_id(fleet.id, workspace_id)
    by_name = await fleet_repo.get_by_name_and_workspace(workspace_id, other_fleet.name)
    listed, total = await fleet_repo.list_by_workspace(workspace_id, page=1, page_size=10)
    active = await fleet_repo.list_active()
    active_with_rules = await fleet_repo.list_with_active_rules()
    soft_deleted = await fleet_repo.soft_delete(fleet)
    updated = await fleet_repo.update(other_fleet, name="Renamed")

    member_session = SessionStub(
        execute_results=[
            QueryResultStub(many=[member]),
            QueryResultStub(one=member),
            QueryResultStub(one=member),
            QueryResultStub(one=member),
            QueryResultStub(many=[member]),
        ]
    )
    member_repo = FleetMemberRepository(member_session)
    assert await member_repo.get_by_fleet(fleet.id) == [member]
    assert await member_repo.get_by_id(member.id, fleet.id) == member
    assert await member_repo.get_by_fleet_and_fqn(fleet.id, member.agent_fqn) == member
    assert await member_repo.get_lead(fleet.id) == member
    assert await member_repo.add(member) == member
    await member_repo.remove(member)
    assert await member_repo.update_role(member, FleetMemberRole.observer) == member
    assert await member_repo.get_by_agent_fqn_across_fleets(member.agent_fqn) == [member]

    topology_session = SessionStub(
        execute_results=[
            QueryResultStub(one=topology),
            QueryResultStub(one=topology),
            QueryResultStub(many=[topology]),
        ]
    )
    topology_repo = FleetTopologyVersionRepository(topology_session)
    assert await topology_repo.get_current(fleet.id) == topology
    assert await topology_repo.create_version(topology) == topology
    assert await topology_repo.list_history(fleet.id) == [topology]

    binding_session = SessionStub(
        execute_results=[
            QueryResultStub(one=binding),
            QueryResultStub(one=binding),
            QueryResultStub(many=[binding]),
        ]
    )
    binding_repo = FleetPolicyBindingRepository(binding_session)
    assert await binding_repo.get_by_id(binding.id, fleet.id) == binding
    assert await binding_repo.get_by_policy(fleet.id, binding.policy_id) == binding
    assert await binding_repo.bind(binding) == binding
    await binding_repo.unbind(binding)
    assert await binding_repo.list_by_fleet(fleet.id) == [binding]

    observer_session = SessionStub(
        execute_results=[
            QueryResultStub(one=observer),
            QueryResultStub(one=observer),
            QueryResultStub(many=[observer]),
        ]
    )
    observer_repo = ObserverAssignmentRepository(observer_session)
    assert await observer_repo.get_by_id(observer.id, fleet.id) == observer
    assert (
        await observer_repo.get_active_by_fleet_and_fqn(fleet.id, observer.observer_fqn) == observer
    )
    assert await observer_repo.assign(observer) == observer
    assert await observer_repo.deactivate(observer) == observer
    assert await observer_repo.list_active_by_fleet(fleet.id) == [observer]

    governance_session = SessionStub(
        execute_results=[
            QueryResultStub(one=chain),
            QueryResultStub(one=chain),
            QueryResultStub(many=[chain]),
        ]
    )
    governance_repo = FleetGovernanceChainRepository(governance_session)
    assert await governance_repo.get_current(fleet.id) == chain
    assert await governance_repo.create_version(chain) == chain
    assert await governance_repo.list_history(fleet.id) == [chain]

    rules_session = SessionStub(
        execute_results=[
            QueryResultStub(one=rules),
            QueryResultStub(one=rules),
            QueryResultStub(many=[rules, previous_rules]),
            QueryResultStub(one=previous_rules),
            QueryResultStub(one=previous_rules),
            QueryResultStub(many=[rules, previous_rules]),
        ]
    )
    rules_repo = FleetOrchestrationRulesRepository(rules_session)
    assert await rules_repo.get_current(fleet.id) == rules
    assert await rules_repo.create_version(rules) == rules
    assert await rules_repo.list_history(fleet.id) == [rules, previous_rules]
    assert await rules_repo.get_by_version(fleet.id, previous_rules.version) == previous_rules
    assert await rules_repo.set_current_version(fleet.id, previous_rules.version) == previous_rules
    assert previous_rules.is_current is True
    assert rules.is_current is False

    assert created == fleet
    assert fetched == fleet
    assert by_name == other_fleet
    assert listed == [fleet, other_fleet]
    assert total == 2
    assert active == [fleet]
    assert active_with_rules == [fleet]
    assert soft_deleted.deleted_at is not None
    assert updated.name == "Renamed"


def test_fleet_router_workspace_resolution_prefers_header_then_roles() -> None:
    header_workspace_id = uuid4()
    role_workspace_id = uuid4()

    from_header = fleet_workspace_id(
        _request_with_headers((b"x-workspace-id", str(header_workspace_id).encode("utf-8"))),
        {},
    )
    from_roles = fleet_workspace_id(
        _request_with_headers(),
        {"roles": [{"workspace_id": str(role_workspace_id)}]},
    )

    assert from_header == header_workspace_id
    assert from_roles == role_workspace_id

    with pytest.raises(ValidationError, match="workspace_id is required"):
        fleet_workspace_id(_request_with_headers(), {})
