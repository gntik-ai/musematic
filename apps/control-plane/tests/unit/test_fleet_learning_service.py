from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.exceptions import ValidationError
from platform.fleet_learning.adaptation import FleetAdaptationEngineService
from platform.fleet_learning.exceptions import (
    AdaptationError,
    IncompatibleTopologyError,
    TransferError,
)
from platform.fleet_learning.models import (
    AutonomyLevel,
    CommunicationStyle,
    DecisionSpeed,
    RiskTolerance,
    TransferRequestStatus,
)
from platform.fleet_learning.personality import FleetPersonalityProfileService
from platform.fleet_learning.schemas import FleetPerformanceProfileQuery, TransferRejectRequest
from platform.fleet_learning.transfer import CrossFleetTransferService
from platform.fleets.models import FleetMemberRole, FleetTopologyType
from uuid import uuid4

import pytest

from tests.auth_support import RecordingProducer
from tests.fleet_support import (
    ObjectStorageStub,
    build_adaptation_log,
    build_adaptation_rule,
    build_adaptation_rule_create,
    build_fleet,
    build_fleet_learning_stack,
    build_fleet_service_stack,
    build_member,
    build_orchestration_rules,
    build_personality_create,
    build_personality_profile,
    build_profile,
    build_rules_create,
    build_topology_version,
    build_transfer_create,
    build_transfer_request,
)


@pytest.mark.asyncio
async def test_performance_service_computes_profiles_history_and_guards_workspace() -> None:
    workspace_id = uuid4()
    service, fleet_deps = build_fleet_service_stack(known_fqns={"agent:lead", "agent:worker"})
    fleet = build_fleet(workspace_id=workspace_id)
    fleet_deps.fleet_repo.fleets[fleet.id] = fleet
    fleet_deps.member_repo.members = {
        member.id: member
        for member in [
            build_member(
                fleet_id=fleet.id,
                workspace_id=workspace_id,
                agent_fqn="agent:lead",
                role=FleetMemberRole.lead,
            ),
            build_member(
                fleet_id=fleet.id,
                workspace_id=workspace_id,
                agent_fqn="agent:worker",
            ),
        ]
    }
    learning, deps = build_fleet_learning_stack(fleet_service=service)
    deps.clickhouse.query_responses.append(
        [
            {
                "agent_fqn": "agent:lead",
                "avg_completion_time_ms": 100.0,
                "execution_count": 6,
                "success_rate": 1.0,
                "cost_per_task": 0.2,
                "quality_score": 0.95,
            },
            {
                "agent_fqn": "agent:worker",
                "avg_completion_time_ms": 12000.0,
                "execution_count": 6,
                "success_rate": 0.5,
                "cost_per_task": 0.8,
                "quality_score": 0.6,
            },
        ]
    )

    end = datetime.now(UTC)
    start = end - timedelta(hours=2)
    computed = await learning.performance.compute_profile(fleet.id, workspace_id, start, end)
    all_profiles = await learning.performance.compute_all_profiles(start, end)
    profile = await learning.performance.get_profile(
        fleet.id,
        workspace_id,
        FleetPerformanceProfileQuery(start=start, end=end),
    )
    history = await learning.performance.get_profile_history(fleet.id, workspace_id)

    assert computed.fleet_id == fleet.id
    assert computed.avg_completion_time_ms > 0
    assert computed.throughput_per_hour == pytest.approx(6.0)
    assert all_profiles[0].fleet_id == fleet.id
    assert profile.fleet_id == fleet.id
    assert history[0].fleet_id == fleet.id

    with pytest.raises(ValueError, match="No performance profile exists"):
        await learning.performance.get_profile(
            uuid4(),
            workspace_id,
            FleetPerformanceProfileQuery(start=start, end=end),
        )

    with pytest.raises(ValueError, match="does not belong to workspace"):
        await learning.performance.get_profile(
            fleet.id,
            uuid4(),
            FleetPerformanceProfileQuery(start=start, end=end),
        )


