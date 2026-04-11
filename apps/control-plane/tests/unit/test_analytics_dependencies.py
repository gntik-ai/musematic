from __future__ import annotations

from platform.analytics import __all__ as analytics_exports
from platform.analytics.dependencies import (
    _get_clickhouse,
    _get_producer,
    _get_settings,
    build_analytics_service,
    get_analytics_repository,
    get_analytics_service,
)
from platform.analytics.forecast import ForecastEngine
from platform.analytics.recommendation import RecommendationEngine
from platform.analytics.repository import AnalyticsRepository, CostModelRepository
from platform.common.config import PlatformSettings
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.analytics_support import ClickHouseClientStub, WorkspacesServiceStub
from tests.auth_support import RecordingProducer


def test_build_analytics_service_wires_dependencies() -> None:
    repository = AnalyticsRepository(ClickHouseClientStub())  # type: ignore[arg-type]
    cost_model_repository = CostModelRepository(object())  # type: ignore[arg-type]
    workspaces_service = WorkspacesServiceStub([uuid4()])
    producer = RecordingProducer()
    service = build_analytics_service(
        repository=repository,
        cost_model_repository=cost_model_repository,
        workspaces_service=workspaces_service,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        producer=producer,
    )

    assert service.repo is repository
    assert service.cost_model_repo is cost_model_repository
    assert service.workspaces_service is workspaces_service
    assert service.kafka_producer is producer
    assert isinstance(service.recommendation_engine, RecommendationEngine)
    assert isinstance(service.forecast_engine, ForecastEngine)
    assert analytics_exports == ["get_analytics_service"]


def test_dependency_helpers_read_request_state_and_cache_repository() -> None:
    settings = PlatformSettings()
    clickhouse = ClickHouseClientStub()
    producer = RecordingProducer()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={"clickhouse": clickhouse, "kafka": producer},
            )
        )
    )

    repository = get_analytics_repository(request)

    assert _get_settings(request) is settings
    assert _get_clickhouse(request) is clickhouse
    assert _get_producer(request) is producer
    assert get_analytics_repository(request) is repository


@pytest.mark.asyncio
async def test_get_analytics_service_builds_from_dependencies(monkeypatch) -> None:
    settings = PlatformSettings()
    clickhouse = ClickHouseClientStub()
    producer = RecordingProducer()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={"clickhouse": clickhouse, "kafka": producer},
            )
        )
    )
    session = object()
    repository = AnalyticsRepository(clickhouse)  # type: ignore[arg-type]
    workspaces_service = WorkspacesServiceStub([uuid4()])
    captured: dict[str, object] = {}

    def _fake_builder(**kwargs: object) -> str:
        captured.update(kwargs)
        return "analytics-service"

    monkeypatch.setattr("platform.analytics.dependencies.build_analytics_service", _fake_builder)

    service = await get_analytics_service(
        request,  # type: ignore[arg-type]
        session=session,  # type: ignore[arg-type]
        repository=repository,
        workspaces_service=workspaces_service,  # type: ignore[arg-type]
    )

    assert service == "analytics-service"
    assert captured["repository"] is repository
    assert isinstance(captured["cost_model_repository"], CostModelRepository)
    assert captured["cost_model_repository"].session is session
    assert captured["workspaces_service"] is workspaces_service
    assert captured["settings"] is settings
    assert captured["producer"] is producer
