from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.common.events.envelope import CorrelationContext
from platform.common.exceptions import PlatformError, ValidationError, platform_exception_handler
from platform.fleet_learning.dependencies import (
    _get_clickhouse,
    _get_object_storage,
    _get_producer,
    _get_settings,
    build_adaptation_service,
    build_fleet_learning_service,
    build_performance_service,
    build_personality_service,
    build_transfer_service,
    get_adaptation_service,
    get_fleet_learning_service,
    get_performance_service,
    get_personality_service,
    get_transfer_service,
)
from platform.fleet_learning.events import (
    publish_adaptation_applied,
    publish_transfer_status_changed,
)
from platform.fleet_learning.models import TransferRequestStatus
from platform.fleet_learning.repository import (
    CrossFleetTransferRepository,
    FleetAdaptationLogRepository,
    FleetAdaptationRuleRepository,
    FleetPerformanceProfileRepository,
    FleetPersonalityProfileRepository,
)
from platform.fleet_learning.router import (
    _workspace_id as learning_workspace_id,
)
from platform.fleet_learning.router import (
    get_transfer,
    revert_adaptation,
    revert_transfer,
    router,
)
from platform.fleet_learning.schemas import TransferRejectRequest
from platform.fleets.events import (
    FleetAdaptationAppliedPayload,
    FleetTransferStatusChangedPayload,
)
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI, Request

from tests.auth_support import RecordingProducer
from tests.fleet_support import (
    ClickHouseStub,
    ObjectStorageStub,
    QueryResultStub,
    SessionStub,
    build_adaptation_log,
    build_adaptation_rule,
    build_adaptation_rule_create,
    build_fleet,
    build_fleet_create,
    build_fleet_learning_stack,
    build_fleet_service_stack,
    build_orchestration_rules,
    build_personality_create,
    build_personality_profile,
    build_profile,
    build_topology_version,
    build_transfer_create,
    build_transfer_request,
)


def _request_with_state(app: FastAPI) -> Request:
    return Request({"type": "http", "app": app, "headers": []})


def _request_with_headers(*headers: tuple[bytes, bytes]) -> Request:
    return Request({"type": "http", "app": FastAPI(), "headers": list(headers)})


