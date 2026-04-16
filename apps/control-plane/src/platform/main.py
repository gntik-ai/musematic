from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from fnmatch import fnmatch
from platform.accounts.events import register_accounts_event_types
from platform.accounts.router import router as accounts_router
from platform.agentops.dependencies import build_agentops_service
from platform.agentops.events import register_agentops_event_types
from platform.agentops.governance.triggers import AgentOpsGovernanceTriggers
from platform.agentops.router import router as agentops_router
from platform.analytics.clickhouse_setup import run_setup as run_analytics_clickhouse_setup
from platform.analytics.consumer import AnalyticsPipelineConsumer
from platform.analytics.dependencies import build_analytics_service
from platform.analytics.events import register_analytics_event_types
from platform.analytics.forecast import ForecastEngine
from platform.analytics.recommendation import RecommendationEngine
from platform.analytics.repository import AnalyticsRepository, CostModelRepository
from platform.analytics.router import router as analytics_router
from platform.api.evaluations import router as evaluations_router
from platform.api.health import router as health_router
from platform.api.testing import router as testing_router
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
from platform.composition.events import register_composition_event_types
from platform.composition.router import router as composition_router
from platform.connectors.dependencies import build_connectors_service
from platform.connectors.events import register_connectors_event_types
from platform.connectors.implementations.email import EmailPollingJob
from platform.connectors.retry import RetryScanner
from platform.connectors.router import router as connectors_router
from platform.context_engineering.context_engineering_clickhouse_setup import (
    run_setup as run_context_engineering_clickhouse_setup,
)
from platform.context_engineering.dependencies import build_context_engineering_service
from platform.context_engineering.drift_monitor import DriftMonitorTask
from platform.context_engineering.events import register_context_engineering_event_types
from platform.context_engineering.router import router as context_engineering_router
from platform.discovery.events import register_discovery_event_types
from platform.discovery.router import router as discovery_router
from platform.evaluation.dependencies import build_eval_runner_service, build_robustness_service
from platform.evaluation.events import register_evaluation_event_types
from platform.evaluation.repository import EvaluationRepository
from platform.evaluation.scorers.semantic import SemanticSimilarityScorer
from platform.execution.dependencies import build_execution_service, build_scheduler_service
from platform.execution.events import (
    event_bus_consumer_handler,
    register_execution_consumers,
    register_execution_event_types,
)
from platform.execution.models import ExecutionEventType, ExecutionStatus
from platform.execution.router import router as execution_router
from platform.execution.schemas import ExecutionCreate
from platform.fleet_learning.dependencies import build_adaptation_service, build_performance_service
from platform.fleet_learning.router import router as fleet_learning_router
from platform.fleets.dependencies import build_fleet_service, build_health_service
from platform.fleets.events import register_fleet_event_types
from platform.fleets.repository import FleetMemberRepository
from platform.fleets.router import router as fleets_router
from platform.fleets.service import route_execution_event_to_observers
from platform.interactions.dependencies import build_interactions_service
from platform.interactions.events import register_interactions_event_types
from platform.interactions.router import router as interactions_router
from platform.marketplace.dependencies import (
    build_quality_service as build_marketplace_quality_service,
)
from platform.marketplace.dependencies import (
    build_recommendation_service as build_marketplace_recommendation_service,
)
from platform.marketplace.dependencies import (
    build_search_service as build_marketplace_search_service,
)
from platform.marketplace.events import register_marketplace_event_types
from platform.marketplace.jobs import run_cf_recommendations, run_trending_computation
from platform.marketplace.repository import MarketplaceRepository
from platform.marketplace.router import router as marketplace_router
from platform.memory.consolidation_worker import ConsolidationWorker, SessionMemoryCleaner
from platform.memory.dependencies import build_memory_service
from platform.memory.embedding_worker import EmbeddingWorker
from platform.memory.events import register_memory_event_types
from platform.memory.memory_setup import setup_memory_collections
from platform.memory.router import router as memory_router
from platform.policies.dependencies import build_policy_service
from platform.policies.events import PolicyEventConsumer, register_policies_event_types
from platform.policies.router import router as policies_router
from platform.registry.dependencies import build_registry_service
from platform.registry.events import register_registry_event_types
from platform.registry.index_worker import RegistryIndexWorker
from platform.registry.registry_opensearch_setup import create_marketplace_agents_index
from platform.registry.registry_qdrant_setup import create_agent_embeddings_collection
from platform.registry.router import router as registry_router
from platform.simulation.dependencies import build_simulation_service
from platform.simulation.events import register_simulation_event_types
from platform.simulation.router import router as simulation_router
from platform.testing.dependencies import build_drift_service
from platform.testing.events import register_testing_event_types
from platform.trust.dependencies import (
    build_ate_service,
    build_certification_service,
    build_circuit_breaker_service,
    build_prescreener_service,
    build_recertification_service,
    build_trust_tier_service,
)
from platform.trust.events import register_trust_event_types
from platform.trust.router import router as trust_router
from platform.workflows.dependencies import build_workflow_service
from platform.workflows.events import register_workflows_event_types
from platform.workflows.models import TriggerType
from platform.workflows.router import router as workflows_router
from platform.workspaces.consumer import WorkspacesConsumer
from platform.workspaces.dependencies import build_workspaces_service
from platform.workspaces.events import register_workspaces_event_types
from platform.workspaces.router import router as workspaces_router
from typing import Any, cast
from uuid import UUID

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
    register_interactions_event_types()
    register_connectors_event_types()
    register_evaluation_event_types()
    register_policies_event_types()
    register_testing_event_types()
    register_workflows_event_types()
    register_execution_event_types()
    register_marketplace_event_types()
    register_trust_event_types()
    register_fleet_event_types()
    register_agentops_event_types()
    register_composition_event_types()
    register_discovery_event_types()
    register_simulation_event_types()

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
        try:
            async with database.AsyncSessionLocal() as session:
                drift_service = build_drift_service(
                    session=session,
                    settings=cast(PlatformSettings, app.state.settings),
                    producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                    clickhouse_client=clickhouse_client,
                )
                await drift_service.ensure_schema()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["testing_clickhouse_setup"] = str(exc)
            LOGGER.warning("Failed to run testing ClickHouse setup: %s", exc)
    object_storage_client = app.state.clients.get("minio")
    if isinstance(object_storage_client, AsyncObjectStorageClient):
        for bucket_name in ("evaluation-ate-evidence", "evaluation-generated-suites"):
            try:
                await object_storage_client.create_bucket_if_not_exists(bucket_name)
            except Exception as exc:
                app.state.degraded = True
                startup_errors[f"bucket:{bucket_name}"] = str(exc)
                LOGGER.warning("Failed to provision bucket %s: %s", bucket_name, exc)
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
        try:
            await SemanticSimilarityScorer(
                settings=cast(PlatformSettings, app.state.settings),
                qdrant=qdrant_client,
            ).ensure_collection()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["evaluation_qdrant_setup"] = str(exc)
            LOGGER.warning("Failed to run evaluation Qdrant setup: %s", exc)
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
    connectors_worker_scheduler = getattr(app.state, "connectors_worker_scheduler", None)
    workflow_execution_scheduler = getattr(app.state, "workflow_execution_scheduler", None)
    marketplace_scheduler = getattr(app.state, "marketplace_scheduler", None)
    fleet_learning_scheduler = getattr(app.state, "fleet_learning_scheduler", None)
    agentops_lifecycle_scheduler = getattr(app.state, "agentops_lifecycle_scheduler", None)
    agentops_drift_scheduler = getattr(app.state, "agentops_drift_scheduler", None)
    discovery_proximity_scheduler = getattr(app.state, "discovery_proximity_scheduler", None)
    simulation_prediction_scheduler = getattr(
        app.state,
        "simulation_prediction_scheduler",
        None,
    )
    robustness_orchestrator_scheduler = getattr(
        app.state,
        "robustness_orchestrator_scheduler",
        None,
    )
    if memory_scheduler is not None:
        try:
            memory_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["memory_scheduler"] = str(exc)
            LOGGER.warning("Failed to start memory scheduler: %s", exc)
    if connectors_worker_scheduler is not None:
        try:
            connectors_worker_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["connectors_worker_scheduler"] = str(exc)
            LOGGER.warning("Failed to start connectors worker scheduler: %s", exc)
    if workflow_execution_scheduler is not None:
        try:
            workflow_execution_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["workflow_execution_scheduler"] = str(exc)
            LOGGER.warning("Failed to start workflow execution scheduler: %s", exc)
    if marketplace_scheduler is not None:
        try:
            marketplace_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["marketplace_scheduler"] = str(exc)
            LOGGER.warning("Failed to start marketplace scheduler: %s", exc)
    if fleet_learning_scheduler is not None:
        try:
            fleet_learning_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["fleet_learning_scheduler"] = str(exc)
            LOGGER.warning("Failed to start fleet learning scheduler: %s", exc)
    if agentops_lifecycle_scheduler is not None:
        try:
            agentops_lifecycle_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["agentops_lifecycle_scheduler"] = str(exc)
            LOGGER.warning("Failed to start agentops lifecycle scheduler: %s", exc)
    if agentops_drift_scheduler is not None:
        try:
            agentops_drift_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["agentops_drift_scheduler"] = str(exc)
            LOGGER.warning("Failed to start agentops drift scheduler: %s", exc)
    if robustness_orchestrator_scheduler is not None:
        try:
            robustness_orchestrator_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["robustness_orchestrator_scheduler"] = str(exc)
            LOGGER.warning("Failed to start robustness orchestrator scheduler: %s", exc)
    if discovery_proximity_scheduler is not None:
        try:
            discovery_proximity_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["discovery_proximity_scheduler"] = str(exc)
            LOGGER.warning("Failed to start discovery proximity scheduler: %s", exc)
    if simulation_prediction_scheduler is not None:
        try:
            simulation_prediction_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["simulation_prediction_scheduler"] = str(exc)
            LOGGER.warning("Failed to start simulation prediction scheduler: %s", exc)
    try:
        await _load_trust_runtime_assets(app)
    except Exception as exc:
        app.state.degraded = True
        startup_errors["trust_runtime_assets"] = str(exc)
        LOGGER.warning("Failed to initialize trust runtime assets: %s", exc)
    trust_certifier_scheduler = getattr(app.state, "trust_certifier_scheduler", None)
    if trust_certifier_scheduler is not None:
        try:
            trust_certifier_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["trust_certifier_scheduler"] = str(exc)
            LOGGER.warning("Failed to start trust certifier scheduler: %s", exc)
    try:
        yield
    finally:
        if simulation_prediction_scheduler is not None:
            try:
                simulation_prediction_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop simulation prediction scheduler cleanly: %s", exc)
        if robustness_orchestrator_scheduler is not None:
            try:
                robustness_orchestrator_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning(
                    "Failed to stop robustness orchestrator scheduler cleanly: %s",
                    exc,
                )
        if discovery_proximity_scheduler is not None:
            try:
                discovery_proximity_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop discovery proximity scheduler cleanly: %s", exc)
        if agentops_drift_scheduler is not None:
            try:
                agentops_drift_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop agentops drift scheduler cleanly: %s", exc)
        if agentops_lifecycle_scheduler is not None:
            try:
                agentops_lifecycle_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop agentops lifecycle scheduler cleanly: %s", exc)
        if trust_certifier_scheduler is not None:
            try:
                trust_certifier_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop trust certifier scheduler cleanly: %s", exc)
        if marketplace_scheduler is not None:
            try:
                marketplace_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop marketplace scheduler cleanly: %s", exc)
        if fleet_learning_scheduler is not None:
            try:
                fleet_learning_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop fleet learning scheduler cleanly: %s", exc)
        if workflow_execution_scheduler is not None:
            try:
                workflow_execution_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning(
                    "Failed to stop workflow execution scheduler cleanly: %s",
                    exc,
                )
        if connectors_worker_scheduler is not None:
            try:
                connectors_worker_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop connectors worker scheduler cleanly: %s", exc)
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
    app.state.connectors_worker_scheduler = None
    app.state.workflow_execution_scheduler = None
    app.state.workflow_scheduler = None
    app.state.marketplace_scheduler = None
    app.state.fleet_learning_scheduler = None
    app.state.agentops_lifecycle_scheduler = None
    app.state.agentops_drift_scheduler = None
    app.state.discovery_proximity_scheduler = None
    app.state.simulation_prediction_scheduler = None
    app.state.robustness_orchestrator_scheduler = None
    app.state.trust_certifier_scheduler = None
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
        if resolved.connectors.worker_enabled:
            app.state.connectors_worker_scheduler = _build_connectors_worker_scheduler(app)
        app.state.workflow_execution_scheduler = _build_workflow_execution_scheduler(app)
        app.state.workflow_scheduler = app.state.workflow_execution_scheduler
        app.state.marketplace_scheduler = _build_marketplace_scheduler(app)
        app.state.fleet_learning_scheduler = _build_fleet_learning_scheduler(app)
    if resolved.profile == "agentops":
        app.state.agentops_lifecycle_scheduler = _build_agentops_lifecycle_scheduler(app)
    if resolved.profile == "agentops-testing":
        app.state.agentops_drift_scheduler = _build_agentops_drift_scheduler(app)
        app.state.robustness_orchestrator_scheduler = _build_robustness_orchestrator_scheduler(app)
    if resolved.profile == "trust-certifier":
        app.state.trust_certifier_scheduler = _build_trust_certifier_scheduler(app)
    if resolved.profile == "discovery":
        app.state.discovery_proximity_scheduler = _build_discovery_proximity_scheduler(app)
    if resolved.profile == "simulation":
        app.state.simulation_prediction_scheduler = _build_simulation_prediction_scheduler(app)
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
        PolicyEventConsumer(
            invalidate_bundle_by_revision=_build_policy_bundle_invalidator(app),
        ).register(consumer_manager)
        if resolved.profile == "agentops":
            consumer_manager.subscribe(
                "evaluation.events",
                f"{resolved.kafka.consumer_group}-agentops-regression",
                _build_agentops_evaluation_handler(app),
            )
            consumer_manager.subscribe(
                "trust.events",
                f"{resolved.kafka.consumer_group}-agentops-governance",
                _build_agentops_trust_handler(app),
            )
            consumer_manager.subscribe(
                "agentops.events",
                f"{resolved.kafka.consumer_group}-agentops-retirement",
                _build_agentops_retirement_handler(app),
            )
        if resolved.profile == "discovery":
            consumer_manager.subscribe(
                "workflow.runtime",
                f"{resolved.kafka.consumer_group}-discovery-runtime",
                _build_discovery_workflow_runtime_handler(app),
            )
        if resolved.profile == "simulation":
            consumer_manager.subscribe(
                "simulation.events",
                f"{resolved.kafka.consumer_group}-simulation-status",
                _build_simulation_event_handler(app),
            )
        if resolved.profile == "worker" and resolved.connectors.worker_enabled:
            consumer_manager.subscribe(
                resolved.connectors.delivery_topic,
                resolved.connectors.delivery_consumer_group,
                _build_connector_delivery_handler(app),
            )
        if resolved.profile == "worker":
            register_execution_consumers(
                consumer_manager,
                group_id=f"{resolved.kafka.consumer_group}-workflow-execution",
                workflow_runtime_handler=_build_workflow_runtime_handler(app),
                reasoning_handler=_build_reprioritization_handler(
                    app,
                    "budget_threshold_breached",
                ),
                fleet_handler=_build_reprioritization_handler(
                    app,
                    "resource_constraint_changed",
                ),
                workspace_goal_handler=_build_workspace_goal_handler(app),
                attention_handler=_build_reprioritization_handler(
                    app,
                    "external_event",
                ),
                event_bus_handler=_build_event_bus_handler(app),
            )
            consumer_manager.subscribe(
                "workflow.runtime",
                "marketplace-quality-signals",
                _build_marketplace_quality_handler(app, "handle_execution_event"),
            )
            consumer_manager.subscribe(
                "evaluation.events",
                "marketplace-quality-signals",
                _build_marketplace_quality_handler(app, "handle_evaluation_event"),
            )
            consumer_manager.subscribe(
                "trust.events",
                "marketplace-quality-signals",
                _build_marketplace_quality_handler(app, "handle_trust_event"),
            )
            consumer_manager.subscribe(
                "registry.events",
                f"{resolved.kafka.consumer_group}-trust-recertification",
                _build_trust_registry_handler(app),
            )
            consumer_manager.subscribe(
                "policy.events",
                f"{resolved.kafka.consumer_group}-trust-recertification",
                _build_trust_policy_handler(app),
            )
            consumer_manager.subscribe(
                "workflow.runtime",
                f"{resolved.kafka.consumer_group}-trust-runtime",
                _build_trust_runtime_handler(app),
            )
            consumer_manager.subscribe(
                "simulation.events",
                f"{resolved.kafka.consumer_group}-trust-ate",
                _build_trust_simulation_handler(app),
            )
            consumer_manager.subscribe(
                "trust.events",
                f"{resolved.kafka.consumer_group}-trust-tier",
                _build_trust_event_handler(app),
            )
            consumer_manager.subscribe(
                "trust.events",
                f"{resolved.kafka.consumer_group}-trust-prescreener",
                _build_trust_prescreener_handler(app),
            )
            consumer_manager.subscribe(
                "runtime.lifecycle",
                f"{resolved.kafka.consumer_group}-fleet-health",
                _build_fleet_runtime_lifecycle_handler(app),
            )
            consumer_manager.subscribe(
                "workflow.runtime",
                f"{resolved.kafka.consumer_group}-fleet-observers",
                _build_fleet_observer_runtime_handler(app),
            )

    api_router = APIRouter(prefix="/api/v1")

    @api_router.get("/protected")
    async def protected_endpoint(
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        return {"status": "ok", "user": current_user}

    if resolved.profile in {"api", "agentops", "composition", "discovery", "simulation"}:
        app.include_router(api_router)
        app.include_router(auth_router)
        app.include_router(accounts_router)
        app.include_router(workspaces_router)
        app.include_router(analytics_router)
        app.include_router(registry_router)
        app.include_router(context_engineering_router)
        app.include_router(evaluations_router)
        app.include_router(memory_router)
        app.include_router(marketplace_router)
        app.include_router(interactions_router)
        app.include_router(connectors_router)
        app.include_router(policies_router)
        app.include_router(testing_router)
        app.include_router(workflows_router)
        app.include_router(execution_router)
        app.include_router(trust_router, prefix="/api/v1/trust")
        app.include_router(fleets_router)
        app.include_router(fleet_learning_router)
        app.include_router(agentops_router)
        app.include_router(composition_router)
        app.include_router(discovery_router)
        app.include_router(simulation_router)

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
            interactions_service = build_interactions_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
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
                interactions_service=interactions_service,
                memory_service=memory_service,
                connectors_service=None,
                policies_service=build_policy_service(
                    session=session,
                    settings=cast(PlatformSettings, app.state.settings),
                    producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                    redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                    registry_service=registry_service,
                    workspaces_service=workspaces_service,
                    reasoning_client=cast(
                        ReasoningEngineClient | None,
                        app.state.clients.get("reasoning_engine"),
                    ),
                ),
            )
            await DriftMonitorTask(service).run()

    scheduler.add_job(
        _run_drift_analysis,
        trigger,
        id="context-engineering-drift-analysis",
    )
    return scheduler