@pytest.mark.asyncio
async def test_adaptation_service_rule_crud_evaluation_revert_and_bulk_evaluation() -> None:
    workspace_id = uuid4()
    producer = RecordingProducer()
    service, fleet_deps = build_fleet_service_stack(known_fqns={"agent:lead"}, producer=producer)
    fleet = build_fleet(workspace_id=workspace_id)
    fleet_deps.fleet_repo.fleets[fleet.id] = fleet
    fleet_deps.rules_repo.rules[fleet.id] = [
        build_orchestration_rules(fleet_id=fleet.id, workspace_id=workspace_id)
    ]
    learning, deps = build_fleet_learning_stack(fleet_service=service, producer=producer)
    deps.rules_repo = fleet_deps.rules_repo
    learning.adaptation.rules_repo = fleet_deps.rules_repo
    deps.performance_repo.profiles[fleet.id] = [
        build_profile(
            fleet_id=fleet.id,
            workspace_id=workspace_id,
            avg_completion_time_ms=40.0,
        )
    ]

    created = await learning.adaptation.create_rule(
        fleet.id,
        workspace_id,
        build_adaptation_rule_create(),
    )
    listed = await learning.adaptation.list_rules(fleet.id, workspace_id)
    updated = await learning.adaptation.update_rule(
        fleet.id,
        created.id,
        workspace_id,
        build_adaptation_rule_create(threshold=35.0),
    )
    logs = await learning.adaptation.evaluate_rules_for_fleet(fleet.id)
    history = await learning.adaptation.list_log(fleet.id, workspace_id)
    reverted = await learning.adaptation.revert_adaptation(logs[0].id, workspace_id)
    bulk = await learning.adaptation.evaluate_all_fleets()
    await learning.adaptation.deactivate_rule(fleet.id, created.id, workspace_id)

    assert created.id == updated.id
    assert len(listed) == 1
    assert logs[0].after_rules_version == 2
    assert history[0].id == logs[0].id
    assert reverted.is_reverted is True
    assert len(bulk) == 1
    assert bulk[0].fleet_id == fleet.id
    assert any(event["event_type"] == "fleet.adaptation.applied" for event in producer.events)

    with pytest.raises(AdaptationError):
        await learning.adaptation.revert_adaptation(logs[0].id, workspace_id)

    with pytest.raises(AdaptationError):
        FleetAdaptationEngineService._apply_action({}, {"type": "unknown", "value": 1})


