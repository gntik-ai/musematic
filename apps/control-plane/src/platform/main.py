from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from platform.accounts.events import register_accounts_event_types
from platform.accounts.router import router as accounts_router
from platform.analytics.clickhouse_setup import run_setup as run_analytics_clickhouse_setup
from platform.analytics.consumer import AnalyticsPipelineConsumer
from platform.analytics.dependencies import build_analytics_service
from platform.analytics.events import register_analytics_event_types
from platform.analytics.forecast import ForecastEngine
from platform.analytics.recommendation import RecommendationEngine
from platform.analytics.repository import AnalyticsRepository, CostModelRepository
from platform.analytics.router import router as analytics_router
from platform.api.health import router as health_router
from platform.auth.events import register_auth_event_types
from platform.auth.router import router as auth_router
from platform.common import database
from platform.common.auth_middleware import AuthMiddleware
from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.clients.neo4j import AsyncNeo4jClient
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.opensearch import AsyncOpenSearchClient
from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.clients.reasoning_engine import ReasoningEngineClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.clients.runtime_controller import RuntimeControllerClient
from platform.common.clients.sandbox_manager import SandboxManagerClient
from platform.common.clients.simulation_controller import SimulationControllerClient
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from platform.common.correlation import CorrelationMiddleware
from platform.common.dependencies import get_current_user
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.producer import EventProducer
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.common.telemetry import setup_telemetry
from platform.context_engineering.context_engineering_clickhouse_setup import (
    run_setup as run_context_engineering_clickhouse_setup,
)
from platform.context_engineering.dependencies import build_context_engineering_service
from platform.context_engineering.drift_monitor import DriftMonitorTask
from platform.context_engineering.events import register_context_engineering_event_types
from platform.context_engineering.router import router as context_engineering_router
from platform.memory.consolidation_worker import ConsolidationWorker, SessionMemoryCleaner
from platform.memory.dependencies import build_memory_service
from platform.memory.embedding_worker import EmbeddingWorker
from platform.memory.events import register_memory_event_types
from platform.memory.memory_setup import setup_memory_collections
from platform.memory.router import router as memory_router
from platform.registry.dependencies import build_registry_service
from platform.registry.events import register_registry_event_types
from platform.registry.index_worker import RegistryIndexWorker
from platform.registry.registry_opensearch_setup import create_marketplace_agents_index
from platform.registry.registry_qdrant_setup import create_agent_embeddings_collection
from platform.registry.router import router as registry_router
from platform.workspaces.consumer import WorkspacesConsumer
from platform.workspaces.dependencies import build_workspaces_service
from platform.workspaces.events import register_workspaces_event_types
from platform.workspaces.router import router as workspaces_router
from typing import Any, cast

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import Response
from starlette.requests import Request

LOGGER = logging.getLogger(__name__)