def _build_discovery_proximity_scheduler(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _drain_cycle_completed_queue() -> None:
        # Actual cycle-completed events are delivered through Kafka. This periodic
        # job is intentionally lightweight and keeps the discovery runtime profile
        # ready for queued proximity work without scanning unrelated tables.
        return None

    scheduler.add_job(
        _drain_cycle_completed_queue,
        "interval",
        seconds=60,
        id="discovery-proximity-clustering",
    )
    return scheduler


def _build_simulation_prediction_scheduler(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run_prediction_worker() -> None:
        async with database.AsyncSessionLocal() as session:
            service = build_simulation_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient | None, app.state.clients.get("redis")),
                simulation_controller=cast(
                    SimulationControllerClient | None,
                    app.state.clients.get("simulation_controller"),
                ),
                clickhouse_client=cast(
                    AsyncClickHouseClient | None, app.state.clients.get("clickhouse")
                ),
                registry_service=getattr(app.state, "registry_service", None),
                policy_service=getattr(app.state, "policy_service", None),
            )
            try:
                await service.prediction_worker.run_once()
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Simulation prediction worker failed")

    scheduler.add_job(
        _run_prediction_worker,
        "interval",
        seconds=app.state.settings.simulation.prediction_worker_interval_seconds,
        id="simulation-prediction-worker",
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


def _build_workflow_execution_scheduler(app: FastAPI) -> Any | None:
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
    cron_trigger = trigger_module.CronTrigger

    async def _fire_cron_trigger(workflow_id: str, trigger_id: str) -> None:
        async with database.AsyncSessionLocal() as session:
            workflow_service = build_workflow_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                scheduler=app.state.workflow_scheduler,
            )
            execution_service = build_execution_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
                runtime_controller=cast(
                    RuntimeControllerClient | None,
                    app.state.clients.get("runtime_controller"),
                ),
                reasoning_engine=cast(
                    ReasoningEngineClient | None,
                    app.state.clients.get("reasoning_engine"),
                ),
                context_engineering_service=None,
            )
            try:
                workflow = await workflow_service.get_workflow(UUID(workflow_id))
                execution = await execution_service.create_execution(
                    ExecutionCreate(
                        workflow_definition_id=workflow.id,
                        trigger_type=TriggerType.cron,
                        trigger_id=UUID(trigger_id),
                        input_parameters={},
                        workspace_id=workflow.workspace_id,
                    )
                )
                await workflow_service.record_trigger_fired(
                    UUID(trigger_id),
                    execution_id=execution.id,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception(
                    "Workflow cron trigger failed",
                    extra={"workflow_id": workflow_id, "trigger_id": trigger_id},
                )

    async def _load_cron_triggers() -> None:
        async with database.AsyncSessionLocal() as session:
            workflow_service = build_workflow_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                scheduler=app.state.workflow_scheduler,
            )
            try:
                triggers = await workflow_service.repository.list_active_triggers_by_type(
                    TriggerType.cron
                )
                for trigger in triggers:
                    expression = str(trigger.config.get("cron_expression", "")).strip()
                    timezone = str(trigger.config.get("timezone", "UTC"))
                    if not expression:
                        continue
                    scheduler.add_job(
                        _fire_cron_trigger,
                        cron_trigger.from_crontab(expression, timezone=timezone),
                        id=str(trigger.id),
                        replace_existing=True,
                        args=[str(trigger.definition_id), str(trigger.id)],
                    )
            except Exception:
                LOGGER.exception("Failed to load workflow cron triggers")

    async def _run_tick() -> None:
        async with database.AsyncSessionLocal() as session:
            scheduler_service = build_scheduler_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
                runtime_controller=cast(
                    RuntimeControllerClient | None,
                    app.state.clients.get("runtime_controller"),
                ),
                reasoning_engine=cast(
                    ReasoningEngineClient | None,
                    app.state.clients.get("reasoning_engine"),
                ),
                context_engineering_service=None,
                interactions_service=None,
            )
            try:
                await scheduler_service.tick()
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Workflow execution tick failed")

    async def _run_approval_timeout_scan() -> None:
        async with database.AsyncSessionLocal() as session:
            scheduler_service = build_scheduler_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
                runtime_controller=cast(
                    RuntimeControllerClient | None,
                    app.state.clients.get("runtime_controller"),
                ),
                reasoning_engine=cast(
                    ReasoningEngineClient | None,
                    app.state.clients.get("reasoning_engine"),
                ),
                context_engineering_service=None,
                interactions_service=None,
            )
            try:
                await scheduler_service.scan_approval_timeouts()
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Workflow approval timeout scan failed")

    scheduler.add_job(_load_cron_triggers, "date", id="workflow-cron-loader")
    scheduler.add_job(_run_tick, "interval", seconds=1, id="workflow-execution-tick")
    scheduler.add_job(
        _run_approval_timeout_scan,
        "interval",
        seconds=60,
        id="workflow-approval-timeout-scan",
    )
    return scheduler