@pytest.mark.asyncio
async def test_transfer_service_inline_large_payload_apply_revert_and_reject_flows() -> None:
    workspace_id = uuid4()
    service, fleet_deps = build_fleet_service_stack(known_fqns={"agent:lead"})
    source_fleet = build_fleet(workspace_id=workspace_id, name="Source")
    target_fleet = build_fleet(workspace_id=workspace_id, name="Target")
    fleet_deps.fleet_repo.fleets[source_fleet.id] = source_fleet
    fleet_deps.fleet_repo.fleets[target_fleet.id] = target_fleet
    fleet_deps.topology_repo.versions[source_fleet.id] = [
        build_topology_version(
            fleet_id=source_fleet.id,
            topology_type=FleetTopologyType.hierarchical,
            config={"lead_fqn": "agent:lead"},
        )
    ]
    fleet_deps.topology_repo.versions[target_fleet.id] = [
        build_topology_version(
            fleet_id=target_fleet.id,
            topology_type=FleetTopologyType.peer_to_peer,
            config={},
        )
    ]
    fleet_deps.rules_repo.rules[target_fleet.id] = [
        build_orchestration_rules(fleet_id=target_fleet.id, workspace_id=workspace_id, version=1)
    ]
    learning, deps = build_fleet_learning_stack(
        fleet_service=service,
        object_storage=ObjectStorageStub(),
    )
    deps.topology_repo.versions[target_fleet.id] = fleet_deps.topology_repo.versions[
        target_fleet.id
    ]
    deps.rules_repo.rules[target_fleet.id] = fleet_deps.rules_repo.rules[target_fleet.id]

    proposed = await learning.transfer.propose(
        source_fleet.id,
        workspace_id,
        build_transfer_create(target_fleet.id),
        uuid4(),
    )
    approved = await learning.transfer.approve(proposed.id, workspace_id, uuid4())
    applied = await learning.transfer.apply(proposed.id, workspace_id)
    reverted = await learning.transfer.revert(proposed.id, workspace_id)

    large_request = build_transfer_create(target_fleet.id)
    large_request.pattern_definition["blob"] = "x" * (60 * 1024)
    large_proposed = await learning.transfer.propose(
        source_fleet.id,
        workspace_id,
        large_request,
        uuid4(),
    )
    rejected = await learning.transfer.reject(
        large_proposed.id,
        workspace_id,
        TransferRejectRequest(reason="mismatch"),
    )
    listed = await learning.transfer.list_for_fleet(source_fleet.id, workspace_id)
    fetched = await learning.transfer.get(proposed.id, workspace_id)

    assert proposed.status == TransferRequestStatus.proposed
    assert approved.status == TransferRequestStatus.approved
    assert applied.status == TransferRequestStatus.applied
    assert reverted.reverted_at is not None
    assert large_proposed.pattern_minio_key is not None
    assert rejected.status == TransferRequestStatus.rejected
    assert len(listed) == 2
    assert fetched.id == proposed.id

    with pytest.raises(TransferError):
        await learning.transfer.approve(proposed.id, workspace_id, uuid4())

    hierarchical_topology = build_topology_version(
        fleet_id=target_fleet.id,
        topology_type=FleetTopologyType.hierarchical,
        config={},
    )
    with pytest.raises(IncompatibleTopologyError):
        CrossFleetTransferService._adapt_pattern(
            {"delegation": {"config": {}}},
            {"delegation": {"config": {}}},
            hierarchical_topology.config,
            hierarchical_topology.topology_type,
            uuid4(),
        )


@pytest.mark.asyncio
async def test_personality_service_defaults_updates_and_modifier_mapping() -> None:
    workspace_id = uuid4()
    fleet_id = uuid4()
    _, deps = build_fleet_learning_stack(fleet_service=build_fleet_service_stack()[0])
    repo = deps.personality_repo
    service = FleetPersonalityProfileService(repository=repo)

    default_profile = await service.get(fleet_id, workspace_id)
    updated = await service.update(
        fleet_id,
        workspace_id,
        build_personality_create(
            communication_style=CommunicationStyle.structured,
            decision_speed=DecisionSpeed.consensus_seeking,
            risk_tolerance=RiskTolerance.conservative,
            autonomy_level=AutonomyLevel.fully_autonomous,
        ),
    )
    modifier = await service.get_modifier(fleet_id)

    assert default_profile.autonomy_level == AutonomyLevel.semi_autonomous
    assert updated.version == 1
    assert modifier.require_quorum_for_decision is True
    assert modifier.escalate_unverified is True
    assert modifier.auto_approve is True

    repo.profiles[fleet_id] = [
        build_personality_profile(
            fleet_id=fleet_id,
            workspace_id=workspace_id,
            decision_speed=DecisionSpeed.fast,
        )
    ]
    fast_modifier = await service.get_modifier(fleet_id)
    assert fast_modifier.max_wait_ms == 0