@pytest.mark.asyncio
async def test_fleet_learning_router_end_to_end() -> None:
    workspace_id = uuid4()
    user_id = uuid4()
    fleet_service, fleet_deps = build_fleet_service_stack(
        known_fqns={"agent:lead", "agent:worker-1", "agent:worker-2"}
    )
    source_fleet = await fleet_service.create_fleet(workspace_id, build_fleet_create(), user_id)
    target_fleet = build_fleet(workspace_id=workspace_id, name="Target")
    fleet_deps.fleet_repo.fleets[target_fleet.id] = target_fleet
    fleet_deps.topology_repo.versions[target_fleet.id] = [
        build_topology_version(
            fleet_id=target_fleet.id,
            topology_type=source_fleet.topology_type,
            config={"lead_fqn": "agent:lead"},
        )
    ]
    fleet_deps.rules_repo.rules[target_fleet.id] = [
        build_orchestration_rules(fleet_id=target_fleet.id, workspace_id=workspace_id)
    ]

    learning, deps = build_fleet_learning_stack(fleet_service=fleet_service)
    deps.topology_repo.versions[target_fleet.id] = fleet_deps.topology_repo.versions[
        target_fleet.id
    ]
    deps.rules_repo.rules[target_fleet.id] = fleet_deps.rules_repo.rules[
        target_fleet.id
    ]
    deps.clickhouse.query_responses.append(
        [
            {
                "agent_fqn": "agent:lead",
                "avg_completion_time_ms": 2500.0,
                "execution_count": 4,
                "success_rate": 0.9,
                "cost_per_task": 0.4,
                "quality_score": 0.8,
            }
        ]
    )

    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)

    async def _current_user() -> dict[str, str]:
        return {"sub": str(user_id), "workspace_id": str(workspace_id)}

    async def _performance_service():
        return learning.performance

    async def _adaptation_service():
        return learning.adaptation

    async def _transfer_service():
        return learning.transfer

    async def _personality_service():
        return learning.personality

    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_performance_service] = _performance_service
    app.dependency_overrides[get_adaptation_service] = _adaptation_service
    app.dependency_overrides[get_transfer_service] = _transfer_service
    app.dependency_overrides[get_personality_service] = _personality_service

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        computed = await client.post(
            f"/api/v1/fleets/{source_fleet.id}/performance-profile/compute"
        )
        profile = await client.get(f"/api/v1/fleets/{source_fleet.id}/performance-profile")
        profile_history = await client.get(
            f"/api/v1/fleets/{source_fleet.id}/performance-profile/history"
        )
        rule = await client.post(
            f"/api/v1/fleets/{source_fleet.id}/adaptation-rules",
            json=build_adaptation_rule_create().model_dump(mode="json"),
        )
        rules = await client.get(f"/api/v1/fleets/{source_fleet.id}/adaptation-rules")
        updated_rule = await client.put(
            f"/api/v1/fleets/{source_fleet.id}/adaptation-rules/{rule.json()['id']}",
            json=build_adaptation_rule_create(threshold=15.0).model_dump(mode="json"),
        )
        adaptation_log = await client.get(f"/api/v1/fleets/{source_fleet.id}/adaptation-log")
        transfer = await client.post(
            f"/api/v1/fleets/{source_fleet.id}/transfers",
            json=build_transfer_create(target_fleet.id).model_dump(mode="json"),
        )
        approve = await client.post(f"/api/v1/fleets/transfers/{transfer.json()['id']}/approve")
        apply_transfer = await client.post(
            f"/api/v1/fleets/transfers/{transfer.json()['id']}/apply"
        )
        reject_transfer = await client.post(
            f"/api/v1/fleets/transfers/{transfer.json()['id']}/reject",
            json=TransferRejectRequest(reason="no-op").model_dump(mode="json"),
        )
        transfers = await client.get(f"/api/v1/fleets/{source_fleet.id}/transfers")
        personality = await client.get(f"/api/v1/fleets/{source_fleet.id}/personality-profile")
        updated_personality = await client.put(
            f"/api/v1/fleets/{source_fleet.id}/personality-profile",
            json=build_personality_create().model_dump(mode="json"),
        )
        deleted_rule = await client.delete(
            f"/api/v1/fleets/{source_fleet.id}/adaptation-rules/{rule.json()['id']}"
        )

    assert computed.status_code == 202
    assert profile.status_code == 200
    assert profile_history.json()["total"] == 1
    assert rule.status_code == 201
    assert rules.json()["total"] == 1
    assert updated_rule.status_code == 200
    assert adaptation_log.status_code == 200
    assert transfer.status_code == 201
    assert approve.status_code == 200
    assert apply_transfer.status_code == 200
    assert reject_transfer.status_code == 409
    assert transfers.json()["total"] == 1
    assert personality.status_code == 200
    assert updated_personality.status_code == 200
    assert deleted_rule.status_code == 204