def _build_workflow_runtime_handler(app: FastAPI) -> Callable[[Any], Awaitable[None]]:
    async def _handle(envelope: Any) -> None:
        payload = envelope.payload
        execution_id = payload.get("execution_id")
        event_type = payload.get("event_type")
        if execution_id is None or event_type is None:
            return
        async with database.AsyncSessionLocal() as session:
            service = build_execution_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
                runtime_controller=cast(
                    RuntimeControllerClient | None,
                    app.state.clients.get("runtime_controller"),
                ),
                reasoning_engine=cast(
                    ReasoningEngineClient | None,
                    app.state.clients.get("reasoning_engine"),
                ),
                context_engineering_service=None,
            )
            status_map = {
                "completed": ExecutionStatus.running,
                "failed": ExecutionStatus.failed,
                "runtime_started": ExecutionStatus.running,
            }
            event_enum = ExecutionEventType(str(event_type))
            try:
                await service.record_runtime_event(
                    UUID(str(execution_id)),
                    step_id=payload.get("step_id"),
                    event_type=event_enum,
                    payload=dict(payload),
                    status=status_map.get(event_enum.value),
                )
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Workflow runtime consumer failed")

    return _handle


def _build_discovery_workflow_runtime_handler(app: FastAPI) -> Callable[[Any], Awaitable[None]]:
    async def _handle(envelope: Any) -> None:
        payload = getattr(envelope, "payload", {})
        if payload.get("session_id") is None:
            return
        LOGGER.debug(
            "Discovery workflow runtime event received",
            extra={
                "profile": app.state.settings.profile,
                "session_id": payload.get("session_id"),
            },
        )

    return _handle


