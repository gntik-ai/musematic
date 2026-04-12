from __future__ import annotations

from platform.common.events.envelope import EventEnvelope
from platform.fleets.exceptions import (
    FleetNameConflictError,
    FleetNotFoundError,
    FleetStateError,
    QuorumNotMetError,
)
from platform.fleets.governance import FleetGovernanceChainService, _correlation
from platform.fleets.health import FleetHealthProjectionService
from platform.fleets.models import (
    FleetMemberRole,
    FleetStatus,
    FleetTopologyType,
)
from platform.fleets.schemas import (
    FleetGovernanceChainUpdate,
    FleetMemberCreate,
    FleetTopologyUpdateRequest,
    FleetUpdate,
)
from platform.fleets.service import (
    FleetOrchestrationModifierService,
    _extract_agent_fqn,
    _rules_payload,
    make_correlation,
    route_execution_event_to_observers,
)
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.auth_support import FakeAsyncRedisClient, RecordingProducer
from tests.fleet_support import (
    ForwardingProducerStub,
    OJEPipelineServiceStub,
    RuntimeControllerStub,
    build_fleet,
    build_fleet_create,
    build_fleet_service_stack,
    build_governance_chain,
    build_member,
    build_rules_create,
)


@pytest.mark.asyncio
async def test_fleet_service_core_crud_rules_and_archive_flow() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service, deps = build_fleet_service_stack(
        known_fqns={"agent:lead", "agent:worker-1", "agent:worker-2"}
    )

    created = await service.create_fleet(
        workspace_id,
        build_fleet_create(),
        actor_id,
    )
    fetched = await service.get_fleet(created.id, workspace_id)
    listed = await service.list_fleets(workspace_id, page=1, page_size=10)
    active = await service.list_active_fleets()
    updated = await service.update_fleet(
        created.id,
        workspace_id,
        FleetUpdate(quorum_min=3),
    )
    topology_history = await service.get_topology_history(created.id, workspace_id)
    rules = await service.get_orchestration_rules(created.id, workspace_id)
    updated_rules = await service.update_orchestration_rules(
        created.id,
        workspace_id,
        build_rules_create(max_parallelism=4),
    )
    rules_history = await service.get_rules_history(created.id, workspace_id)
    governance_chain = await service.get_governance_chain(created.id, workspace_id)
    members = await service.get_fleet_members(created.id, workspace_id)
    archived = await service.archive_fleet(created.id, workspace_id)

    assert created.name == "Fleet Alpha"
    assert fetched.id == created.id
    assert listed.total == 1
    assert len(active) == 1
    assert updated.quorum_min == 3
    assert topology_history.total == 1
    assert rules.version == 1
    assert updated_rules.version == 2
    assert rules_history.total == 2
    assert governance_chain.version == 1
    assert archived.status == FleetStatus.archived
    assert len(members) == 3
    assert any(member.role == FleetMemberRole.lead for member in members)
    assert deps.governance_repo.chains[created.id][0].is_current is False
    assert deps.rules_repo.rules[created.id][-1].is_current is False
    assert [event["event_type"] for event in deps.producer.events] == [
        "fleet.created",
        "fleet.orchestration_rules.updated",
        "fleet.archived",
    ]

    with pytest.raises(FleetNotFoundError):
        await service.get_fleet(created.id, uuid4())


