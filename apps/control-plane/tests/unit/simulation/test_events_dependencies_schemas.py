from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.simulation.dependencies import (
    _build_policy,
    _build_registry,
    _state_service,
    build_simulation_service,
    get_simulation_service,
)
from platform.simulation.events import (
    SimulationEventPublisher,
    SimulationEventsConsumer,
    register_simulation_event_types,
)
from platform.simulation.models import SimulationRun
from platform.simulation.schemas import (
    BehavioralPredictionCreateRequest,
    DigitalTwinResponse,
    SimulationComparisonCreateRequest,
    SimulationRunCreateRequest,
)
from types import SimpleNamespace
from uuid import uuid4

import pytest


class FakeProducer:
    def __init__(self) -> None:
        self.published: list[dict[str, object]] = []

    async def publish(self, **kwargs) -> None:
        self.published.append(kwargs)


class FakeRepository:
    def __init__(self, run: SimulationRun) -> None:
        self.run = run
        self.cache: dict[object, dict[str, object]] = {}

    async def update_run_status(self, run_id, workspace_id, status, *, results=None):
        if run_id == self.run.id and workspace_id == self.run.workspace_id:
            self.run.status = status
            self.run.results = results
            return self.run
        return None

    async def set_status_cache(self, run_id, status_dict):
        self.cache[run_id] = status_dict


def _run() -> SimulationRun:
    run = SimulationRun(
        workspace_id=uuid4(),
        name="scenario",
        digital_twin_ids=[],
        scenario_config={},
        status="provisioning",
        initiated_by=uuid4(),
    )
    run.id = uuid4()
    run.created_at = datetime.now(UTC)
    return run


@pytest.mark.asyncio
async def test_event_publisher_registers_and_publishes_all_event_types() -> None:
    register_simulation_event_types()
    producer = FakeProducer()
    publisher = SimulationEventPublisher(producer)
    workspace_id = uuid4()
    run_id = uuid4()

    await publisher.simulation_run_created(run_id, workspace_id, uuid4(), "ctrl")
    await publisher.simulation_run_cancelled(run_id, workspace_id, uuid4())
    await publisher.twin_created(uuid4(), workspace_id, "namespace.agent")
    await publisher.twin_modified(uuid4(), workspace_id, uuid4(), 2)
    await publisher.prediction_completed(uuid4(), workspace_id, "completed")
    await publisher.comparison_completed(uuid4(), workspace_id, True)
    await publisher.isolation_breach_detected(run_id, workspace_id, {"severity": "critical"})

    assert [item["topic"] for item in producer.published] == ["simulation.events"] * 7
    assert producer.published[0]["event_type"] == "simulation_run_created"


@pytest.mark.asyncio
async def test_events_consumer_updates_terminal_status_and_releases_isolation() -> None:
    run = _run()
    released: list[object] = []
    repository = FakeRepository(run)
    consumer = SimulationEventsConsumer(
        repository,
        release_isolation=lambda item: released.append(item),
    )

    await consumer.handle_event(
        SimpleNamespace(
            event_type="simulation_run_completed",
            payload={
                "run_id": str(run.id),
                "workspace_id": str(run.workspace_id),
                "results": {"ok": True},
            },
        )
    )
    await consumer.handle_event({"event_type": "unknown"})
    await consumer.handle_event(SimpleNamespace(event_type="simulation_run_failed", payload={}))

    assert run.status == "completed"
    assert repository.cache[run.id]["progress_pct"] == 100
    assert released == [run]


@pytest.mark.asyncio
async def test_dependency_builders_create_services_and_handle_missing_optional_context() -> None:
    settings = PlatformSettings()
    service = build_simulation_service(
        session=SimpleNamespace(),
        settings=settings,
        producer=None,
        redis_client=None,
        simulation_controller=None,
        clickhouse_client=None,
        registry_service=None,
        policy_service=None,
    )
    assert service.settings is settings

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={},
                registry_service="registry",
                policy_service="policy",
            )
        )
    )
    assert _state_service(request, "registry_service") == "registry"
    assert _build_registry(request, SimpleNamespace(), settings, None) is None
    assert _build_policy(request, SimpleNamespace(), settings, None, None, None) is None

    resolved = await get_simulation_service(request, session=SimpleNamespace())
    assert resolved.repository.redis is None


def test_schema_validators_and_warning_flags() -> None:
    from pydantic import ValidationError as PydanticValidationError

    with pytest.raises(PydanticValidationError):
        SimulationRunCreateRequest(
            workspace_id=uuid4(),
            name=" ",
            digital_twin_ids=[uuid4()],
            scenario_config={},
        )
    with pytest.raises(PydanticValidationError):
        BehavioralPredictionCreateRequest(
            workspace_id=uuid4(),
            condition_modifiers={"load_factor": 0},
        )
    with pytest.raises(PydanticValidationError):
        SimulationComparisonCreateRequest(
            workspace_id=uuid4(),
            comparison_type="simulation_vs_simulation",
        )
    twin = DigitalTwinResponse(
        twin_id=uuid4(),
        workspace_id=uuid4(),
        source_agent_fqn="namespace.agent",
        source_revision_id=None,
        version=1,
        parent_twin_id=None,
        config_snapshot={},
        behavioral_history_summary={"warning_flags": ["agent_archived"]},
        modifications=[],
        is_active=True,
        created_at=datetime.now(UTC),
    )
    assert twin.warning_flags == ["agent_archived"]