def _build_clients(settings: PlatformSettings) -> dict[str, Any]:
    return {
        "redis": AsyncRedisClient.from_settings(settings),
        "kafka": EventProducer.from_settings(settings),
        "kafka_consumer": EventConsumerManager.from_settings(settings),
        "qdrant": AsyncQdrantClient.from_settings(settings),
        "neo4j": AsyncNeo4jClient.from_settings(settings),
        "clickhouse": AsyncClickHouseClient.from_settings(settings),
        "opensearch": AsyncOpenSearchClient.from_settings(settings),
        "minio": AsyncObjectStorageClient.from_settings(settings),
        "runtime_controller": RuntimeControllerClient.from_settings(settings),
        "reasoning_engine": ReasoningEngineClient.from_settings(settings),
        "sandbox_manager": SandboxManagerClient.from_settings(settings),
        "simulation_controller": SimulationControllerClient.from_settings(settings),
    }


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.started_at = time.monotonic()
    app.state.degraded = False
    startup_errors: dict[str, str] = {}
    register_auth_event_types()
    register_accounts_event_types()
    register_workspaces_event_types()
    register_analytics_event_types()
    register_registry_event_types()
    register_context_engineering_event_types()
    register_memory_event_types()

    for name, client in app.state.clients.items():
        if name == "kafka_consumer":
            continue
        try:
            await client.connect()
        except Exception as exc:
            app.state.degraded = True
            startup_errors[name] = str(exc)
            LOGGER.warning("Failed to connect %s during startup: %s", name, exc)

    app.state.startup_errors = startup_errors
    clickhouse_client = app.state.clients.get("clickhouse")
    if isinstance(clickhouse_client, AsyncClickHouseClient):
        try:
            await run_analytics_clickhouse_setup(clickhouse_client, app.state.settings)
        except Exception as exc:
            app.state.degraded = True
            startup_errors["analytics_clickhouse_setup"] = str(exc)
            LOGGER.warning("Failed to run analytics ClickHouse setup: %s", exc)
        try:
            await run_context_engineering_clickhouse_setup(clickhouse_client, app.state.settings)
        except Exception as exc:
            app.state.degraded = True
            startup_errors["context_engineering_clickhouse_setup"] = str(exc)
            LOGGER.warning("Failed to run context engineering ClickHouse setup: %s", exc)
    opensearch_client = app.state.clients.get("opensearch")
    if isinstance(opensearch_client, AsyncOpenSearchClient):
        try:
            await create_marketplace_agents_index(opensearch_client, app.state.settings)
        except Exception as exc:
            app.state.degraded = True
            startup_errors["registry_opensearch_setup"] = str(exc)
            LOGGER.warning("Failed to run registry OpenSearch setup: %s", exc)
    qdrant_client = app.state.clients.get("qdrant")
    neo4j_client = app.state.clients.get("neo4j")
    if isinstance(qdrant_client, AsyncQdrantClient):
        try:
            await create_agent_embeddings_collection(qdrant_client, app.state.settings)
        except Exception as exc:
            app.state.degraded = True
            startup_errors["registry_qdrant_setup"] = str(exc)
            LOGGER.warning("Failed to run registry Qdrant setup: %s", exc)
    if isinstance(qdrant_client, AsyncQdrantClient) and isinstance(neo4j_client, AsyncNeo4jClient):
        try:
            await setup_memory_collections(qdrant_client, neo4j_client, app.state.settings)
        except Exception as exc:
            app.state.degraded = True
            startup_errors["memory_setup"] = str(exc)
            LOGGER.warning("Failed to run memory setup: %s", exc)

    consumer_manager = app.state.clients.get("kafka_consumer")
    if consumer_manager is not None:
        start = getattr(consumer_manager, "start", None)
        if callable(start):
            try:
                result = start()
                if hasattr(result, "__await__"):
                    await result
            except Exception as exc:
                app.state.degraded = True
                startup_errors["kafka_consumer"] = str(exc)
                LOGGER.warning("Failed to start kafka consumer during startup: %s", exc)

    analytics_consumer = getattr(app.state, "analytics_consumer", None)
    if analytics_consumer is not None:
        try:
            await analytics_consumer.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["analytics_consumer"] = str(exc)
            LOGGER.warning("Failed to start analytics consumer during startup: %s", exc)

    analytics_scheduler = getattr(app.state, "analytics_budget_scheduler", None)
    if analytics_scheduler is not None:
        try:
            analytics_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["analytics_budget_scheduler"] = str(exc)
            LOGGER.warning("Failed to start analytics budget scheduler: %s", exc)
    registry_index_worker = getattr(app.state, "registry_index_worker", None)
    context_engineering_scheduler = getattr(app.state, "context_engineering_drift_scheduler", None)
    if registry_index_worker is not None:
        try:
            await registry_index_worker.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["registry_index_worker"] = str(exc)
            LOGGER.warning("Failed to start registry index worker: %s", exc)
    if context_engineering_scheduler is not None:
        try:
            context_engineering_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["context_engineering_drift_scheduler"] = str(exc)
            LOGGER.warning("Failed to start context engineering scheduler: %s", exc)
    memory_scheduler = getattr(app.state, "memory_scheduler", None)
    if memory_scheduler is not None:
        try:
            memory_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["memory_scheduler"] = str(exc)
            LOGGER.warning("Failed to start memory scheduler: %s", exc)
    try:
        yield
    finally:
        if memory_scheduler is not None:
            try:
                memory_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop memory scheduler cleanly: %s", exc)
        if context_engineering_scheduler is not None:
            try:
                context_engineering_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop context engineering scheduler cleanly: %s", exc)
        if registry_index_worker is not None:
            try:
                await registry_index_worker.stop()
            except Exception as exc:
                LOGGER.warning("Failed to stop registry index worker cleanly: %s", exc)
        if analytics_scheduler is not None:
            try:
                analytics_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop analytics budget scheduler cleanly: %s", exc)
        if analytics_consumer is not None:
            try:
                await analytics_consumer.stop()
            except Exception as exc:
                LOGGER.warning("Failed to stop analytics consumer cleanly: %s", exc)
        stop = getattr(consumer_manager, "stop", None)
        if callable(stop):
            try:
                result = stop()
                if hasattr(result, "__await__"):
                    await result
            except Exception as exc:
                LOGGER.warning("Failed to stop kafka consumer cleanly: %s", exc)
        for client in reversed(list(app.state.clients.values())):
            close = getattr(client, "close", None)
            if close is None:
                continue
            try:
                result = close()
                if hasattr(result, "__await__"):
                    await result
            except Exception as exc:
                LOGGER.warning("Failed to close client cleanly: %s", exc)