def _build_simulation_event_handler(app: FastAPI) -> Callable[[Any], Awaitable[None]]:
    async def _handle(envelope: Any) -> None:
        async with database.AsyncSessionLocal() as session:
            service = build_simulation_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient | None, app.state.clients.get("redis")),
                simulation_controller=cast(
                    SimulationControllerClient | None,
                    app.state.clients.get("simulation_controller"),
                ),
                clickhouse_client=cast(
                    AsyncClickHouseClient | None, app.state.clients.get("clickhouse")
                ),
                registry_service=getattr(app.state, "registry_service", None),
                policy_service=getattr(app.state, "policy_service", None),
            )
            try:
                await service.events_consumer.handle_event(envelope)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Simulation event consumer failed")

    return _handle


def _build_reprioritization_handler(
    app: FastAPI,
    trigger_reason: str,
) -> Callable[[Any], Awaitable[None]]:
    async def _handle(envelope: Any) -> None:
        execution_id = envelope.payload.get("execution_id")
        if execution_id is None:
            return
        async with database.AsyncSessionLocal() as session:
            scheduler_service = build_scheduler_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
                runtime_controller=cast(
                    RuntimeControllerClient | None,
                    app.state.clients.get("runtime_controller"),
                ),
                reasoning_engine=cast(
                    ReasoningEngineClient | None,
                    app.state.clients.get("reasoning_engine"),
                ),
                context_engineering_service=None,
                interactions_service=None,
            )
            try:
                await scheduler_service.handle_reprioritization_trigger(
                    trigger_reason,
                    UUID(str(execution_id)),
                )
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception(
                    "Workflow reprioritization consumer failed",
                    extra={"trigger_reason": trigger_reason},
                )

    return _handle