@pytest.mark.asyncio
async def test_fleet_service_members_topology_policy_observer_and_failure_paths() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    runtime_controller = RuntimeControllerStub()
    service, deps = build_fleet_service_stack(
        known_fqns={
            "agent:lead",
            "agent:worker-1",
            "agent:worker-2",
            "agent:worker-3",
            "observer:quality",
        },
        runtime_controller=runtime_controller,
    )
    created = await service.create_fleet(workspace_id, build_fleet_create(), actor_id)
    members = await service.list_members(created.id, workspace_id)
    extra_member = await service.add_member(
        created.id,
        workspace_id,
        FleetMemberCreate(agent_fqn="agent:worker-3", role=FleetMemberRole.worker),
    )

    with pytest.raises(FleetStateError):
        await service.add_member(
            created.id,
            workspace_id,
            FleetMemberCreate(agent_fqn="agent:worker-3", role=FleetMemberRole.worker),
        )

    with pytest.raises(FleetStateError):
        await service.add_member(
            created.id,
            workspace_id,
            FleetMemberCreate(agent_fqn="missing:agent", role=FleetMemberRole.worker),
        )

    worker_member = next(
        member for member in members.items if member.role == FleetMemberRole.worker
    )
    with pytest.raises(FleetStateError):
        await service.update_member_role(
            created.id,
            worker_member.id,
            workspace_id,
            FleetMemberRole.lead,
        )

    peer_topology = await service.update_topology(
        created.id,
        workspace_id,
        FleetTopologyUpdateRequest(
            topology_type=FleetTopologyType.peer_to_peer,
            config={},
        ),
    )
    lead_after_peer = await deps.member_repo.get_lead(created.id)
    hierarchical_topology = await service.update_topology(
        created.id,
        workspace_id,
        FleetTopologyUpdateRequest(
            topology_type=FleetTopologyType.hierarchical,
            config={"lead_fqn": "agent:worker-1"},
        ),
    )
    reassigned_lead = await deps.member_repo.get_lead(created.id)
    await service.update_fleet(created.id, workspace_id, FleetUpdate(quorum_min=4))

    with pytest.raises(QuorumNotMetError):
        await service.remove_member(created.id, extra_member.id, workspace_id)

    await service.update_fleet(created.id, workspace_id, FleetUpdate(quorum_min=2))
    await service.remove_member(created.id, extra_member.id, workspace_id)

    policy_id = uuid4()
    binding = await service.bind_policy(created.id, workspace_id, policy_id, actor_id)
    with pytest.raises(FleetStateError):
        await service.bind_policy(created.id, workspace_id, policy_id, actor_id)
    await service.unbind_policy(created.id, binding.id, workspace_id)
    with pytest.raises(FleetStateError):
        await service.unbind_policy(created.id, binding.id, workspace_id)

    observer = await service.assign_observer(created.id, workspace_id, "observer:quality")
    with pytest.raises(FleetStateError):
        await service.assign_observer(created.id, workspace_id, "observer:quality")
    await service.remove_observer(created.id, observer.id, workspace_id)
    with pytest.raises(FleetStateError):
        await service.remove_observer(created.id, uuid4(), workspace_id)

    await service.record_member_failure(created.id, "agent:worker-1")

    assert peer_topology.version == 2
    assert lead_after_peer is None
    assert hierarchical_topology.version == 3
    assert reassigned_lead is not None
    assert reassigned_lead.agent_fqn == "agent:worker-1"
    assert runtime_controller.failures == [
        {"fleet_id": str(created.id), "agent_fqn": "agent:worker-1"}
    ]


@pytest.mark.asyncio
async def test_modifier_helpers_and_event_forwarding() -> None:
    modifier_service = FleetOrchestrationModifierService()
    default_modifier = await modifier_service.get_modifier(uuid4())
    assert default_modifier == await modifier_service.get_modifier(uuid4())

    class PersonalityStub:
        async def get_modifier(self, fleet_id):
            del fleet_id
            return {"max_wait_ms": 25, "require_quorum_for_decision": True}

    delegated_modifier = await FleetOrchestrationModifierService(
        personality_service=PersonalityStub()
    ).get_modifier(uuid4())

    correlation = make_correlation(uuid4(), fleet_id=uuid4())
    payload = _rules_payload(build_rules_create(max_parallelism=2))
    forwarded_producer = ForwardingProducerStub()
    workspace_id = uuid4()
    fleet_id = uuid4()
    member_repo = build_fleet_service_stack()[1].member_repo
    await member_repo.add(
        build_member(
            fleet_id=fleet_id,
            workspace_id=workspace_id,
            agent_fqn="agent:worker",
        )
    )
    envelope = EventEnvelope(
        event_type="workflow.runtime.completed",
        source="tests",
        correlation_context=correlation,
        payload={"runtime": {"agent_fqn": "agent:worker"}},
    )

    await route_execution_event_to_observers(
        envelope,
        member_repo=member_repo,
        producer=forwarded_producer,
    )

    assert delegated_modifier.max_wait_ms == 25
    assert delegated_modifier.require_quorum_for_decision is True
    assert payload["max_parallelism"] == 2
    assert _extract_agent_fqn({"source_agent_fqn": "agent:one"}) == "agent:one"
    assert _extract_agent_fqn({"participant_identity": "agent:two"}) == "agent:two"
    assert _extract_agent_fqn({}) is None
    assert _correlation(workspace_id, fleet_id).fleet_id == fleet_id
    assert forwarded_producer.raw.messages[0]["topic"] == "fleet.events"