def create_app(profile: str = "api", settings: PlatformSettings | None = None) -> FastAPI:
    resolved = settings or default_settings
    if resolved.profile != profile:
        resolved = resolved.model_copy(update={"profile": profile})

    database.configure_database(resolved)

    app = FastAPI(lifespan=_lifespan)
    app.state.settings = resolved
    app.state.clients = _build_clients(resolved)
    app.state.analytics_repository = AnalyticsRepository(
        cast(AsyncClickHouseClient, app.state.clients["clickhouse"])
    )
    app.state.analytics_consumer = None
    app.state.analytics_budget_scheduler = None
    app.state.registry_index_worker = None
    app.state.context_engineering_drift_scheduler = None
    app.state.memory_scheduler = None
    if resolved.profile == "worker":
        app.state.analytics_consumer = AnalyticsPipelineConsumer(
            settings=resolved,
            clickhouse_client=cast(AsyncClickHouseClient, app.state.clients["clickhouse"]),
            producer=cast(EventProducer | None, app.state.clients.get("kafka")),
        )
        app.state.analytics_budget_scheduler = _build_analytics_budget_scheduler(app)
        app.state.memory_scheduler = _build_memory_scheduler(app)
        opensearch_client = app.state.clients.get("opensearch")
        if isinstance(opensearch_client, AsyncOpenSearchClient):
            app.state.registry_index_worker = RegistryIndexWorker(
                settings=resolved,
                opensearch=opensearch_client,
            )
    if resolved.profile in {"scheduler", "context-engineering"}:
        app.state.context_engineering_drift_scheduler = _build_context_engineering_scheduler(app)
    exception_handler = cast(
        Callable[[Request, Exception], Response | Awaitable[Response]],
        platform_exception_handler,
    )
    app.add_exception_handler(PlatformError, exception_handler)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(CorrelationMiddleware)
    app.include_router(health_router)
    consumer_manager = app.state.clients.get("kafka_consumer")
    if isinstance(consumer_manager, EventConsumerManager):
        WorkspacesConsumer(
            settings=resolved,
            redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
            producer=cast(EventProducer | None, app.state.clients.get("kafka")),
        ).register(consumer_manager)

    api_router = APIRouter(prefix="/api/v1")

    @api_router.get("/protected")
    async def protected_endpoint(
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        return {"status": "ok", "user": current_user}

    if resolved.profile == "api":
        app.include_router(api_router)
        app.include_router(auth_router)
        app.include_router(accounts_router)
        app.include_router(workspaces_router)
        app.include_router(analytics_router)
        app.include_router(registry_router)
        app.include_router(context_engineering_router)
        app.include_router(memory_router)

    setup_telemetry(
        service_name=f"{resolved.otel.service_name}-{resolved.profile}",
        exporter_endpoint=resolved.otel.exporter_endpoint,
        app=app,
        engine=database.engine,
    )
    return app


def _build_analytics_budget_scheduler(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run_threshold_check() -> None:
        async with database.AsyncSessionLocal() as session:
            service = build_analytics_service(
                repository=cast(AnalyticsRepository, app.state.analytics_repository),
                cost_model_repository=CostModelRepository(session),
                workspaces_service=None,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            service.recommendation_engine = RecommendationEngine()
            service.forecast_engine = ForecastEngine()
            await service.check_budget_thresholds()

    scheduler.add_job(_run_threshold_check, "interval", days=1, id="analytics-budget-threshold")
    return scheduler


def _build_context_engineering_scheduler(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
        trigger_module = __import__(
            "apscheduler.triggers.cron",
            fromlist=["CronTrigger"],
        )
    except Exception:
        return None

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")
    trigger = trigger_module.CronTrigger(
        minute=f"*/{app.state.settings.context_engineering.drift_schedule_minutes}",
    )

    async def _run_drift_analysis() -> None:
        async with database.AsyncSessionLocal() as session:
            workspaces_service = build_workspaces_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                accounts_service=None,
            )
            registry_service = build_registry_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
                opensearch=cast(AsyncOpenSearchClient, app.state.clients["opensearch"]),
                qdrant=cast(AsyncQdrantClient, app.state.clients["qdrant"]),
                workspaces_service=workspaces_service,
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            memory_service = build_memory_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                qdrant=cast(AsyncQdrantClient, app.state.clients["qdrant"]),
                neo4j=cast(AsyncNeo4jClient, app.state.clients["neo4j"]),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                workspaces_service=workspaces_service,
                registry_service=registry_service,
            )
            service = build_context_engineering_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                clickhouse_client=cast(AsyncClickHouseClient, app.state.clients["clickhouse"]),
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                workspaces_service=workspaces_service,
                registry_service=registry_service,
                execution_service=None,
                interactions_service=None,
                memory_service=memory_service,
                connectors_service=None,
                policies_service=None,
            )
            await DriftMonitorTask(service).run()

    scheduler.add_job(
        _run_drift_analysis,
        trigger,
        id="context-engineering-drift-analysis",
    )
    return scheduler


def _build_memory_scheduler(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run_embedding_jobs() -> None:
        async with database.AsyncSessionLocal() as session:
            workspaces_service = build_workspaces_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                accounts_service=None,
            )
            registry_service = build_registry_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
                opensearch=cast(AsyncOpenSearchClient, app.state.clients["opensearch"]),
                qdrant=cast(AsyncQdrantClient, app.state.clients["qdrant"]),
                workspaces_service=workspaces_service,
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            service = build_memory_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                qdrant=cast(AsyncQdrantClient, app.state.clients["qdrant"]),
                neo4j=cast(AsyncNeo4jClient, app.state.clients["neo4j"]),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                workspaces_service=workspaces_service,
                registry_service=registry_service,
            )
            await EmbeddingWorker(
                repository=service.repository,
                qdrant=service.qdrant,
                settings=cast(PlatformSettings, app.state.settings),
            ).run()

    async def _run_consolidation() -> None:
        async with database.AsyncSessionLocal() as session:
            workspaces_service = build_workspaces_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                accounts_service=None,
            )
            registry_service = build_registry_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
                opensearch=cast(AsyncOpenSearchClient, app.state.clients["opensearch"]),
                qdrant=cast(AsyncQdrantClient, app.state.clients["qdrant"]),
                workspaces_service=workspaces_service,
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            service = build_memory_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                qdrant=cast(AsyncQdrantClient, app.state.clients["qdrant"]),
                neo4j=cast(AsyncNeo4jClient, app.state.clients["neo4j"]),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                workspaces_service=workspaces_service,
                registry_service=registry_service,
            )
            await ConsolidationWorker(
                repository=service.repository,
                write_gate=service.write_gate,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            ).run()

    async def _run_session_cleanup() -> None:
        async with database.AsyncSessionLocal() as session:
            workspaces_service = build_workspaces_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                accounts_service=None,
            )
            registry_service = build_registry_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
                opensearch=cast(AsyncOpenSearchClient, app.state.clients["opensearch"]),
                qdrant=cast(AsyncQdrantClient, app.state.clients["qdrant"]),
                workspaces_service=workspaces_service,
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            service = build_memory_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                qdrant=cast(AsyncQdrantClient, app.state.clients["qdrant"]),
                neo4j=cast(AsyncNeo4jClient, app.state.clients["neo4j"]),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                workspaces_service=workspaces_service,
                registry_service=registry_service,
            )
            await SessionMemoryCleaner(
                repository=service.repository,
                qdrant=service.qdrant,
            ).run()

    scheduler.add_job(
        _run_embedding_jobs,
        "interval",
        seconds=30,
        id="memory-embedding-worker",
    )
    if app.state.settings.memory.consolidation_enabled:
        scheduler.add_job(
            _run_consolidation,
            "interval",
            minutes=app.state.settings.memory.consolidation_interval_minutes,
            id="memory-consolidation-worker",
        )
    scheduler.add_job(
        _run_session_cleanup,
        "interval",
        minutes=app.state.settings.memory.session_cleaner_interval_minutes,
        id="memory-session-cleaner",
    )
    return scheduler