def _build_workspace_goal_handler(app: FastAPI) -> Callable[[Any], Awaitable[None]]:
    async def _handle(envelope: Any) -> None:
        workspace_id = envelope.payload.get("workspace_id")
        goal_type = str(envelope.payload.get("goal_type", ""))
        goal_id = envelope.payload.get("goal_id")
        if workspace_id is None:
            return
        async with database.AsyncSessionLocal() as session:
            workflow_service = build_workflow_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                scheduler=app.state.workflow_scheduler,
            )
            execution_service = build_execution_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
                runtime_controller=cast(
                    RuntimeControllerClient | None,
                    app.state.clients.get("runtime_controller"),
                ),
                reasoning_engine=cast(
                    ReasoningEngineClient | None,
                    app.state.clients.get("reasoning_engine"),
                ),
                context_engineering_service=None,
            )
            try:
                triggers = await workflow_service.repository.list_active_triggers_by_type(
                    TriggerType.workspace_goal
                )
                for trigger in triggers:
                    configured_workspace = str(trigger.config.get("workspace_id", workspace_id))
                    pattern = str(trigger.config.get("goal_type_pattern", "*"))
                    if configured_workspace != str(workspace_id):
                        continue
                    if not fnmatch(goal_type, pattern):
                        continue
                    workflow = await workflow_service.get_workflow(trigger.definition_id)
                    execution = await execution_service.create_execution(
                        ExecutionCreate(
                            workflow_definition_id=workflow.id,
                            trigger_type=TriggerType.workspace_goal,
                            trigger_id=trigger.id,
                            input_parameters=dict(envelope.payload),
                            workspace_id=workflow.workspace_id,
                            correlation_goal_id=UUID(str(goal_id)) if goal_id else None,
                        )
                    )
                    await workflow_service.record_trigger_fired(
                        trigger.id,
                        execution_id=execution.id,
                    )
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Workspace goal trigger consumer failed")

    return _handle


def _build_event_bus_handler(app: FastAPI) -> Callable[[Any], Awaitable[None]]:
    async def _handle(envelope: Any) -> None:
        async with database.AsyncSessionLocal() as session:
            workflow_service = build_workflow_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                scheduler=app.state.workflow_scheduler,
            )
            execution_service = build_execution_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
                runtime_controller=cast(
                    RuntimeControllerClient | None,
                    app.state.clients.get("runtime_controller"),
                ),
                reasoning_engine=cast(
                    ReasoningEngineClient | None,
                    app.state.clients.get("reasoning_engine"),
                ),
                context_engineering_service=None,
            )
            try:
                await event_bus_consumer_handler(
                    envelope,
                    workflow_service=workflow_service,
                    execution_service=execution_service,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Event bus trigger consumer failed")

    return _handle


def _build_connector_delivery_handler(
    app: FastAPI,
) -> Callable[[Any], Awaitable[None]]:
    async def _handle(envelope: Any) -> None:
        delivery_id = envelope.payload.get("delivery_id")
        if delivery_id is None:
            return
        async with database.AsyncSessionLocal() as session:
            service = build_connectors_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
            )
            try:
                await service.execute_delivery(UUID(str(delivery_id)))
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception(
                    "Connector delivery handler failed",
                    extra={"delivery_id": str(delivery_id)},
                )

    return _handle