@pytest.mark.asyncio
async def test_fleet_service_error_paths_and_forwarding_guards() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service, deps = build_fleet_service_stack(
        known_fqns={"agent:lead", "agent:worker-1", "agent:worker-2", "agent:new-lead"}
    )
    created = await service.create_fleet(workspace_id, build_fleet_create(), actor_id)

    with pytest.raises(FleetNameConflictError):
        await service.create_fleet(
            workspace_id,
            build_fleet_create(name="Fleet Alpha"),
            actor_id,
        )

    deps.fleet_repo.fleets[created.id].status = FleetStatus.archived
    with pytest.raises(FleetStateError, match="cannot be archived"):
        await service.archive_fleet(created.id, workspace_id)
    deps.fleet_repo.fleets[created.id].status = FleetStatus.active

    with pytest.raises(FleetStateError, match="one lead"):
        await service.add_member(
            created.id,
            workspace_id,
            FleetMemberCreate(
                agent_fqn="agent:new-lead",
                role=FleetMemberRole.lead,
            ),
        )

    with pytest.raises(FleetStateError, match="member was not found"):
        await service.remove_member(created.id, uuid4(), workspace_id)

    with pytest.raises(FleetStateError, match="member was not found"):
        await service.update_member_role(
            created.id,
            uuid4(),
            workspace_id,
            FleetMemberRole.observer,
        )

    members = await service.get_fleet_members(created.id)
    assert len(members) == 3

    saved_rules = deps.rules_repo.rules.pop(created.id)
    with pytest.raises(FleetStateError, match="rules were not found"):
        await service.get_orchestration_rules(created.id)
    deps.rules_repo.rules[created.id] = saved_rules

    saved_chains = deps.governance_repo.chains.pop(created.id)
    with pytest.raises(FleetStateError, match="governance chain was not found"):
        await service.get_governance_chain(created.id, workspace_id)
    deps.governance_repo.chains[created.id] = saved_chains

    default_modifier = await FleetOrchestrationModifierService(
        personality_service=object()
    ).get_modifier(created.id)
    assert default_modifier.max_wait_ms is None
    assert default_modifier.require_quorum_for_decision is False

    service.registry_service = SimpleNamespace()
    await service._ensure_agent_exists(workspace_id, "agent:unknown")

    class SyncRuntimeController:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []

        def record_member_failure(self, *, fleet_id: str, agent_fqn: str) -> None:
            self.calls.append({"fleet_id": fleet_id, "agent_fqn": agent_fqn})

    service.health_service = None
    controller = SyncRuntimeController()
    service.runtime_controller = controller
    await service.record_member_failure(created.id, "agent:worker-1")

    envelope = EventEnvelope(
        event_type="workflow.runtime.completed",
        source="tests",
        correlation_context=make_correlation(workspace_id, fleet_id=created.id),
        payload={"runtime": {"agent_fqn": "agent:worker-1"}},
    )
    no_raw_producer = RecordingProducer()
    empty_member_repo = build_fleet_service_stack()[1].member_repo

    await route_execution_event_to_observers(
        envelope,
        member_repo=deps.member_repo,
        producer=None,
    )
    await route_execution_event_to_observers(
        EventEnvelope(
            event_type="workflow.runtime.completed",
            source="tests",
            correlation_context=make_correlation(workspace_id, fleet_id=created.id),
            payload={},
        ),
        member_repo=deps.member_repo,
        producer=ForwardingProducerStub(),
    )
    await route_execution_event_to_observers(
        envelope,
        member_repo=empty_member_repo,
        producer=ForwardingProducerStub(),
    )
    await route_execution_event_to_observers(
        envelope,
        member_repo=deps.member_repo,
        producer=no_raw_producer,
    )

    assert controller.calls == [
        {"fleet_id": str(created.id), "agent_fqn": "agent:worker-1"}
    ]
    assert no_raw_producer.events == []


