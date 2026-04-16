from __future__ import annotations

from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.clients.simulation_controller import SimulationControllerClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.policies.dependencies import build_policy_service
from platform.registry.dependencies import build_registry_service
from platform.simulation.comparison.analyzer import ComparisonAnalyzer
from platform.simulation.coordination.runner import SimulationRunner
from platform.simulation.events import SimulationEventPublisher, SimulationEventsConsumer
from platform.simulation.isolation.enforcer import IsolationEnforcer
from platform.simulation.prediction.forecaster import BehavioralForecaster, PredictionWorker
from platform.simulation.repository import SimulationRepository
from platform.simulation.service import SimulationService
from platform.simulation.twins.snapshot import TwinSnapshotService
from platform.workspaces.dependencies import build_workspaces_service
from typing import Annotated, Any, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def build_simulation_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    redis_client: AsyncRedisClient | Any | None,
    simulation_controller: SimulationControllerClient | Any | None,
    clickhouse_client: AsyncClickHouseClient | Any | None,
    registry_service: Any | None,
    policy_service: Any | None,
) -> SimulationService:
    repository = SimulationRepository(session, redis_client)
    publisher = SimulationEventPublisher(producer)
    runner = SimulationRunner(
        repository=repository,
        controller_client=simulation_controller,
        publisher=publisher,
    )
    isolation_enforcer = IsolationEnforcer(
        repository=repository,
        policy_service=policy_service,
        runner=runner,
        publisher=publisher,
        settings=settings,
    )
    forecaster = BehavioralForecaster(
        repository=repository,
        clickhouse_client=clickhouse_client,
        publisher=publisher,
        settings=settings,
    )
    comparison_analyzer = ComparisonAnalyzer(
        repository=repository,
        clickhouse_client=clickhouse_client,
        publisher=publisher,
        settings=settings,
    )
    twin_snapshot = TwinSnapshotService(
        repository=repository,
        registry_service=registry_service,
        clickhouse_client=clickhouse_client,
        publisher=publisher,
        settings=settings,
    )
    events_consumer = SimulationEventsConsumer(
        repository,
        release_isolation=isolation_enforcer.release,
    )
    prediction_worker = PredictionWorker(forecaster, repository)
    return SimulationService(
        repository=repository,
        settings=settings,
        runner=runner,
        twin_snapshot=twin_snapshot,
        isolation_enforcer=isolation_enforcer,
        forecaster=forecaster,
        comparison_analyzer=comparison_analyzer,
        events_consumer=events_consumer,
        prediction_worker=prediction_worker,
    )


async def get_simulation_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> SimulationService:
    settings = cast(PlatformSettings, request.app.state.settings)
    producer = cast(EventProducer | None, request.app.state.clients.get("kafka"))
    redis_client = cast(AsyncRedisClient | None, request.app.state.clients.get("redis"))
    registry_service = _state_service(request, "registry_service") or _build_registry(
        request,
        session,
        settings,
        producer,
    )
    policy_service = _state_service(request, "policy_service") or _build_policy(
        request,
        session,
        settings,
        producer,
        redis_client,
        registry_service,
    )
    return build_simulation_service(
        session=session,
        settings=settings,
        producer=producer,
        redis_client=redis_client,
        simulation_controller=cast(
            SimulationControllerClient | None,
            request.app.state.clients.get("simulation_controller"),
        ),
        clickhouse_client=cast(
            AsyncClickHouseClient | None,
            request.app.state.clients.get("clickhouse"),
        ),
        registry_service=registry_service,
        policy_service=policy_service,
    )


SimulationServiceDep = Annotated[SimulationService, Depends(get_simulation_service)]


def _state_service(request: Request, name: str) -> Any | None:
    return getattr(request.app.state, name, None)


def _build_registry(
    request: Request,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
) -> Any | None:
    try:
        workspaces_service = build_workspaces_service(
            session=session,
            settings=settings,
            producer=producer,
            accounts_service=None,
        )
        return build_registry_service(
            session=session,
            settings=settings,
            object_storage=request.app.state.clients["minio"],
            opensearch=request.app.state.clients["opensearch"],
            qdrant=request.app.state.clients["qdrant"],
            workspaces_service=workspaces_service,
            producer=producer,
        )
    except Exception:
        return None


def _build_policy(
    request: Request,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    redis_client: AsyncRedisClient | Any | None,
    registry_service: Any | None,
) -> Any | None:
    if redis_client is None:
        return None
    try:
        workspaces_service = build_workspaces_service(
            session=session,
            settings=settings,
            producer=producer,
            accounts_service=None,
        )
        return build_policy_service(
            session=session,
            settings=settings,
            producer=producer,
            redis_client=redis_client,
            registry_service=registry_service,
            workspaces_service=workspaces_service,
            reasoning_client=request.app.state.clients.get("reasoning_engine"),
        )
    except Exception:
        return None