def _build_policy_bundle_invalidator(
    app: FastAPI,
) -> Callable[[str], Awaitable[None]]:
    async def _invalidate(revision_id: str) -> None:
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
            service = build_policy_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                registry_service=registry_service,
                workspaces_service=workspaces_service,
                reasoning_client=cast(
                    ReasoningEngineClient | None,
                    app.state.clients.get("reasoning_engine"),
                ),
            )
            await service.invalidate_bundle_by_revision(revision_id)

    return _invalidate


def _build_marketplace_scheduler(app: FastAPI) -> Any | None:
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
    cron_trigger = trigger_module.CronTrigger

    async def _run_cf_job() -> None:
        async with database.AsyncSessionLocal() as session:
            workspaces_service = build_workspaces_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                accounts_service=None,
            )
            search_service = build_marketplace_search_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                opensearch=cast(AsyncOpenSearchClient, app.state.clients["opensearch"]),
                qdrant=cast(AsyncQdrantClient, app.state.clients["qdrant"]),
                workspaces_service=workspaces_service,
            )
            recommendation_service = build_marketplace_recommendation_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                clickhouse=cast(AsyncClickHouseClient, app.state.clients["clickhouse"]),
                qdrant=cast(AsyncQdrantClient, app.state.clients["qdrant"]),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                search_service=search_service,
                workspaces_service=workspaces_service,
            )
            try:
                await run_cf_recommendations(
                    service=recommendation_service,
                    repository=MarketplaceRepository(session),
                )
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Marketplace collaborative recommendation job failed")

    async def _run_trending_job() -> None:
        async with database.AsyncSessionLocal() as session:
            try:
                await run_trending_computation(
                    repository=MarketplaceRepository(session),
                    clickhouse=cast(AsyncClickHouseClient, app.state.clients["clickhouse"]),
                    redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                    producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                )
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Marketplace trending computation job failed")

    scheduler.add_job(
        _run_cf_job,
        cron_trigger(hour=2, minute=0, timezone="UTC"),
        id="marketplace_cf_recs",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_trending_job,
        cron_trigger(hour=3, minute=0, timezone="UTC"),
        id="marketplace_trending",
        replace_existing=True,
    )
    return scheduler


def _build_fleet_learning_scheduler(app: FastAPI) -> Any | None:
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
    cron_trigger = trigger_module.CronTrigger

    async def _run_compute_profiles() -> None:
        async with database.AsyncSessionLocal() as session:
            fleet_service = build_fleet_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                registry_service=None,
                health_service=None,
                runtime_controller=cast(
                    RuntimeControllerClient | None,
                    app.state.clients.get("runtime_controller"),
                ),
            )
            service = build_performance_service(
                session=session,
                clickhouse=cast(AsyncClickHouseClient, app.state.clients["clickhouse"]),
                fleet_service=fleet_service,
            )
            try:
                now = datetime.now(UTC)
                period_end = now.replace(hour=0, minute=0, second=0, microsecond=0)
                period_start = period_end - timedelta(days=1)
                await service.compute_all_profiles(period_start, period_end)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Fleet performance profile scheduler failed")

    async def _run_adaptation_scan() -> None:
        async with database.AsyncSessionLocal() as session:
            fleet_service = build_fleet_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                registry_service=None,
                health_service=None,
                runtime_controller=cast(
                    RuntimeControllerClient | None,
                    app.state.clients.get("runtime_controller"),
                ),
            )
            service = build_adaptation_service(
                session=session,
                fleet_service=fleet_service,
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            try:
                await service.evaluate_all_fleets()
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Fleet adaptation scheduler failed")

    scheduler.add_job(
        _run_compute_profiles,
        cron_trigger(hour=1, minute=0),
        id="fleet-learning-compute-profiles",
    )
    scheduler.add_job(
        _run_adaptation_scan,
        cron_trigger(hour=1, minute=5),
        id="fleet-learning-evaluate-adaptations",
    )
    return scheduler


def _build_agentops_lifecycle_scheduler(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run_handler(method_name: str) -> None:
        async with database.AsyncSessionLocal() as session:
            service = build_agentops_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                clickhouse_client=cast(AsyncClickHouseClient, app.state.clients["clickhouse"]),
                reasoning_client=cast(
                    ReasoningEngineClient | None,
                    app.state.clients.get("reasoning_engine"),
                ),
            )
            try:
                await cast(Callable[[], Awaitable[None]], getattr(service, method_name))()
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception(
                    "AgentOps lifecycle scheduler failed",
                    extra={"handler": method_name},
                )

    async def _run_health_scores() -> None:
        await _run_handler("score_all_agents_task")

    async def _run_canary_monitor() -> None:
        await _run_handler("monitor_active_canaries_task")

    async def _run_retirement_grace() -> None:
        await _run_handler("retirement_grace_period_scanner_task")

    async def _run_recertification_grace() -> None:
        await _run_handler("recertification_grace_period_scanner_task")

    scheduler.add_job(
        _run_health_scores,
        "interval",
        minutes=15,
        id="agentops-health-score",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_canary_monitor,
        "interval",
        minutes=5,
        id="agentops-canary-monitor",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_retirement_grace,
        "interval",
        hours=1,
        id="agentops-retirement-grace",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_recertification_grace,
        "interval",
        hours=1,
        id="agentops-recertification-grace",
        replace_existing=True,
    )
    return scheduler


def _build_agentops_drift_scheduler(app: FastAPI) -> Any | None:
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
    cron_trigger = trigger_module.CronTrigger

    async def _run_drift_scan() -> None:
        async with database.AsyncSessionLocal() as session:
            service = build_drift_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                clickhouse_client=cast(AsyncClickHouseClient, app.state.clients["clickhouse"]),
            )
            try:
                await service.run_drift_scan_all()
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("AgentOps drift scan failed")

    scheduler.add_job(
        _run_drift_scan,
        cron_trigger(hour=4, minute=0, timezone="UTC"),
        id="agentops-drift-scan",
        replace_existing=True,
    )
    return scheduler