@pytest.mark.asyncio
async def test_governance_service_and_health_projection_flows() -> None:
    workspace_id = uuid4()
    fleet = build_fleet(workspace_id=workspace_id, quorum_min=2)
    lead = build_member(
        fleet_id=fleet.id,
        workspace_id=workspace_id,
        agent_fqn="agent:lead",
        role=FleetMemberRole.lead,
    )
    worker = build_member(
        fleet_id=fleet.id,
        workspace_id=workspace_id,
        agent_fqn="agent:worker",
    )
    redis = FakeAsyncRedisClient()
    producer = RecordingProducer()
    _service, deps = build_fleet_service_stack(
        known_fqns={"agent:lead", "agent:worker"},
        producer=producer,
        redis_client=redis,
    )
    deps.fleet_repo.fleets[fleet.id] = fleet
    deps.member_repo.members[lead.id] = lead
    deps.member_repo.members[worker.id] = worker
    default_chain = build_governance_chain(
        fleet_id=fleet.id,
        workspace_id=workspace_id,
        is_current=True,
        is_default=True,
    )
    deps.governance_repo.chains[fleet.id] = [default_chain]

    governance = FleetGovernanceChainService(
        fleet_repo=deps.fleet_repo,
        governance_repo=deps.governance_repo,
        producer=producer,
        oje_service=OJEPipelineServiceStub(),
    )
    health = FleetHealthProjectionService(
        fleet_repo=deps.fleet_repo,
        member_repo=deps.member_repo,
        redis_client=redis,
        producer=producer,
    )

    current_chain = await governance.get_chain(fleet.id, workspace_id)
    updated_chain = await governance.update_chain(
        fleet.id,
        workspace_id,
        FleetGovernanceChainUpdate(
            observer_fqns=["observer:new"],
            judge_fqns=["judge:new"],
            enforcer_fqns=["enforcer:new"],
            policy_binding_ids=[],
        ),
    )
    history = await governance.get_chain_history(fleet.id, workspace_id)
    verdict = await governance.trigger_oje_pipeline(
        fleet.id,
        workspace_id,
        {"severity": "high"},
    )

    projection = await health.get_health(fleet.id, workspace_id)
    await health.handle_member_availability_change("agent:worker", is_available=False)
    paused_projection = await health.refresh_health(fleet.id)
    await health.handle_member_availability_change("agent:worker", is_available=True)
    cached_projection = await health.get_health(fleet.id, workspace_id)

    assert current_chain.version == 1
    assert updated_chain.version == 2
    assert history.total == 2
    assert verdict["status"] == "processed"
    assert projection.status == FleetStatus.active
    assert paused_projection.status == FleetStatus.paused
    assert cached_projection.fleet_id == fleet.id
    assert any(event["event_type"] == "fleet.status.changed" for event in producer.events)
    assert any(event["topic"] == "interaction.attention" for event in producer.events)

    with pytest.raises(FleetNotFoundError):
        await governance.get_chain(uuid4(), workspace_id)


@pytest.mark.asyncio
async def test_governance_and_health_edge_paths() -> None:
    workspace_id = uuid4()
    producer = RecordingProducer()
    redis = FakeAsyncRedisClient()
    _service, deps = build_fleet_service_stack(
        known_fqns={"agent:lead"},
        producer=producer,
        redis_client=redis,
    )
    governance = FleetGovernanceChainService(
        fleet_repo=deps.fleet_repo,
        governance_repo=deps.governance_repo,
        producer=producer,
        oje_service=object(),
    )
    health = deps.health_service

    with pytest.raises(FleetNotFoundError):
        await health.get_health(uuid4(), workspace_id)

    with pytest.raises(FleetNotFoundError):
        await health.refresh_health(uuid4())

    fleet = build_fleet(workspace_id=workspace_id, quorum_min=1)
    lead = build_member(
        fleet_id=fleet.id,
        workspace_id=workspace_id,
        agent_fqn="agent:lead",
        role=FleetMemberRole.lead,
    )
    deps.fleet_repo.fleets[fleet.id] = fleet
    deps.member_repo.members[lead.id] = lead
    default_chain = await governance.create_default_chain(fleet.id, workspace_id)
    skipped = await governance.trigger_oje_pipeline(
        fleet.id,
        workspace_id,
        {"reason": "interface missing"},
    )

    raw_redis = await redis._get_client()
    scan_results = [
        (1, []),
        (0, [f"fleet:member:avail:{fleet.id}:agent:lead".encode()]),
    ]

    async def scan_with_bytes(
        *,
        cursor: int = 0,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, list[bytes]]:
        del cursor, match, count
        next_cursor, keys = scan_results.pop(0)
        return next_cursor, keys

    raw_redis.scan = scan_with_bytes  # type: ignore[assignment]
    refreshed = await health.refresh_health(fleet.id)
    cached = await health.get_health(fleet.id, workspace_id)
    await health.handle_member_availability_change("missing:agent", is_available=False)

    assert default_chain.is_default is True
    assert skipped["status"] == "skipped"
    assert refreshed.available_count == 1
    assert cached.fleet_id == fleet.id

    deps.governance_repo.chains[fleet.id] = []
    with pytest.raises(FleetStateError, match="governance chain was not found"):
        await governance.get_chain(fleet.id, workspace_id)