@pytest.mark.asyncio
async def test_fleet_learning_dependencies_events_and_aggregate_service() -> None:
    app = FastAPI()
    clickhouse = ClickHouseStub()
    object_storage = ObjectStorageStub()
    producer = RecordingProducer()
    app.state.settings = build_fleet_service_stack()[0].settings
    app.state.clients = {
        "clickhouse": clickhouse,
        "object_storage": object_storage,
        "kafka": producer,
    }
    request = _request_with_state(app)
    session = SessionStub()
    fleet_service = build_fleet_service_stack()[0]

    assert _get_settings(request) is app.state.settings
    assert _get_clickhouse(request) is clickhouse
    assert _get_object_storage(request) is object_storage
    assert _get_producer(request) is producer

    personality = build_personality_service(session=session)
    performance = build_performance_service(
        session=session,
        clickhouse=clickhouse,
        fleet_service=fleet_service,
    )
    adaptation = build_adaptation_service(
        session=session,
        fleet_service=fleet_service,
        producer=producer,
    )
    transfer = build_transfer_service(
        session=session,
        object_storage=object_storage,
        fleet_service=fleet_service,
        producer=producer,
    )
    learning = build_fleet_learning_service(
        session=session,
        clickhouse=clickhouse,
        object_storage=object_storage,
        fleet_service=fleet_service,
        producer=producer,
    )
    resolved_personality = await get_personality_service(request, session=session)
    resolved_performance = await get_performance_service(
        request,
        session=session,
        fleet_service=fleet_service,
    )
    resolved_adaptation = await get_adaptation_service(
        request,
        session=session,
        fleet_service=fleet_service,
    )
    resolved_transfer = await get_transfer_service(
        request,
        session=session,
        fleet_service=fleet_service,
    )
    resolved_learning = await get_fleet_learning_service(
        request,
        session=session,
        fleet_service=fleet_service,
    )

    correlation = CorrelationContext(correlation_id=uuid4(), workspace_id=uuid4(), fleet_id=uuid4())
    await publish_adaptation_applied(
        producer,
        FleetAdaptationAppliedPayload(
            fleet_id=uuid4(),
            workspace_id=uuid4(),
            rule_id=uuid4(),
            before_version=1,
            after_version=2,
        ),
        correlation,
    )
    await publish_transfer_status_changed(
        producer,
        FleetTransferStatusChangedPayload(
            transfer_id=uuid4(),
            workspace_id=uuid4(),
            source_fleet_id=uuid4(),
            target_fleet_id=uuid4(),
            status="approved",
        ),
        correlation,
    )

    assert personality is not None
    assert performance is not None
    assert adaptation is not None
    assert transfer is not None
    assert learning.performance is not None
    assert learning.adaptation is not None
    assert learning.transfer is not None
    assert learning.personality is not None
    assert resolved_personality is not None
    assert resolved_performance is not None
    assert resolved_adaptation is not None
    assert resolved_transfer is not None
    assert resolved_learning is not None
    assert producer.events[0]["event_type"] == "fleet.adaptation.applied"
    assert producer.events[1]["event_type"] == "fleet.transfer.status_changed"


@pytest.mark.asyncio
async def test_fleet_learning_repositories_cover_query_helpers() -> None:
    workspace_id = uuid4()
    fleet_id = uuid4()
    profile = build_profile(fleet_id=fleet_id, workspace_id=workspace_id)
    rule = build_adaptation_rule(fleet_id=fleet_id, workspace_id=workspace_id)
    log = build_adaptation_log(
        fleet_id=fleet_id, workspace_id=workspace_id, adaptation_rule_id=rule.id
    )
    transfer = build_transfer_request(
        workspace_id=workspace_id,
        source_fleet_id=fleet_id,
        target_fleet_id=uuid4(),
    )
    personality = build_personality_profile(fleet_id=fleet_id, workspace_id=workspace_id)

    profile_session = SessionStub(
        execute_results=[
            QueryResultStub(one=profile),
            QueryResultStub(one=profile),
            QueryResultStub(many=[profile]),
            QueryResultStub(many=[profile]),
        ]
    )
    profile_repo = FleetPerformanceProfileRepository(profile_session)
    assert await profile_repo.insert(profile) == profile
    assert await profile_repo.get_latest(fleet_id) == profile
    assert (
        await profile_repo.get_by_range(
            fleet_id,
            start=profile.period_start,
            end=profile.period_end,
        )
        == profile
    )
    assert await profile_repo.list_by_range(fleet_id) == [profile]
    assert (
        await profile_repo.list_by_range(
            fleet_id,
            start=profile.period_start,
            end=profile.period_end,
        )
        == [profile]
    )

    rule_session = SessionStub(
        execute_results=[
            QueryResultStub(one=rule),
            QueryResultStub(one=rule),
            QueryResultStub(many=[rule]),
            QueryResultStub(many=[rule]),
            QueryResultStub(many=[fleet_id]),
        ]
    )
    rule_repo = FleetAdaptationRuleRepository(rule_session)
    assert await rule_repo.create(rule) == rule
    assert await rule_repo.get_by_id(rule.id) == rule
    assert await rule_repo.get_by_id(rule.id, fleet_id) == rule
    assert await rule_repo.list_active_by_priority(fleet_id) == [rule]
    assert await rule_repo.list_by_fleet(fleet_id) == [rule]
    assert await rule_repo.update(rule) == rule
    assert await rule_repo.deactivate(rule) == rule
    assert await rule_repo.list_fleet_ids_with_active_rules() == [fleet_id]

    log_session = SessionStub(
        execute_results=[
            QueryResultStub(many=[log]),
            QueryResultStub(many=[log]),
            QueryResultStub(one=log),
        ]
    )
    log_repo = FleetAdaptationLogRepository(log_session)
    assert await log_repo.create(log) == log
    assert await log_repo.list_by_fleet(fleet_id) == [log]
    assert await log_repo.list_by_fleet(fleet_id, is_reverted=False) == [log]
    assert await log_repo.get_by_id(log.id) == log
    assert await log_repo.mark_reverted(log) == log
    assert log.is_reverted is True

    transfer_session = SessionStub(
        execute_results=[
            QueryResultStub(one=transfer),
            QueryResultStub(many=[transfer]),
            QueryResultStub(many=[transfer]),
            QueryResultStub(many=[transfer]),
        ]
    )
    transfer_repo = CrossFleetTransferRepository(transfer_session)
    assert await transfer_repo.create(transfer) == transfer
    assert await transfer_repo.get_by_id(transfer.id) == transfer
    assert await transfer_repo.update_status(transfer) == transfer
    assert await transfer_repo.list_for_fleet(fleet_id) == [transfer]
    assert (
        await transfer_repo.list_for_fleet(
            fleet_id,
            role="source",
            status=TransferRequestStatus.proposed,
        )
        == [transfer]
    )
    assert await transfer_repo.list_for_fleet(transfer.target_fleet_id, role="target") == [transfer]

    personality_session = SessionStub(
        execute_results=[
            QueryResultStub(one=personality),
            QueryResultStub(one=personality),
            QueryResultStub(many=[personality]),
        ]
    )
    personality_repo = FleetPersonalityProfileRepository(personality_session)
    assert await personality_repo.get_current(fleet_id) == personality
    assert await personality_repo.create_version(personality) == personality
    assert await personality_repo.list_history(fleet_id) == [personality]