def _build_robustness_orchestrator_scheduler(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run_pending_robustness() -> None:
        async with database.AsyncSessionLocal() as session:
            drift_service = build_drift_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                clickhouse_client=cast(AsyncClickHouseClient, app.state.clients["clickhouse"]),
            )
            execution_service = build_execution_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
                runtime_controller=cast(
                    RuntimeControllerClient | None,
                    app.state.clients.get("runtime_controller"),
                ),
                reasoning_engine=cast(
                    ReasoningEngineClient | None,
                    app.state.clients.get("reasoning_engine"),
                ),
                context_engineering_service=None,
            )
            eval_runner_service = build_eval_runner_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                qdrant=cast(AsyncQdrantClient, app.state.clients["qdrant"]),
                runtime_controller=cast(
                    RuntimeControllerClient | None,
                    app.state.clients.get("runtime_controller"),
                ),
                reasoning_engine=cast(
                    ReasoningEngineClient | None,
                    app.state.clients.get("reasoning_engine"),
                ),
                execution_service=execution_service,
                drift_service=drift_service,
            )
            service = build_robustness_service(
                session=session,
                eval_runner_service=eval_runner_service,
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            repository = EvaluationRepository(session)
            pending_runs = await repository.list_pending_robustness_runs(limit=10)
            for pending_run in pending_runs:
                try:
                    await service.execute_run(pending_run.id)
                except Exception:
                    await session.rollback()
                    LOGGER.exception(
                        "Robustness orchestrator failed",
                        extra={"robustness_run_id": str(pending_run.id)},
                    )

    scheduler.add_job(
        _run_pending_robustness,
        "interval",
        seconds=30,
        id="agentops-robustness-orchestrator",
        replace_existing=True,
    )
    return scheduler


def _build_marketplace_quality_handler(
    app: FastAPI,
    method_name: str,
) -> Callable[[Any], Awaitable[None]]:
    async def _handle(envelope: Any) -> None:
        async with database.AsyncSessionLocal() as session:
            service = build_marketplace_quality_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            try:
                handler = getattr(service, method_name)
                await handler(envelope)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception(
                    "Marketplace quality consumer failed",
                    extra={"handler": method_name},
                )

    return _handle


async def _load_trust_runtime_assets(app: FastAPI) -> None:
    async with database.AsyncSessionLocal() as session:
        prescreener_service = build_prescreener_service(
            session=session,
            settings=cast(PlatformSettings, app.state.settings),
            producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
            object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
        )
        await prescreener_service.load_active_rules()
        circuit_breaker_service = build_circuit_breaker_service(
            session=session,
            settings=cast(PlatformSettings, app.state.settings),
            producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
            runtime_controller=cast(
                RuntimeControllerClient | None,
                app.state.clients.get("runtime_controller"),
            ),
        )
        await circuit_breaker_service.load_script()


def _build_trust_certifier_scheduler(app: FastAPI) -> Any | None:
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
    cron_trigger = trigger_module.CronTrigger

    async def _run_expire_stale() -> None:
        async with database.AsyncSessionLocal() as session:
            service = build_certification_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            try:
                await service.expire_stale()
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Trust certification stale expiry scan failed")

    async def _run_expiry_approaching_scan() -> None:
        async with database.AsyncSessionLocal() as session:
            service = build_recertification_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            try:
                await service.scan_expiry_approaching()
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Trust recertification expiry scan failed")

    async def _run_ate_timeout_scan() -> None:
        async with database.AsyncSessionLocal() as session:
            service = build_ate_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
                simulation_controller=cast(
                    SimulationControllerClient | None,
                    app.state.clients.get("simulation_controller"),
                ),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
            )
            try:
                await service.scan_timed_out_runs()
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Trust ATE timeout scan failed")

    scheduler.add_job(_run_expire_stale, "interval", hours=1, id="trust-expire-stale")
    scheduler.add_job(
        _run_expiry_approaching_scan,
        cron_trigger(hour=0, minute=5, timezone="UTC"),
        id="trust-recertification-expiry-approaching",
    )
    scheduler.add_job(
        _run_ate_timeout_scan,
        "interval",
        minutes=5,
        id="trust-ate-timeout-scan",
    )
    return scheduler


def _build_fleet_runtime_lifecycle_handler(app: FastAPI) -> Callable[[Any], Awaitable[None]]:
    async def _handle(envelope: Any) -> None:
        payload = envelope.payload
        event_type = payload.get("event_type") or envelope.event_type
        if event_type not in {"runtime.heartbeat_missed", "runtime.started"}:
            return
        agent_fqn = payload.get("agent_fqn") or payload.get("source_agent_fqn")
        if not isinstance(agent_fqn, str) or not agent_fqn:
            return
        async with database.AsyncSessionLocal() as session:
            service = build_health_service(
                session=session,
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            try:
                await service.handle_member_availability_change(
                    agent_fqn,
                    is_available=event_type == "runtime.started",
                )
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Fleet runtime lifecycle consumer failed")

    return _handle


def _build_fleet_observer_runtime_handler(app: FastAPI) -> Callable[[Any], Awaitable[None]]:
    async def _handle(envelope: Any) -> None:
        async with database.AsyncSessionLocal() as session:
            try:
                await route_execution_event_to_observers(
                    envelope,
                    member_repo=FleetMemberRepository(session),
                    producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                )
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Fleet observer routing consumer failed")

    return _handle


def _build_trust_registry_handler(app: FastAPI) -> Callable[[Any], Awaitable[None]]:
    async def _handle(envelope: Any) -> None:
        payload = envelope.payload
        if payload.get("event_type") not in {None, "agent_revision.published"}:
            return
        async with database.AsyncSessionLocal() as session:
            service = build_recertification_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            try:
                await service.handle_registry_event(payload)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Trust registry consumer failed")

    return _handle


def _build_trust_policy_handler(app: FastAPI) -> Callable[[Any], Awaitable[None]]:
    async def _handle(envelope: Any) -> None:
        payload = envelope.payload
        if payload.get("event_type") not in {None, "policy.updated"}:
            return
        async with database.AsyncSessionLocal() as session:
            service = build_recertification_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            try:
                await service.handle_policy_event(payload)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Trust policy consumer failed")

    return _handle


def _build_trust_runtime_handler(app: FastAPI) -> Callable[[Any], Awaitable[None]]:
    async def _handle(envelope: Any) -> None:
        payload = envelope.payload
        event_type = payload.get("event_type")
        if event_type not in {"execution.guardrail_failed", "conformance_failed"}:
            return
        async with database.AsyncSessionLocal() as session:
            circuit_breaker_service = build_circuit_breaker_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                runtime_controller=cast(
                    RuntimeControllerClient | None,
                    app.state.clients.get("runtime_controller"),
                ),
            )
            recertification_service = build_recertification_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            try:
                agent_id = payload.get("agent_id")
                workspace_id = payload.get("workspace_id")
                if isinstance(agent_id, str) and isinstance(workspace_id, str):
                    await circuit_breaker_service.record_failure(
                        agent_id,
                        workspace_id,
                        execution_id=payload.get("execution_id"),
                        fleet_id=payload.get("fleet_id"),
                    )
                await recertification_service.handle_runtime_event(payload)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Trust workflow runtime consumer failed")

    return _handle