@pytest.mark.asyncio
async def test_fleet_learning_error_paths_and_private_helpers() -> None:
    workspace_id = uuid4()
    service, fleet_deps = build_fleet_service_stack(known_fqns={"agent:lead"})
    source_fleet = build_fleet(workspace_id=workspace_id, name="Source")
    target_fleet = build_fleet(workspace_id=workspace_id, name="Target")
    fleet_deps.fleet_repo.fleets[source_fleet.id] = source_fleet
    fleet_deps.fleet_repo.fleets[target_fleet.id] = target_fleet
    fleet_deps.rules_repo.rules[source_fleet.id] = [
        build_orchestration_rules(fleet_id=source_fleet.id, workspace_id=workspace_id, version=1)
    ]
    fleet_deps.rules_repo.rules[target_fleet.id] = [
        build_orchestration_rules(fleet_id=target_fleet.id, workspace_id=workspace_id, version=1)
    ]
    learning, deps = build_fleet_learning_stack(
        fleet_service=service,
        object_storage=ObjectStorageStub(),
    )
    learning.adaptation.rules_repo = fleet_deps.rules_repo
    deps.rules_repo = fleet_deps.rules_repo
    deps.topology_repo.versions[target_fleet.id] = [
        build_topology_version(
            fleet_id=target_fleet.id,
            topology_type=FleetTopologyType.peer_to_peer,
            config={},
        )
    ]

    with pytest.raises(AdaptationError, match="rule was not found"):
        await learning.adaptation.update_rule(
            source_fleet.id,
            uuid4(),
            workspace_id,
            build_adaptation_rule_create(),
        )

    with pytest.raises(AdaptationError, match="rule was not found"):
        await learning.adaptation.deactivate_rule(source_fleet.id, uuid4(), workspace_id)

    assert await learning.adaptation.evaluate_rules_for_fleet(source_fleet.id) == []

    deps.performance_repo.profiles[source_fleet.id] = [
        build_profile(
            fleet_id=source_fleet.id,
            workspace_id=workspace_id,
            avg_completion_time_ms=10.0,
        )
    ]
    assert await learning.adaptation.evaluate_rules_for_fleet(source_fleet.id) == []

    non_matching_rule = build_adaptation_rule(
        fleet_id=source_fleet.id,
        workspace_id=workspace_id,
        condition={
            "metric": "avg_completion_time_ms",
            "operator": "gt",
            "threshold": 999.0,
        },
    )
    deps.rule_repo.rules[non_matching_rule.id] = non_matching_rule
    assert await learning.adaptation.evaluate_rules_for_fleet(source_fleet.id) == []

    bad_threshold_rule = build_adaptation_rule(
        fleet_id=source_fleet.id,
        workspace_id=workspace_id,
        condition={
            "metric": "avg_completion_time_ms",
            "operator": "gt",
            "threshold": "not-a-number",
        },
    )
    deps.rule_repo.rules = {bad_threshold_rule.id: bad_threshold_rule}
    with pytest.raises(AdaptationError, match="must be numeric"):
        await learning.adaptation.evaluate_rules_for_fleet(source_fleet.id)

    with pytest.raises(AdaptationError, match="log entry was not found"):
        await learning.adaptation.revert_adaptation(uuid4(), workspace_id)

    missing_version_log = build_adaptation_log(
        fleet_id=source_fleet.id,
        workspace_id=workspace_id,
        before_rules_version=999,
    )
    deps.log_repo.logs[missing_version_log.id] = missing_version_log
    with pytest.raises(AdaptationError, match="Original orchestration rules version was not found"):
        await learning.adaptation.revert_adaptation(missing_version_log.id, workspace_id)

    patched_strategy = FleetAdaptationEngineService._apply_action(
        build_rules_create().model_dump(mode="json"),
        {"type": "set_delegation_strategy", "value": "priority"},
    )
    patched_timeout = FleetAdaptationEngineService._apply_action(
        build_rules_create().model_dump(mode="json"),
        {"type": "set_escalation_timeout", "value": 45},
    )
    patched_aggregation = FleetAdaptationEngineService._apply_action(
        build_rules_create().model_dump(mode="json"),
        {"type": "set_aggregation_strategy", "value": "vote"},
    )
    assert patched_strategy["delegation"]["strategy"] == "priority"
    assert patched_timeout["escalation"]["timeout_seconds"] == 45
    assert patched_aggregation["aggregation"]["strategy"] == "vote"

    current_profile = build_personality_profile(
        fleet_id=source_fleet.id,
        workspace_id=workspace_id,
        decision_speed=DecisionSpeed.deliberate,
    )
    deps.personality_repo.profiles[source_fleet.id] = [current_profile]
    current = await learning.personality.get(source_fleet.id, workspace_id)
    deliberate_modifier = await learning.personality.get_modifier(source_fleet.id)
    assert current.id == current_profile.id
    assert deliberate_modifier.max_wait_ms == 5000

    with pytest.raises(ValidationError, match="must differ"):
        await learning.transfer.propose(
            source_fleet.id,
            workspace_id,
            build_transfer_create(source_fleet.id),
            uuid4(),
        )

    proposed = await learning.transfer.propose(
        source_fleet.id,
        workspace_id,
        build_transfer_create(target_fleet.id),
        uuid4(),
    )
    with pytest.raises(TransferError, match="Only approved transfers can be applied"):
        await learning.transfer.apply(proposed.id, workspace_id)

    approved = await learning.transfer.approve(proposed.id, workspace_id, uuid4())
    deps.topology_repo.versions.pop(target_fleet.id)
    with pytest.raises(TransferError, match="topology was not found"):
        await learning.transfer.apply(approved.id, workspace_id)

    missing_metadata = build_transfer_request(
        workspace_id=workspace_id,
        source_fleet_id=source_fleet.id,
        target_fleet_id=target_fleet.id,
        status=TransferRequestStatus.applied,
        pattern_definition={"metadata": {}},
    )
    deps.transfer_repo.transfers[missing_metadata.id] = missing_metadata
    with pytest.raises(
        TransferError,
        match="missing original orchestration rules version metadata",
    ):
        await learning.transfer.revert(missing_metadata.id, workspace_id)

    missing_version_transfer = build_transfer_request(
        workspace_id=workspace_id,
        source_fleet_id=source_fleet.id,
        target_fleet_id=target_fleet.id,
        status=TransferRequestStatus.applied,
        pattern_definition={"metadata": {"target_before_rules_version": 999}},
    )
    deps.transfer_repo.transfers[missing_version_transfer.id] = missing_version_transfer
    with pytest.raises(TransferError, match="Original orchestration rules version was not found"):
        await learning.transfer.revert(missing_version_transfer.id, workspace_id)

    with pytest.raises(TransferError, match="Transfer request was not found"):
        await learning.transfer.get(uuid4(), workspace_id)

    empty_pattern = build_transfer_request(
        workspace_id=workspace_id,
        source_fleet_id=source_fleet.id,
        target_fleet_id=target_fleet.id,
    )
    empty_pattern.pattern_definition = None
    empty_pattern.pattern_minio_key = None
    assert await learning.transfer._load_pattern(empty_pattern) == {}

    invalid_pattern = build_transfer_request(
        workspace_id=workspace_id,
        source_fleet_id=source_fleet.id,
        target_fleet_id=target_fleet.id,
        pattern_definition=None,
        pattern_minio_key="fleet-patterns/test-transfer/pattern.json",
    )
    deps.object_storage.objects[("fleet-patterns", "test-transfer/pattern.json")] = b"[]"
    with pytest.raises(TransferError, match="must be a JSON object"):
        await learning.transfer._load_pattern(invalid_pattern)

    peer_pattern = CrossFleetTransferService._adapt_pattern(
        {},
        {"delegation": {"strategy": "round_robin", "config": {"lead_fqn": "agent:lead"}}},
        {},
        FleetTopologyType.peer_to_peer,
        uuid4(),
    )
    hybrid_pattern = CrossFleetTransferService._adapt_pattern(
        {},
        {"delegation": {"strategy": "priority", "config": {"lead_fqn": "agent:lead"}}},
        {},
        FleetTopologyType.hybrid,
        uuid4(),
    )
    assert "lead_fqn" not in peer_pattern["delegation"]["config"]
    assert hybrid_pattern["delegation"]["config"]["lead_fqn"] == "agent:lead"