@pytest.mark.asyncio
async def test_fleet_learning_router_helper_paths() -> None:
    workspace_id = uuid4()
    log_id = uuid4()
    transfer_id = uuid4()
    request = _request_with_headers((b"x-workspace-id", str(workspace_id).encode("utf-8")))

    class AdaptationStub:
        def __init__(self) -> None:
            self.calls: list[tuple[UUID, UUID]] = []

        async def revert_adaptation(
            self,
            current_log_id: UUID,
            current_workspace_id: UUID,
        ) -> dict[str, str]:
            self.calls.append((current_log_id, current_workspace_id))
            return {"id": str(current_log_id)}

    class TransferStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, UUID, UUID]] = []

        async def get(
            self,
            current_transfer_id: UUID,
            current_workspace_id: UUID,
        ) -> dict[str, str]:
            self.calls.append(("get", current_transfer_id, current_workspace_id))
            return {"id": str(current_transfer_id)}

        async def revert(
            self,
            current_transfer_id: UUID,
            current_workspace_id: UUID,
        ) -> dict[str, str]:
            self.calls.append(("revert", current_transfer_id, current_workspace_id))
            return {"id": str(current_transfer_id)}

    adaptation_service = AdaptationStub()
    transfer_service = TransferStub()

    resolved_from_header = learning_workspace_id(request, {})
    resolved_from_roles = learning_workspace_id(
        _request_with_headers(),
        {"roles": [{"workspace_id": str(workspace_id)}]},
    )
    reverted_log = await revert_adaptation(
        uuid4(),
        log_id,
        request,
        {"sub": str(uuid4())},
        adaptation_service,
    )
    fetched_transfer = await get_transfer(
        transfer_id,
        request,
        {"sub": str(uuid4())},
        transfer_service,
    )
    reverted_transfer = await revert_transfer(
        transfer_id,
        request,
        {"sub": str(uuid4())},
        transfer_service,
    )

    assert resolved_from_header == workspace_id
    assert resolved_from_roles == workspace_id
    assert reverted_log["id"] == str(log_id)
    assert fetched_transfer["id"] == str(transfer_id)
    assert reverted_transfer["id"] == str(transfer_id)
    assert adaptation_service.calls == [(log_id, workspace_id)]
    assert transfer_service.calls == [
        ("get", transfer_id, workspace_id),
        ("revert", transfer_id, workspace_id),
    ]

    with pytest.raises(ValidationError, match="workspace_id is required"):
        learning_workspace_id(_request_with_headers(), {})