def _build_trust_simulation_handler(app: FastAPI) -> Callable[[Any], Awaitable[None]]:
    async def _handle(envelope: Any) -> None:
        payload = envelope.payload
        if payload.get("event_type") not in {None, "simulation.completed"}:
            return
        async with database.AsyncSessionLocal() as session:
            service = build_ate_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
                simulation_controller=cast(
                    SimulationControllerClient | None,
                    app.state.clients.get("simulation_controller"),
                ),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
            )
            try:
                await service.handle_simulation_completed(payload)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Trust simulation consumer failed")

    return _handle


def _build_trust_event_handler(app: FastAPI) -> Callable[[Any], Awaitable[None]]:
    async def _handle(envelope: Any) -> None:
        async with database.AsyncSessionLocal() as session:
            service = build_trust_tier_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            try:
                await service.handle_trust_event(envelope.payload)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Trust event consumer failed")

    return _handle


def _build_trust_prescreener_handler(app: FastAPI) -> Callable[[Any], Awaitable[None]]:
    async def _handle(envelope: Any) -> None:
        payload = envelope.payload
        if payload.get("event_type") not in {None, "prescreener.rule_set.activated"}:
            return
        async with database.AsyncSessionLocal() as session:
            service = build_prescreener_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
            )
            try:
                await service.handle_rule_set_activated(payload)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Trust prescreener consumer failed")

    return _handle


def _build_agentops_evaluation_handler(app: FastAPI) -> Callable[[Any], Awaitable[None]]:
    async def _handle(envelope: Any) -> None:
        async with database.AsyncSessionLocal() as session:
            service = build_agentops_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                clickhouse_client=cast(AsyncClickHouseClient, app.state.clients["clickhouse"]),
                reasoning_client=cast(
                    ReasoningEngineClient | None,
                    app.state.clients.get("reasoning_engine"),
                ),
            )
            triggers = AgentOpsGovernanceTriggers(
                repository=service.repository,
                detector=service.regression_detector(),
                evaluation_repository=EvaluationRepository(session),
                registry_service=service.registry_service,
                trust_service=service.trust_service,
                governance_publisher=service.governance_publisher,
                agentops_service=service,
            )
            try:
                await triggers.handle_evaluation_event(envelope)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("AgentOps evaluation consumer failed")

    return _handle


def _build_agentops_retirement_handler(app: FastAPI) -> Callable[[Any], Awaitable[None]]:
    async def _handle(envelope: Any) -> None:
        async with database.AsyncSessionLocal() as session:
            service = build_agentops_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                clickhouse_client=cast(AsyncClickHouseClient, app.state.clients["clickhouse"]),
                reasoning_client=cast(
                    ReasoningEngineClient | None,
                    app.state.clients.get("reasoning_engine"),
                ),
            )
            triggers = AgentOpsGovernanceTriggers(
                repository=service.repository,
                detector=service.regression_detector(),
                evaluation_repository=EvaluationRepository(session),
                registry_service=service.registry_service,
                trust_service=service.trust_service,
                governance_publisher=service.governance_publisher,
                agentops_service=service,
            )
            try:
                await triggers.handle_agentops_event(envelope)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("AgentOps retirement consumer failed")

    return _handle


def _build_agentops_trust_handler(app: FastAPI) -> Callable[[Any], Awaitable[None]]:
    async def _handle(envelope: Any) -> None:
        async with database.AsyncSessionLocal() as session:
            service = build_agentops_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                clickhouse_client=cast(AsyncClickHouseClient, app.state.clients["clickhouse"]),
                reasoning_client=cast(
                    ReasoningEngineClient | None,
                    app.state.clients.get("reasoning_engine"),
                ),
            )
            triggers = AgentOpsGovernanceTriggers(
                repository=service.repository,
                detector=service.regression_detector(),
                evaluation_repository=EvaluationRepository(session),
                registry_service=service.registry_service,
                trust_service=service.trust_service,
                governance_publisher=service.governance_publisher,
                agentops_service=service,
            )
            try:
                await triggers.handle_trust_event(envelope)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("AgentOps trust consumer failed")

    return _handle


def _build_connectors_worker_scheduler(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run_retry_scan() -> None:
        async with database.AsyncSessionLocal() as session:
            service = build_connectors_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
            )
            try:
                await RetryScanner(service).run()
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Connector retry scan failed")

    async def _run_email_polling() -> None:
        async with database.AsyncSessionLocal() as session:
            service = build_connectors_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
            )
            try:
                await EmailPollingJob(service.poll_email_connectors).run()
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Connector email polling failed")

    scheduler.add_job(
        _run_retry_scan,
        "interval",
        seconds=max(1, app.state.settings.connectors.retry_scan_interval_seconds),
        id="connectors-retry-scan",
    )
    scheduler.add_job(
        _run_email_polling,
        "interval",
        seconds=max(1, app.state.settings.connectors.email_poll_interval_seconds),
        id="connectors-email-polling",
    )
    return scheduler
