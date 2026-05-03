from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from fnmatch import fnmatch
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from platform.a2a_gateway.events import (
    A2AEventPayload,
    A2AEventPublisher,
    A2AEventType,
    register_a2a_event_types,
)
from platform.a2a_gateway.models import A2AAuditRecord, A2ATaskState
from platform.a2a_gateway.repository import A2AGatewayRepository
from platform.a2a_gateway.router import router as a2a_gateway_router
from platform.accounts.events import register_accounts_event_types
from platform.accounts.jobs.workspace_auto_create import build_workspace_auto_create_retry
from platform.accounts.onboarding_router import router as onboarding_router
from platform.accounts.repository import AccountsRepository
from platform.accounts.router import router as accounts_router
from platform.accounts.setup_router import router as setup_router
from platform.admin.bootstrap import BootstrapConfigError, bootstrap_superadmin_from_env
from platform.admin.events import register_admin_event_types
from platform.admin.read_only_middleware import AdminReadOnlyMiddleware
from platform.admin.router import admin_router
from platform.admin.security_scheduler import build_admin_security_expiry_scheduler
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
from platform.audit.router import router as audit_router
from platform.audit.signing import AuditChainSigning
from platform.auth.events import register_auth_event_types
from platform.auth.ibor_sync import IBORSyncService
from platform.auth.repository import AuthRepository
from platform.auth.router import router as auth_router
from platform.auth.router_oauth import oauth_router
from platform.auth.services.oauth_bootstrap import (
    bootstrap_oauth_providers_from_env,
    oauth_bootstrap_enabled,
)
from platform.billing.exceptions import (
    ModelTierNotAllowedError,
    NoActiveSubscriptionError,
    OverageCapExceededError,
    OverageRequiredError,
    QuotaExceededError,
    SubscriptionSuspendedError,
)
from platform.billing.plans.admin_router import router as billing_admin_plans_router
from platform.billing.plans.public_router import router as billing_public_plans_router
from platform.billing.plans.seeder import provision_default_plans_if_missing
from platform.billing.providers.protocol import PaymentProvider
from platform.billing.providers.stub_provider import StubPaymentProvider
from platform.billing.quotas.metering import MeteringJob
from platform.billing.quotas.reconciliation import build_billing_reconciliation_scheduler
from platform.billing.subscriptions.admin_router import router as billing_admin_subscriptions_router
from platform.billing.subscriptions.events import register_billing_event_types
from platform.billing.subscriptions.period_scheduler import build_period_rollover_scheduler
from platform.billing.subscriptions.router import router as billing_workspace_router
from platform.common import database
from platform.common.api_versioning.registry import clear_markers, mark_deprecated
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
from platform.common.debug_logging.capture import DebugCaptureMiddleware
from platform.common.debug_logging.events import register_debug_logging_event_types
from platform.common.debug_logging.router import router as debug_logging_router
from platform.common.debug_logging.service import purge_debug_captures
from platform.common.dependencies import get_current_user
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.common.logging import configure_logging, get_logger
from platform.common.middleware.api_versioning_middleware import ApiVersioningMiddleware
from platform.common.middleware.correlation_logging_middleware import CorrelationLoggingMiddleware
from platform.common.middleware.rate_limit_middleware import RateLimitMiddleware
from platform.common.middleware.tenant_resolver import TenantResolverMiddleware
from platform.common.secret_provider import (
    KubernetesSecretProvider,
    MockSecretProvider,
    SecretProvider,
    VaultSecretProvider,
)
from platform.common.tagging.router import (
    admin_labels_router as tagging_admin_labels_router,
)
from platform.common.tagging.router import labels_router as tagging_labels_router
from platform.common.tagging.router import saved_views_router as tagging_saved_views_router
from platform.common.tagging.router import tags_router as tagging_tags_router
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
from platform.cost_governance.clickhouse_repository import ClickHouseCostRepository
from platform.cost_governance.clickhouse_setup import run_setup as run_cost_clickhouse_setup
from platform.cost_governance.events import register_cost_governance_event_types
from platform.cost_governance.jobs.anomaly_job import build_anomaly_scheduler
from platform.cost_governance.jobs.forecast_job import build_forecast_scheduler
from platform.cost_governance.router import router as cost_governance_router
from platform.data_lifecycle.events import register_data_lifecycle_event_types
from platform.data_lifecycle.routers.dpa_router import (
    admin_router as data_lifecycle_dpa_admin_router,
)
from platform.data_lifecycle.routers.dpa_router import (
    me_router as data_lifecycle_dpa_me_router,
)
from platform.data_lifecycle.routers.sub_processors_router import (
    admin_router as data_lifecycle_sub_processors_admin_router,
)
from platform.data_lifecycle.routers.sub_processors_router import (
    public_router as data_lifecycle_sub_processors_public_router,
)
from platform.data_lifecycle.routers.tenant_admin_router import (
    router as data_lifecycle_tenant_admin_router,
)
from platform.data_lifecycle.routers.workspace_router import (
    cancel_router as data_lifecycle_cancel_router,
)
from platform.data_lifecycle.routers.workspace_router import (
    router as data_lifecycle_workspace_router,
)
from platform.discovery.dependencies import build_discovery_service
from platform.discovery.events import register_discovery_event_types
from platform.discovery.router import router as discovery_router
from platform.evaluation.dependencies import (
    build_eval_runner_service,
    build_robustness_service,
    build_rubric_service,
)
from platform.evaluation.events import register_evaluation_event_types
from platform.evaluation.repository import EvaluationRepository
from platform.evaluation.rubric_templates import RubricTemplateLoader
from platform.evaluation.scorers.semantic import SemanticSimilarityScorer
from platform.execution.dependencies import (
    build_checkpoint_service,
    build_execution_service,
    build_scheduler_service,
)
from platform.execution.events import (
    event_bus_consumer_handler,
    register_execution_consumers,
    register_execution_event_types,
)
from platform.execution.models import ExecutionEventType, ExecutionStatus
from platform.execution.router import router as execution_router
from platform.execution.router import runtime_router as execution_runtime_router
from platform.execution.router import trigger_router as execution_reprioritization_router
from platform.execution.schemas import ExecutionCreate
from platform.fleet_learning.dependencies import build_adaptation_service, build_performance_service
from platform.fleet_learning.router import router as fleet_learning_router
from platform.fleets.dependencies import build_fleet_service, build_health_service
from platform.fleets.events import register_fleet_event_types
from platform.fleets.repository import FleetMemberRepository
from platform.fleets.router import router as fleets_router
from platform.fleets.service import route_execution_event_to_observers
from platform.governance.consumers import ObserverSignalConsumer, VerdictConsumer
from platform.governance.events import register_governance_event_types
from platform.governance.repository import GovernanceRepository
from platform.governance.router import router as governance_router
from platform.incident_response.events import register_incident_response_event_types
from platform.incident_response.jobs.delivery_retry_scanner import build_delivery_retry_scheduler
from platform.incident_response.jobs.runbook_freshness_scanner import (
    build_runbook_freshness_scheduler,
)
from platform.incident_response.router import router as incident_response_router
from platform.incident_response.runtime import AppIncidentTrigger
from platform.incident_response.trigger_interface import (
    register_incident_trigger,
    reset_incident_trigger,
)
from platform.interactions.dependencies import build_interactions_service
from platform.interactions.events import register_interactions_event_types
from platform.interactions.goal_lifecycle import GoalAutoCompletionScanner
from platform.interactions.router import router as interactions_router
from platform.localization.events import register_localization_event_types
from platform.localization.router import router as localization_router
from platform.marketplace.consumer import MarketplaceFanoutConsumer
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
from platform.mcp.events import register_mcp_event_types
from platform.mcp.router import router as mcp_router
from platform.me.router import router as me_router
from platform.memory.consolidation_worker import ConsolidationWorker, SessionMemoryCleaner
from platform.memory.dependencies import build_memory_service
from platform.memory.embedding_worker import EmbeddingWorker
from platform.memory.events import register_memory_event_types
from platform.memory.memory_setup import setup_memory_collections
from platform.memory.router import router as memory_router
from platform.model_catalog.events import register_model_catalog_event_types
from platform.model_catalog.router import router as model_catalog_router
from platform.multi_region_ops.events import register_multi_region_ops_event_types
from platform.multi_region_ops.jobs.capacity_projection_runner import (
    build_capacity_projection_scheduler,
)
from platform.multi_region_ops.jobs.maintenance_window_runner import (
    build_maintenance_window_scheduler,
)
from platform.multi_region_ops.jobs.replication_probe_runner import (
    build_replication_probe_scheduler,
)
from platform.multi_region_ops.middleware.maintenance_gate import MaintenanceGateMiddleware
from platform.multi_region_ops.router import router as multi_region_ops_router
from platform.notifications.consumers.attention_consumer import AttentionConsumer
from platform.notifications.consumers.state_change_consumer import StateChangeConsumer
from platform.notifications.deliverers.webhook_deliverer import WebhookDeliverer
from platform.notifications.dependencies import InMemorySecretProvider, build_notifications_service
from platform.notifications.events import register_notifications_event_types
from platform.notifications.repository import NotificationsRepository
from platform.notifications.router import router as notifications_router
from platform.notifications.routers.deadletter_router import (
    router as notifications_deadletter_router,
)
from platform.notifications.routers.webhooks_router import router as notifications_webhooks_router
from platform.notifications.workers.channel_verification_worker import (
    build_channel_verification_scheduler,
    expire_unverified_channels,
)
from platform.notifications.workers.deadletter_threshold_worker import (
    build_dead_letter_threshold_scheduler,
    run_dead_letter_threshold_scan,
)
from platform.notifications.workers.webhook_retry_worker import (
    run_webhook_retry_scan as run_workspace_webhook_retry_scan,
)
from platform.policies.dependencies import build_policy_service
from platform.policies.events import PolicyEventConsumer, register_policies_event_types
from platform.policies.router import router as policies_router
from platform.privacy_compliance.events import register_privacy_event_types
from platform.privacy_compliance.router import router as privacy_router
from platform.privacy_compliance.router_self_service import router as privacy_self_service_router
from platform.registry.dependencies import build_registry_service
from platform.registry.events import register_registry_event_types
from platform.registry.index_worker import RegistryIndexWorker
from platform.registry.registry_opensearch_setup import create_marketplace_agents_index
from platform.registry.registry_qdrant_setup import create_agent_embeddings_collection
from platform.registry.router import router as registry_router
from platform.security.abuse_prevention.events import register_abuse_event_types
from platform.security_compliance.consumers import ComplianceEvidenceConsumer
from platform.security_compliance.events import register_security_compliance_event_types
from platform.security_compliance.router import router as security_compliance_router
from platform.simulation.dependencies import build_simulation_service
from platform.simulation.events import register_simulation_event_types
from platform.simulation.router import router as simulation_router
from platform.status_page.me_router import router as status_page_me_router
from platform.status_page.router import router as status_page_router
from platform.tenants.events import register_tenant_event_types
from platform.tenants.jobs.deletion_grace import build_tenant_deletion_scheduler
from platform.tenants.platform_router import router as tenants_platform_router
from platform.tenants.router import router as tenants_router
from platform.tenants.seeder import provision_default_tenant_if_missing
from platform.testing.dependencies import build_drift_service
from platform.testing.events import register_testing_event_types
from platform.testing.router_e2e import router as testing_e2e_router
from platform.testing.router_e2e_contract import router as e2e_contract_router
from platform.trust.contract_monitor import ContractMonitorConsumer
from platform.trust.dependencies import (
    build_ate_service,
    build_certification_service,
    build_circuit_breaker_service,
    build_prescreener_service,
    build_recertification_service,
    build_surveillance_service,
    build_trust_tier_service,
)
from platform.trust.events import register_trust_event_types
from platform.trust.router import router as trust_router
from platform.two_person_approval.router import router as two_pa_router
from platform.workflows.dependencies import build_workflow_service
from platform.workflows.events import register_workflows_event_types
from platform.workflows.models import TriggerType
from platform.workflows.router import router as workflows_router
from platform.workspaces.consumer import WorkspacesConsumer
from platform.workspaces.dependencies import build_workspaces_service
from platform.workspaces.events import register_workspaces_event_types
from platform.workspaces.platform_router import router as workspaces_platform_router
from platform.workspaces.router import router as workspaces_router
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from starlette.requests import Request

LOGGER = get_logger(__name__)

OPENAPI_PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        "/healthz",
        "/api/v1/healthz",
        "/api/openapi.json",
        "/api/docs",
        "/api/redoc",
        "/openapi.json",
        "/docs",
        "/redoc",
        "/api/v1/accounts/register",
        "/api/v1/accounts/verify-email",
        "/api/v1/accounts/resend-verification",
        "/api/v1/accounts/invitations/{token}",
        "/api/v1/accounts/invitations/{token}/accept",
        "/api/v1/setup/validate-token",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/mfa/verify",
        "/api/v1/auth/oauth/providers",
        "/api/v1/auth/oauth/links",
        "/api/v1/auth/oauth/{provider}/authorize",
        "/api/v1/auth/oauth/{provider}/callback",
        "/api/v1/public/plans",
        "/api/v1/security/audit-chain/public-key",
        "/.well-known/agent.json",
    }
)

DEFAULT_OPENAPI_SECURITY: tuple[dict[str, list[str]], ...] = (
    {"session": []},
    {"oauth2": []},
    {"apiKey": []},
)

PROFILE_SERVICE_NAMES: dict[str, str] = {
    "api": "api",
    "scheduler": "scheduler",
    "worker": "worker",
    "ws-hub": "ws",
    "trust-certifier": "trust-certifier",
    "context-engineering": "context-engineering",
    "projection-indexer": "projection-indexer",
    "agentops-testing": "agentops-testing",
}


def _platform_release_version() -> str:
    try:
        return package_version("musematic-control-plane")
    except PackageNotFoundError:
        return "0.1.0"


def _service_name_for_profile(profile: str) -> str:
    return PROFILE_SERVICE_NAMES.get(profile, profile)


async def billing_quota_exception_handler(
    request: Request,
    exc: PlatformError,
) -> JSONResponse:
    del request
    code_by_type = {
        QuotaExceededError: "quota_exceeded",
        OverageCapExceededError: "overage_cap_exceeded",
        ModelTierNotAllowedError: "model_tier_not_allowed",
        NoActiveSubscriptionError: "no_active_subscription",
        SubscriptionSuspendedError: "subscription_suspended",
    }
    if isinstance(exc, OverageRequiredError):
        return JSONResponse(
            status_code=202,
            content={
                "status": "paused_quota_exceeded",
                "quota_name": exc.details.get("quota_name"),
                "workspace_id": exc.details.get("workspace_id"),
            },
        )
    code = next(
        (value for error_type, value in code_by_type.items() if isinstance(exc, error_type)),
        exc.code.lower(),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": code, "message": exc.message, "details": exc.details},
    )


def _dedupe_tags(tags: list[str]) -> list[str]:
    return list(dict.fromkeys(tag for tag in tags if tag))


def _infer_openapi_tags(path: str) -> list[str]:
    if path in {"/health", "/healthz", "/api/v1/healthz"}:
        return ["health"]
    if path == "/api/v1/protected":
        return ["auth"]
    if path == "/.well-known/agent.json" or path.startswith("/api/v1/a2a/"):
        return ["a2a-gateway"]
    if path.startswith("/api/v1/mcp/protocol/"):
        return ["mcp"]
    if path.startswith("/api/v1/admin/"):
        segments = [segment for segment in path.split("/") if segment]
        if len(segments) >= 4:
            return ["admin", segments[3]]
        return ["admin"]
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) >= 3 and segments[0] == "api" and segments[1] == "v1":
        tag_map = {"me": "notifications"}
        return [tag_map.get(segments[2], segments[2])]
    return ["platform"]


def _is_public_openapi_operation(path: str) -> bool:
    return path in OPENAPI_PUBLIC_PATHS


def _openapi_security_requirement() -> list[dict[str, list[str]]]:
    return [dict(requirement) for requirement in DEFAULT_OPENAPI_SECURITY]


def _register_deprecated_routes(app: FastAPI) -> None:
    clear_markers()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        marker = getattr(route.endpoint, "__deprecated_marker__", None)
        if marker is None:
            continue
        sunset, successor = marker
        mark_deprecated(route.unique_id, sunset=sunset, successor=successor)
        route.deprecated = True


def _install_openapi_factory(app: FastAPI) -> None:
    def _custom_openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
            summary=app.summary,
        )
        info = schema.setdefault("info", {})
        info.setdefault(
            "contact",
            {
                "name": "musematic platform",
                "email": "platform@musematic.ai",
            },
        )
        components = schema.setdefault("components", {})
        security_schemes = components.setdefault("securitySchemes", {})
        security_schemes.setdefault(
            "session",
            {
                "type": "apiKey",
                "in": "cookie",
                "name": "session",
                "description": "Session cookie returned after interactive authentication.",
            },
        )
        security_schemes.setdefault(
            "oauth2",
            {
                "type": "oauth2",
                "description": (
                    "OAuth2 login via configured providers. Start the flow from "
                    "/api/v1/auth/oauth/{provider}/authorize."
                ),
                "flows": {
                    "authorizationCode": {
                        "authorizationUrl": app.state.settings.auth.oauth_google_authorize_url,
                        "tokenUrl": app.state.settings.auth.oauth_google_token_url,
                        "scopes": {},
                    }
                },
            },
        )
        security_schemes.setdefault(
            "apiKey",
            {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "Service-account API key.",
            },
        )

        for path, methods in schema.get("paths", {}).items():
            if not isinstance(methods, dict):
                continue
            for method, operation in methods.items():
                if method.startswith("x-") or not isinstance(operation, dict):
                    continue
                tags = list(operation.get("tags") or _infer_openapi_tags(path))
                if path.startswith("/api/v1/admin/") and "admin" not in tags:
                    tags.insert(0, "admin")
                operation["tags"] = _dedupe_tags(tags)
                if not _is_public_openapi_operation(path) and not operation.get("security"):
                    operation["security"] = _openapi_security_requirement()

        app.openapi_schema = schema
        return schema

    app.openapi = _custom_openapi  # type: ignore[method-assign]


def _build_clients(settings: PlatformSettings) -> dict[str, Any]:
    return {
        "redis": AsyncRedisClient.from_settings(settings),
        "kafka": EventProducer.from_settings(settings),
        "kafka_consumer": EventConsumerManager.from_settings(settings),
        "qdrant": AsyncQdrantClient.from_settings(settings),
        "neo4j": AsyncNeo4jClient.from_settings(settings),
        "clickhouse": AsyncClickHouseClient.from_settings(settings),
        "opensearch": AsyncOpenSearchClient.from_settings(settings),
        "object_storage": AsyncObjectStorageClient.from_settings(settings),
        "runtime_controller": RuntimeControllerClient.from_settings(settings),
        "reasoning_engine": ReasoningEngineClient.from_settings(settings),
        "sandbox_manager": SandboxManagerClient.from_settings(settings),
        "simulation_controller": SimulationControllerClient.from_settings(settings),
        "audit_signer": AuditChainSigning(settings.audit),
    }


def _build_payment_provider(settings: PlatformSettings) -> PaymentProvider:
    if settings.BILLING_PAYMENT_PROVIDER == "stub":
        return StubPaymentProvider()
    raise NotImplementedError("StripePaymentProvider lands in UPD-052")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.started_at = time.monotonic()
    app.state.degraded = False
    startup_errors: dict[str, str] = {}
    register_auth_event_types()
    register_accounts_event_types()
    register_workspaces_event_types()
    register_analytics_event_types()
    register_cost_governance_event_types()
    register_security_compliance_event_types()
    register_registry_event_types()
    register_context_engineering_event_types()
    register_memory_event_types()
    register_interactions_event_types()
    register_notifications_event_types()
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
    register_governance_event_types()
    register_a2a_event_types()
    register_mcp_event_types()
    register_abuse_event_types()
    register_debug_logging_event_types()
    register_privacy_event_types()
    register_model_catalog_event_types()
    register_incident_response_event_types()
    register_data_lifecycle_event_types()
    register_multi_region_ops_event_types()
    register_localization_event_types()
    register_admin_event_types()
    register_tenant_event_types()
    register_billing_event_types()
    register_incident_trigger(AppIncidentTrigger(app))

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
    try:
        async with database.AsyncSessionLocal() as session:
            await provision_default_tenant_if_missing(session)
            await provision_default_plans_if_missing(session)
            await session.commit()
    except Exception as exc:
        app.state.degraded = True
        startup_errors["tenant_default_seed"] = str(exc)
        LOGGER.warning("Failed to provision default tenant/plans during startup: %s", exc)

    if os.getenv("PLATFORM_SUPERADMIN_USERNAME"):
        try:
            await bootstrap_superadmin_from_env(
                session_factory=database.AsyncSessionLocal,
                settings=cast(PlatformSettings, app.state.settings),
                method="env_var",
            )
        except BootstrapConfigError:
            raise
        except Exception as exc:
            app.state.degraded = True
            startup_errors["superadmin_bootstrap"] = str(exc)
            LOGGER.warning("Failed to run super admin bootstrap: %s", exc)

    if oauth_bootstrap_enabled(cast(PlatformSettings, app.state.settings)):
        try:
            await bootstrap_oauth_providers_from_env(
                session_factory=database.AsyncSessionLocal,
                settings=cast(PlatformSettings, app.state.settings),
                secret_provider=app.state.secret_provider,
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
        except BootstrapConfigError:
            raise
        except Exception as exc:
            app.state.degraded = True
            startup_errors["oauth_bootstrap"] = str(exc)
            LOGGER.warning("Failed to run OAuth provider bootstrap: %s", exc)

    try:
        async with database.AsyncSessionLocal() as session:
            rubric_service = build_rubric_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            await RubricTemplateLoader().load_templates(rubric_service)
            await session.commit()
    except Exception as exc:
        app.state.degraded = True
        startup_errors["evaluation_rubric_templates"] = str(exc)
        LOGGER.warning("Failed to load evaluation rubric templates: %s", exc)

    clickhouse_client = app.state.clients.get("clickhouse")
    if isinstance(clickhouse_client, AsyncClickHouseClient):
        try:
            await run_analytics_clickhouse_setup(clickhouse_client, app.state.settings)
        except Exception as exc:
            app.state.degraded = True
            startup_errors["analytics_clickhouse_setup"] = str(exc)
            LOGGER.warning("Failed to run analytics ClickHouse setup: %s", exc)
        try:
            await run_cost_clickhouse_setup(clickhouse_client, app.state.settings)
        except Exception as exc:
            app.state.degraded = True
            startup_errors["cost_governance_clickhouse_setup"] = str(exc)
            LOGGER.warning("Failed to run cost governance ClickHouse setup: %s", exc)
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
    object_storage_client = app.state.clients.get("object_storage")
    if isinstance(object_storage_client, AsyncObjectStorageClient):
        for bucket_name in (
            "evaluation-ate-evidence",
            "evaluation-generated-suites",
            app.state.settings.incident_response.postmortem_minio_bucket,
        ):
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

    cost_clickhouse_repository = getattr(app.state, "cost_clickhouse_repository", None)
    if cost_clickhouse_repository is not None:
        try:
            await cost_clickhouse_repository.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["cost_clickhouse_batch_buffer"] = str(exc)
            LOGGER.warning("Failed to start cost ClickHouse batch buffer: %s", exc)

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
    goal_auto_completion_scheduler = getattr(app.state, "goal_auto_completion_scheduler", None)
    notifications_webhook_retry_scheduler = getattr(
        app.state,
        "notifications_webhook_retry_scheduler",
        None,
    )
    notifications_retention_gc_scheduler = getattr(
        app.state,
        "notifications_retention_gc_scheduler",
        None,
    )
    notifications_channel_verification_scheduler = getattr(
        app.state,
        "notifications_channel_verification_scheduler",
        None,
    )
    notifications_deadletter_threshold_scheduler = getattr(
        app.state,
        "notifications_deadletter_threshold_scheduler",
        None,
    )
    admin_security_expiry_scheduler = getattr(
        app.state,
        "admin_security_expiry_scheduler",
        None,
    )
    governance_retention_gc_scheduler = getattr(
        app.state,
        "governance_retention_gc_scheduler",
        None,
    )
    checkpoint_gc_scheduler = getattr(app.state, "checkpoint_gc_scheduler", None)
    debug_logging_capture_gc_scheduler = getattr(
        app.state,
        "debug_logging_capture_gc_scheduler",
        None,
    )
    a2a_idle_timeout_scheduler = getattr(app.state, "a2a_idle_timeout_scheduler", None)
    mcp_catalog_refresh_scheduler = getattr(app.state, "mcp_catalog_refresh_scheduler", None)
    model_catalog_auto_deprecation_scheduler = getattr(
        app.state,
        "model_catalog_auto_deprecation_scheduler",
        None,
    )
    ibor_sync_scheduler = getattr(app.state, "ibor_sync_scheduler", None)
    connectors_worker_scheduler = getattr(app.state, "connectors_worker_scheduler", None)
    workflow_execution_scheduler = getattr(app.state, "workflow_execution_scheduler", None)
    security_rotation_scheduler = getattr(app.state, "security_rotation_scheduler", None)
    security_overlap_expirer = getattr(app.state, "security_overlap_expirer", None)
    security_pentest_overdue_scheduler = getattr(
        app.state,
        "security_pentest_overdue_scheduler",
        None,
    )
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
    cost_forecast_scheduler = getattr(app.state, "cost_forecast_scheduler", None)
    cost_anomaly_scheduler = getattr(app.state, "cost_anomaly_scheduler", None)
    incident_response_delivery_retry_scheduler = getattr(
        app.state,
        "incident_response_delivery_retry_scheduler",
        None,
    )
    incident_response_runbook_freshness_scheduler = getattr(
        app.state,
        "incident_response_runbook_freshness_scheduler",
        None,
    )
    tenant_deletion_scheduler = getattr(app.state, "tenant_deletion_scheduler", None)
    billing_period_rollover_scheduler = getattr(
        app.state,
        "billing_period_rollover_scheduler",
        None,
    )
    billing_reconciliation_scheduler = getattr(
        app.state,
        "billing_reconciliation_scheduler",
        None,
    )
    accounts_workspace_auto_create_scheduler = getattr(
        app.state,
        "accounts_workspace_auto_create_scheduler",
        None,
    )
    multi_region_replication_probe_scheduler = getattr(
        app.state,
        "multi_region_replication_probe_scheduler",
        None,
    )
    multi_region_maintenance_window_scheduler = getattr(
        app.state,
        "multi_region_maintenance_window_scheduler",
        None,
    )
    multi_region_capacity_projection_scheduler = getattr(
        app.state,
        "multi_region_capacity_projection_scheduler",
        None,
    )
    robustness_orchestrator_scheduler = getattr(
        app.state,
        "robustness_orchestrator_scheduler",
        None,
    )
    if ibor_sync_scheduler is not None:
        try:
            ibor_sync_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["ibor_sync_scheduler"] = str(exc)
            LOGGER.warning("Failed to start IBOR sync scheduler: %s", exc)
    if memory_scheduler is not None:
        try:
            memory_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["memory_scheduler"] = str(exc)
            LOGGER.warning("Failed to start memory scheduler: %s", exc)
    if goal_auto_completion_scheduler is not None:
        try:
            goal_auto_completion_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["goal_auto_completion_scheduler"] = str(exc)
            LOGGER.warning("Failed to start goal auto-completion scheduler: %s", exc)
    if notifications_webhook_retry_scheduler is not None:
        try:
            notifications_webhook_retry_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["notifications_webhook_retry_scheduler"] = str(exc)
            LOGGER.warning("Failed to start notifications webhook retry scheduler: %s", exc)
    if notifications_retention_gc_scheduler is not None:
        try:
            notifications_retention_gc_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["notifications_retention_gc_scheduler"] = str(exc)
            LOGGER.warning("Failed to start notifications retention GC scheduler: %s", exc)
    if notifications_channel_verification_scheduler is not None:
        try:
            notifications_channel_verification_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["notifications_channel_verification_scheduler"] = str(exc)
            LOGGER.warning("Failed to start notifications verification scheduler: %s", exc)
    if notifications_deadletter_threshold_scheduler is not None:
        try:
            notifications_deadletter_threshold_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["notifications_deadletter_threshold_scheduler"] = str(exc)
            LOGGER.warning("Failed to start notifications DLQ threshold scheduler: %s", exc)
    if admin_security_expiry_scheduler is not None:
        try:
            admin_security_expiry_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["admin_security_expiry_scheduler"] = str(exc)
            LOGGER.warning("Failed to start admin security expiry scheduler: %s", exc)
    if governance_retention_gc_scheduler is not None:
        try:
            governance_retention_gc_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["governance_retention_gc_scheduler"] = str(exc)
            LOGGER.warning("Failed to start governance retention GC scheduler: %s", exc)
    if checkpoint_gc_scheduler is not None:
        try:
            checkpoint_gc_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["checkpoint_gc_scheduler"] = str(exc)
            LOGGER.warning("Failed to start checkpoint GC scheduler: %s", exc)
    if debug_logging_capture_gc_scheduler is not None:
        try:
            debug_logging_capture_gc_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["debug_logging_capture_gc_scheduler"] = str(exc)
            LOGGER.warning("Failed to start debug logging capture GC scheduler: %s", exc)
    if a2a_idle_timeout_scheduler is not None:
        try:
            a2a_idle_timeout_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["a2a_idle_timeout_scheduler"] = str(exc)
            LOGGER.warning("Failed to start A2A idle-timeout scheduler: %s", exc)
    if mcp_catalog_refresh_scheduler is not None:
        try:
            mcp_catalog_refresh_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["mcp_catalog_refresh_scheduler"] = str(exc)
            LOGGER.warning("Failed to start MCP catalog refresh scheduler: %s", exc)
    if model_catalog_auto_deprecation_scheduler is not None:
        try:
            model_catalog_auto_deprecation_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["model_catalog_auto_deprecation_scheduler"] = str(exc)
            LOGGER.warning("Failed to start model catalog auto-deprecation scheduler: %s", exc)
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
    for scheduler_name, scheduler in (
        ("security_rotation_scheduler", security_rotation_scheduler),
        ("security_overlap_expirer", security_overlap_expirer),
        ("security_pentest_overdue_scheduler", security_pentest_overdue_scheduler),
    ):
        if scheduler is None:
            continue
        try:
            scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors[scheduler_name] = str(exc)
            LOGGER.warning("Failed to start %s: %s", scheduler_name, exc)
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
    if cost_forecast_scheduler is not None:
        try:
            cost_forecast_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["cost_forecast_scheduler"] = str(exc)
            LOGGER.warning("Failed to start cost forecast scheduler: %s", exc)
    if cost_anomaly_scheduler is not None:
        try:
            cost_anomaly_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["cost_anomaly_scheduler"] = str(exc)
            LOGGER.warning("Failed to start cost anomaly scheduler: %s", exc)
    if billing_period_rollover_scheduler is not None:
        try:
            billing_period_rollover_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["billing_period_rollover_scheduler"] = str(exc)
            LOGGER.warning("Failed to start billing period rollover scheduler: %s", exc)
    if billing_reconciliation_scheduler is not None:
        try:
            billing_reconciliation_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["billing_reconciliation_scheduler"] = str(exc)
            LOGGER.warning("Failed to start billing reconciliation scheduler: %s", exc)
    if accounts_workspace_auto_create_scheduler is not None:
        try:
            accounts_workspace_auto_create_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["accounts_workspace_auto_create_scheduler"] = str(exc)
            LOGGER.warning("Failed to start accounts workspace auto-create scheduler: %s", exc)
    if incident_response_delivery_retry_scheduler is not None:
        try:
            incident_response_delivery_retry_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["incident_response_delivery_retry_scheduler"] = str(exc)
            LOGGER.warning("Failed to start incident response delivery retry scheduler: %s", exc)
    if incident_response_runbook_freshness_scheduler is not None:
        try:
            incident_response_runbook_freshness_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["incident_response_runbook_freshness_scheduler"] = str(exc)
            LOGGER.warning("Failed to start incident response runbook freshness scheduler: %s", exc)
    if tenant_deletion_scheduler is not None:
        try:
            tenant_deletion_scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors["tenant_deletion_scheduler"] = str(exc)
            LOGGER.warning("Failed to start tenant deletion scheduler: %s", exc)
    for scheduler_name, scheduler in (
        ("multi_region_replication_probe_scheduler", multi_region_replication_probe_scheduler),
        ("multi_region_maintenance_window_scheduler", multi_region_maintenance_window_scheduler),
        ("multi_region_capacity_projection_scheduler", multi_region_capacity_projection_scheduler),
    ):
        if scheduler is None:
            continue
        try:
            scheduler.start()
        except Exception as exc:
            app.state.degraded = True
            startup_errors[scheduler_name] = str(exc)
            LOGGER.warning("Failed to start %s: %s", scheduler_name, exc)
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
        if cost_anomaly_scheduler is not None:
            try:
                cost_anomaly_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop cost anomaly scheduler cleanly: %s", exc)
        if billing_period_rollover_scheduler is not None:
            try:
                billing_period_rollover_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning(
                    "Failed to stop billing period rollover scheduler cleanly: %s",
                    exc,
                )
        if billing_reconciliation_scheduler is not None:
            try:
                billing_reconciliation_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning(
                    "Failed to stop billing reconciliation scheduler cleanly: %s",
                    exc,
                )
        if accounts_workspace_auto_create_scheduler is not None:
            try:
                accounts_workspace_auto_create_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning(
                    "Failed to stop accounts workspace auto-create scheduler cleanly: %s",
                    exc,
                )
        reset_incident_trigger()
        if incident_response_delivery_retry_scheduler is not None:
            try:
                incident_response_delivery_retry_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning(
                    "Failed to stop incident response delivery retry scheduler cleanly: %s",
                    exc,
                )
        if incident_response_runbook_freshness_scheduler is not None:
            try:
                incident_response_runbook_freshness_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning(
                    "Failed to stop incident response runbook freshness scheduler cleanly: %s",
                    exc,
                )
        if tenant_deletion_scheduler is not None:
            try:
                tenant_deletion_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop tenant deletion scheduler cleanly: %s", exc)
        for scheduler_name, scheduler in (
            ("multi_region_replication_probe_scheduler", multi_region_replication_probe_scheduler),
            (
                "multi_region_maintenance_window_scheduler",
                multi_region_maintenance_window_scheduler,
            ),
            (
                "multi_region_capacity_projection_scheduler",
                multi_region_capacity_projection_scheduler,
            ),
        ):
            if scheduler is None:
                continue
            try:
                scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop %s cleanly: %s", scheduler_name, exc)
        if cost_forecast_scheduler is not None:
            try:
                cost_forecast_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop cost forecast scheduler cleanly: %s", exc)
        if simulation_prediction_scheduler is not None:
            try:
                simulation_prediction_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop simulation prediction scheduler cleanly: %s", exc)
        if checkpoint_gc_scheduler is not None:
            try:
                checkpoint_gc_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop checkpoint GC scheduler cleanly: %s", exc)
        if debug_logging_capture_gc_scheduler is not None:
            try:
                debug_logging_capture_gc_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning(
                    "Failed to stop debug logging capture GC scheduler cleanly: %s",
                    exc,
                )
        if a2a_idle_timeout_scheduler is not None:
            try:
                a2a_idle_timeout_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop A2A idle-timeout scheduler cleanly: %s", exc)
        if mcp_catalog_refresh_scheduler is not None:
            try:
                mcp_catalog_refresh_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop MCP catalog refresh scheduler cleanly: %s", exc)
        if model_catalog_auto_deprecation_scheduler is not None:
            try:
                model_catalog_auto_deprecation_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning(
                    "Failed to stop model catalog auto-deprecation scheduler cleanly: %s",
                    exc,
                )
        if ibor_sync_scheduler is not None:
            try:
                ibor_sync_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop IBOR sync scheduler cleanly: %s", exc)
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
        for scheduler_name, scheduler in (
            ("security_rotation_scheduler", security_rotation_scheduler),
            ("security_overlap_expirer", security_overlap_expirer),
            ("security_pentest_overdue_scheduler", security_pentest_overdue_scheduler),
        ):
            if scheduler is None:
                continue
            try:
                scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning("Failed to stop %s cleanly: %s", scheduler_name, exc)
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
        if goal_auto_completion_scheduler is not None:
            try:
                goal_auto_completion_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning(
                    "Failed to stop goal auto-completion scheduler cleanly: %s",
                    exc,
                )
        if notifications_webhook_retry_scheduler is not None:
            try:
                notifications_webhook_retry_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning(
                    "Failed to stop notifications webhook retry scheduler cleanly: %s",
                    exc,
                )
        if notifications_retention_gc_scheduler is not None:
            try:
                notifications_retention_gc_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning(
                    "Failed to stop notifications retention GC scheduler cleanly: %s",
                    exc,
                )
        if notifications_channel_verification_scheduler is not None:
            try:
                notifications_channel_verification_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning(
                    "Failed to stop notifications verification scheduler cleanly: %s",
                    exc,
                )
        if notifications_deadletter_threshold_scheduler is not None:
            try:
                notifications_deadletter_threshold_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning(
                    "Failed to stop notifications DLQ threshold scheduler cleanly: %s",
                    exc,
                )
        if admin_security_expiry_scheduler is not None:
            try:
                admin_security_expiry_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning(
                    "Failed to stop admin security expiry scheduler cleanly: %s",
                    exc,
                )
        if governance_retention_gc_scheduler is not None:
            try:
                governance_retention_gc_scheduler.shutdown(wait=False)
            except Exception as exc:
                LOGGER.warning(
                    "Failed to stop governance retention GC scheduler cleanly: %s",
                    exc,
                )
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
        if cost_clickhouse_repository is not None:
            try:
                await cost_clickhouse_repository.stop()
            except Exception as exc:
                LOGGER.warning("Failed to stop cost ClickHouse batch buffer cleanly: %s", exc)
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
    configure_logging(_service_name_for_profile(profile), "platform-control")

    database.configure_database(resolved)

    app = FastAPI(
        lifespan=_lifespan,
        title="musematic Control Plane API",
        version=_platform_release_version(),
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        contact={
            "name": "musematic platform",
            "email": "platform@musematic.ai",
        },
    )
    app.state.settings = resolved
    app.state.clients = _build_clients(resolved)
    app.state.secret_provider = _build_secret_provider(resolved)
    app.state.payment_provider = _build_payment_provider(resolved)
    app.state.status_last_good_path = os.environ.get("STATUS_LAST_GOOD_PATH")
    app.state.analytics_repository = AnalyticsRepository(
        cast(AsyncClickHouseClient, app.state.clients["clickhouse"])
    )
    app.state.cost_clickhouse_repository = ClickHouseCostRepository(
        cast(AsyncClickHouseClient, app.state.clients["clickhouse"]),
        resolved,
    )
    app.state.analytics_consumer = None
    app.state.analytics_budget_scheduler = None
    app.state.cost_forecast_scheduler = None
    app.state.cost_anomaly_scheduler = None
    app.state.registry_index_worker = None
    app.state.context_engineering_drift_scheduler = None
    app.state.memory_scheduler = None
    app.state.goal_auto_completion_scheduler = None
    app.state.notifications_webhook_retry_scheduler = None
    app.state.notifications_retention_gc_scheduler = None
    app.state.notifications_channel_verification_scheduler = None
    app.state.notifications_deadletter_threshold_scheduler = None
    app.state.admin_security_expiry_scheduler = None
    app.state.ibor_sync_scheduler = None
    app.state.refresh_ibor_sync_scheduler = None
    app.state.connectors_worker_scheduler = None
    app.state.workflow_execution_scheduler = None
    app.state.workflow_scheduler = None
    app.state.security_rotation_scheduler = None
    app.state.security_overlap_expirer = None
    app.state.security_pentest_overdue_scheduler = None
    app.state.marketplace_scheduler = None
    app.state.fleet_learning_scheduler = None
    app.state.agentops_lifecycle_scheduler = None
    app.state.agentops_drift_scheduler = None
    app.state.discovery_proximity_scheduler = None
    app.state.simulation_prediction_scheduler = None
    app.state.robustness_orchestrator_scheduler = None
    app.state.trust_certifier_scheduler = None
    app.state.governance_retention_gc_scheduler = None
    app.state.checkpoint_gc_scheduler = None
    app.state.debug_logging_capture_gc_scheduler = None
    app.state.a2a_idle_timeout_scheduler = None
    app.state.mcp_catalog_refresh_scheduler = None
    app.state.model_catalog_auto_deprecation_scheduler = None
    app.state.incident_response_delivery_retry_scheduler = None
    app.state.incident_response_runbook_freshness_scheduler = None
    app.state.tenant_deletion_scheduler = None
    app.state.billing_period_rollover_scheduler = None
    app.state.billing_reconciliation_scheduler = None
    app.state.accounts_workspace_auto_create_scheduler = None
    app.state.multi_region_replication_probe_scheduler = None
    app.state.multi_region_maintenance_window_scheduler = None
    app.state.multi_region_capacity_projection_scheduler = None
    if resolved.profile == "api":
        app.state.ibor_sync_scheduler = _build_ibor_sync_scheduler(app)
        app.state.refresh_ibor_sync_scheduler = lambda: _refresh_ibor_sync_scheduler(app)
    if resolved.profile in {"api", "worker"}:
        app.state.notifications_webhook_retry_scheduler = (
            _build_notifications_webhook_retry_scheduler(app)
        )
        app.state.notifications_retention_gc_scheduler = (
            _build_notifications_retention_gc_scheduler(app)
        )
        app.state.notifications_channel_verification_scheduler = (
            _build_notifications_channel_verification_scheduler(app)
        )
        app.state.notifications_deadletter_threshold_scheduler = (
            _build_notifications_deadletter_threshold_scheduler(app)
        )
    if resolved.profile in {"api", "scheduler"}:
        app.state.admin_security_expiry_scheduler = build_admin_security_expiry_scheduler(app)
    if resolved.profile == "worker":
        app.state.analytics_consumer = AnalyticsPipelineConsumer(
            settings=resolved,
            clickhouse_client=cast(AsyncClickHouseClient, app.state.clients["clickhouse"]),
            producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
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
        app.state.security_rotation_scheduler = _build_security_rotation_scheduler(app)
        app.state.security_overlap_expirer = _build_security_overlap_expirer(app)
        app.state.security_pentest_overdue_scheduler = _build_security_pentest_overdue_scheduler(
            app
        )
        app.state.marketplace_scheduler = _build_marketplace_scheduler(app)
        app.state.fleet_learning_scheduler = _build_fleet_learning_scheduler(app)
        app.state.goal_auto_completion_scheduler = _build_goal_auto_completion_scheduler(app)
        app.state.governance_retention_gc_scheduler = _build_governance_retention_gc_scheduler(app)
        app.state.checkpoint_gc_scheduler = _build_checkpoint_gc_scheduler(app)
        app.state.debug_logging_capture_gc_scheduler = _build_debug_logging_capture_gc_scheduler(
            app
        )
        app.state.a2a_idle_timeout_scheduler = _build_a2a_idle_timeout_scheduler(app)
        app.state.mcp_catalog_refresh_scheduler = _build_mcp_catalog_refresh_scheduler(app)
        app.state.model_catalog_auto_deprecation_scheduler = (
            _build_model_catalog_auto_deprecation_scheduler(app)
        )
        app.state.security_rotation_scheduler = _build_security_rotation_scheduler(app)
        app.state.security_overlap_expirer = _build_security_overlap_expirer(app)
        app.state.security_pentest_overdue_scheduler = _build_security_pentest_overdue_scheduler(
            app
        )
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
    if resolved.profile == "scheduler":
        app.state.goal_auto_completion_scheduler = _build_goal_auto_completion_scheduler(app)
        app.state.governance_retention_gc_scheduler = _build_governance_retention_gc_scheduler(app)
        app.state.checkpoint_gc_scheduler = _build_checkpoint_gc_scheduler(app)
        app.state.cost_forecast_scheduler = build_forecast_scheduler(app)
        app.state.cost_anomaly_scheduler = build_anomaly_scheduler(app)
        app.state.billing_period_rollover_scheduler = build_period_rollover_scheduler(app)
        app.state.billing_reconciliation_scheduler = build_billing_reconciliation_scheduler(app)
        app.state.accounts_workspace_auto_create_scheduler = build_workspace_auto_create_retry(app)
        app.state.incident_response_delivery_retry_scheduler = build_delivery_retry_scheduler(app)
        app.state.incident_response_runbook_freshness_scheduler = build_runbook_freshness_scheduler(
            app
        )
        app.state.tenant_deletion_scheduler = build_tenant_deletion_scheduler(app)
        app.state.multi_region_replication_probe_scheduler = build_replication_probe_scheduler(app)
        app.state.multi_region_maintenance_window_scheduler = build_maintenance_window_scheduler(
            app
        )
        app.state.multi_region_capacity_projection_scheduler = build_capacity_projection_scheduler(
            app
        )
        app.state.debug_logging_capture_gc_scheduler = _build_debug_logging_capture_gc_scheduler(
            app
        )
        app.state.a2a_idle_timeout_scheduler = _build_a2a_idle_timeout_scheduler(app)
        app.state.mcp_catalog_refresh_scheduler = _build_mcp_catalog_refresh_scheduler(app)
        app.state.model_catalog_auto_deprecation_scheduler = (
            _build_model_catalog_auto_deprecation_scheduler(app)
        )
    exception_handler = cast(
        Callable[[Request, Exception], Response | Awaitable[Response]],
        platform_exception_handler,
    )
    billing_exception_handler = cast(
        Callable[[Request, Exception], Response | Awaitable[Response]],
        billing_quota_exception_handler,
    )
    for error_type in (
        QuotaExceededError,
        ModelTierNotAllowedError,
        OverageCapExceededError,
        NoActiveSubscriptionError,
        SubscriptionSuspendedError,
        OverageRequiredError,
    ):
        app.add_exception_handler(error_type, billing_exception_handler)
    app.add_exception_handler(PlatformError, exception_handler)
    # Starlette executes middleware in reverse registration order. TenantResolverMiddleware
    # is added last so hostname tenant resolution runs before auth, maintenance, rate limits,
    # debug capture, API versioning, and correlation middleware.
    app.add_middleware(ApiVersioningMiddleware)
    app.add_middleware(DebugCaptureMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(MaintenanceGateMiddleware)
    app.add_middleware(AdminReadOnlyMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(CorrelationLoggingMiddleware)
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(
        TenantResolverMiddleware,
        settings=resolved,
        session_factory=database.AsyncSessionLocal,
        redis_client=cast(AsyncRedisClient | None, app.state.clients.get("redis")),
    )
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
        if resolved.profile in {"api", "worker"}:
            AttentionConsumer(
                settings=resolved,
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            ).register(consumer_manager)
            StateChangeConsumer(
                settings=resolved,
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            ).register(consumer_manager)
        if resolved.profile == "worker":
            ObserverSignalConsumer(
                settings=resolved,
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                registry_service=None,
            ).register(consumer_manager)
            VerdictConsumer(
                settings=resolved,
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                registry_service=None,
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
        if resolved.profile == "trust-certifier":
            build_surveillance_service(
                session=database.AsyncSessionLocal(),
                settings=resolved,
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            ).register(consumer_manager)
        if resolved.profile == "worker":
            # UPD-049 — fan out marketplace.source_updated to fork owners.
            # Defined at platform.marketplace.consumer; gated by the
            # MARKETPLACE_FORK_NOTIFY_SOURCE_OWNERS setting.
            MarketplaceFanoutConsumer(
                settings=resolved,
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
            ).register(consumer_manager)
            MeteringJob(
                settings=resolved,
                payment_provider=cast(
                    PaymentProvider | None,
                    getattr(app.state, "payment_provider", None),
                ),
            ).register(consumer_manager)
            ContractMonitorConsumer(
                settings=resolved,
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                session_factory=database.AsyncSessionLocal,
            ).register(consumer_manager)
            ComplianceEvidenceConsumer(
                settings=resolved,
                object_storage=app.state.clients.get("object_storage"),
            ).register(consumer_manager)
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

    @api_router.get("/protected", tags=["auth"])
    async def protected_endpoint(
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        return {"status": "ok", "user": current_user}

    if resolved.profile in {"api", "agentops", "composition", "discovery", "simulation"}:
        if resolved.feature_e2e_mode:
            app.include_router(e2e_contract_router)
        app.include_router(api_router)
        app.include_router(auth_router)
        app.include_router(oauth_router)
        app.include_router(a2a_gateway_router)
        app.include_router(mcp_router)
        app.include_router(model_catalog_router)
        app.include_router(debug_logging_router)
        app.include_router(accounts_router)
        app.include_router(setup_router)
        app.include_router(onboarding_router)
        app.include_router(workspaces_router)
        app.include_router(data_lifecycle_workspace_router)
        app.include_router(data_lifecycle_cancel_router)
        app.include_router(data_lifecycle_sub_processors_public_router)
        app.include_router(data_lifecycle_sub_processors_admin_router)
        app.include_router(data_lifecycle_tenant_admin_router)
        app.include_router(data_lifecycle_dpa_admin_router)
        app.include_router(data_lifecycle_dpa_me_router)
        app.include_router(admin_router)
        app.include_router(billing_admin_plans_router)
        app.include_router(billing_admin_subscriptions_router)
        app.include_router(billing_public_plans_router)
        app.include_router(billing_workspace_router)
        app.include_router(two_pa_router, prefix="/api/v1")
        app.include_router(analytics_router)
        app.include_router(cost_governance_router)
        app.include_router(registry_router)
        app.include_router(context_engineering_router)
        app.include_router(evaluations_router)
        app.include_router(memory_router)
        app.include_router(marketplace_router)
        app.include_router(interactions_router)
        app.include_router(notifications_router, prefix="/api/v1")
        app.include_router(me_router, prefix="/api/v1")
        app.include_router(tenants_router)
        app.include_router(tenants_platform_router)
        app.include_router(workspaces_platform_router)
        app.include_router(notifications_webhooks_router, prefix="/api/v1")
        app.include_router(notifications_deadletter_router, prefix="/api/v1")
        app.include_router(governance_router, prefix="/api/v1")
        app.include_router(connectors_router)
        app.include_router(policies_router)
        app.include_router(testing_router)
        if resolved.feature_e2e_mode:
            app.include_router(testing_e2e_router)
        app.include_router(workflows_router)
        app.include_router(execution_router)
        app.include_router(execution_reprioritization_router)
        app.include_router(execution_runtime_router)
        app.include_router(trust_router, prefix="/api/v1/trust")
        app.include_router(fleets_router)
        app.include_router(fleet_learning_router)
        app.include_router(agentops_router)
        app.include_router(composition_router)
        app.include_router(discovery_router)
        app.include_router(simulation_router)
        app.include_router(privacy_router)
        app.include_router(privacy_self_service_router)
        app.include_router(audit_router)
        app.include_router(security_compliance_router)
        app.include_router(incident_response_router)
        app.include_router(status_page_router)
        app.include_router(status_page_me_router)
        app.include_router(multi_region_ops_router)
        app.include_router(localization_router)
        app.include_router(tagging_tags_router)
        app.include_router(tagging_labels_router)
        app.include_router(tagging_saved_views_router)
        app.include_router(tagging_admin_labels_router)

    _register_deprecated_routes(app)
    _install_openapi_factory(app)

    setup_telemetry(
        service_name=f"{resolved.otel.service_name}-{resolved.profile}",
        exporter_endpoint=resolved.otel.exporter_endpoint,
        app=app,
        engine=database.engine,
    )
    return app


def _build_secret_provider(settings: PlatformSettings) -> SecretProvider:
    if settings.vault.mode == "vault":
        return VaultSecretProvider(settings.vault)
    if settings.vault.mode == "kubernetes":
        return KubernetesSecretProvider(settings.vault)
    return MockSecretProvider(settings)


def _build_security_rotation_service(app: FastAPI, session: Any) -> Any:
    from platform.audit.dependencies import build_audit_chain_service
    from platform.security_compliance.providers.rotatable_secret_provider import (
        RotatableSecretProvider,
    )
    from platform.security_compliance.repository import SecurityComplianceRepository
    from platform.security_compliance.services.secret_rotation_service import (
        SecretRotationService,
    )

    settings = cast(PlatformSettings, app.state.settings)
    return SecretRotationService(
        SecurityComplianceRepository(session),
        RotatableSecretProvider(
            settings,
            cast(AsyncRedisClient | None, app.state.clients.get("redis")),
            cast(
                SecretProvider,
                getattr(app.state, "secret_provider", None)
                or MockSecretProvider(settings, validate_paths=False),
            ),
        ),
        producer=cast(EventProducer | None, app.state.clients.get("kafka")),
        audit_chain=build_audit_chain_service(
            session,
            settings,
            cast(EventProducer | None, app.state.clients.get("kafka")),
        ),
    )


def _build_security_pentest_service(app: FastAPI, session: Any) -> Any:
    from platform.audit.dependencies import build_audit_chain_service
    from platform.security_compliance.repository import SecurityComplianceRepository
    from platform.security_compliance.services.pentest_service import PentestService

    settings = cast(PlatformSettings, app.state.settings)
    return PentestService(
        SecurityComplianceRepository(session),
        producer=cast(EventProducer | None, app.state.clients.get("kafka")),
        audit_chain=build_audit_chain_service(
            session,
            settings,
            cast(EventProducer | None, app.state.clients.get("kafka")),
        ),
    )


def _build_security_rotation_scheduler(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except ImportError:
        return None
    from platform.security_compliance.workers.rotation_scheduler import run_due_rotations

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run_due_rotations() -> None:
        async with database.AsyncSessionLocal() as session:
            try:
                service = _build_security_rotation_service(app, session)
                await run_due_rotations(service)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Security rotation scheduler failed")

    scheduler.add_job(
        _run_due_rotations,
        "interval",
        seconds=app.state.settings.security_compliance.rotation_scheduler_interval_seconds,
        id="security-compliance-rotation-scheduler",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler


def _build_security_overlap_expirer(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except ImportError:
        return None
    from platform.security_compliance.workers.overlap_expirer import run_overlap_expiry

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run_overlap_expiry() -> None:
        async with database.AsyncSessionLocal() as session:
            try:
                service = _build_security_rotation_service(app, session)
                await run_overlap_expiry(service)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Security rotation overlap expirer failed")

    scheduler.add_job(
        _run_overlap_expiry,
        "interval",
        seconds=30,
        id="security-compliance-overlap-expirer",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler


def _build_security_pentest_overdue_scheduler(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
        trigger_module = __import__("apscheduler.triggers.cron", fromlist=["CronTrigger"])
    except ImportError:
        return None
    from platform.security_compliance.workers.pentest_overdue_scanner import (
        run_pentest_overdue_scan,
    )

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")
    trigger = trigger_module.CronTrigger.from_crontab(
        app.state.settings.security_compliance.pentest_overdue_scan_cron,
        timezone="UTC",
    )

    async def _run_overdue_scan() -> None:
        async with database.AsyncSessionLocal() as session:
            try:
                service = _build_security_pentest_service(app, session)
                await run_pentest_overdue_scan(service)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Security pentest overdue scanner failed")

    scheduler.add_job(
        _run_overdue_scan,
        trigger=trigger,
        id="security-compliance-pentest-overdue",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler


async def _refresh_ibor_sync_scheduler(app: FastAPI) -> None:
    scheduler = getattr(app.state, "ibor_sync_scheduler", None)
    if scheduler is None:
        return

    for job in scheduler.get_jobs():
        job_id = str(getattr(job, "id", ""))
        if job_id.startswith("ibor-sync-"):
            scheduler.remove_job(job.id)

    async with database.AsyncSessionLocal() as session:
        connectors = await AuthRepository(session).list_enabled_connectors()

    for connector in connectors:
        scheduler.add_job(
            _build_ibor_sync_job(app, connector.id),
            "interval",
            seconds=connector.cadence_seconds,
            id=f"ibor-sync-{connector.id}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )


def _build_ibor_sync_job(app: FastAPI, connector_id: UUID) -> Callable[[], Awaitable[None]]:
    async def _run() -> None:
        async with database.AsyncSessionLocal() as session:
            service = IBORSyncService(
                repository=AuthRepository(session),
                accounts_repository=AccountsRepository(session),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                session_factory=database.AsyncSessionLocal,
            )
            try:
                await service.run_sync(connector_id, triggered_by=None)
                await session.commit()
            except Exception as exc:
                await session.rollback()
                LOGGER.warning("IBOR sync job failed for connector %s: %s", connector_id, exc)

    return _run


def _build_ibor_sync_scheduler(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except ModuleNotFoundError:
        return None

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _load_jobs() -> None:
        await _refresh_ibor_sync_scheduler(app)

    scheduler.add_job(_load_jobs, "date", id="ibor-sync-loader")
    return scheduler


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


async def _run_notifications_webhook_retry_scan(app: FastAPI) -> None:
    async with database.AsyncSessionLocal() as session:
        workspaces_service = build_workspaces_service(
            session=session,
            settings=cast(PlatformSettings, app.state.settings),
            producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            accounts_service=None,
        )
        service = build_notifications_service(
            session=session,
            settings=cast(PlatformSettings, app.state.settings),
            redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
            producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            workspaces_service=workspaces_service,
            secret_provider=getattr(app.state, "secret_provider", InMemorySecretProvider()),
        )
        try:
            await service.run_webhook_retry_scan()
            await run_workspace_webhook_retry_scan(
                repo=NotificationsRepository(session),
                redis=cast(AsyncRedisClient, app.state.clients["redis"]),
                secrets=getattr(app.state, "secret_provider", InMemorySecretProvider()),
                deliverer=WebhookDeliverer(),
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _run_notifications_retention_gc(app: FastAPI) -> None:
    async with database.AsyncSessionLocal() as session:
        service = build_notifications_service(
            session=session,
            settings=cast(PlatformSettings, app.state.settings),
            redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
            producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            workspaces_service=None,
            secret_provider=getattr(app.state, "secret_provider", InMemorySecretProvider()),
        )
        try:
            await service.run_retention_gc()
            await service.run_dead_letter_retention_gc()
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _run_notifications_channel_verification(app: FastAPI) -> None:
    async with database.AsyncSessionLocal() as session:
        try:
            await expire_unverified_channels(
                NotificationsRepository(session),
                cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _run_notifications_deadletter_threshold_scan(app: FastAPI) -> None:
    async with database.AsyncSessionLocal() as session:
        try:
            await run_dead_letter_threshold_scan(
                repo=NotificationsRepository(session),
                redis=cast(AsyncRedisClient, app.state.clients["redis"]),
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _build_notifications_webhook_retry_scheduler(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run() -> None:
        await _run_notifications_webhook_retry_scan(app)

    scheduler.add_job(
        _run,
        "interval",
        seconds=app.state.settings.notifications.retry_scan_interval_seconds,
        id="notifications-webhook-retry",
    )
    return scheduler


def _build_notifications_retention_gc_scheduler(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run() -> None:
        await _run_notifications_retention_gc(app)

    scheduler.add_job(
        _run,
        "interval",
        hours=app.state.settings.notifications.gc_interval_hours,
        id="notifications-retention-gc",
    )
    return scheduler


def _build_notifications_channel_verification_scheduler(app: FastAPI) -> Any | None:
    async def _run() -> None:
        await _run_notifications_channel_verification(app)

    return build_channel_verification_scheduler(_run)


def _build_notifications_deadletter_threshold_scheduler(app: FastAPI) -> Any | None:
    async def _run() -> None:
        await _run_notifications_deadletter_threshold_scan(app)

    return build_dead_letter_threshold_scheduler(_run)


async def _run_governance_retention_gc(app: FastAPI) -> None:
    async with database.AsyncSessionLocal() as session:
        repository = GovernanceRepository(session)
        try:
            await repository.delete_expired_verdicts(app.state.settings.governance.retention_days)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _build_governance_retention_gc_scheduler(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run() -> None:
        await _run_governance_retention_gc(app)

    scheduler.add_job(
        _run,
        "interval",
        hours=app.state.settings.governance.gc_interval_hours,
        id="governance-retention-gc",
    )
    return scheduler


async def _run_checkpoint_gc(app: FastAPI) -> None:
    async with database.AsyncSessionLocal() as session:
        checkpoint_service = build_checkpoint_service(
            session=session,
            settings=cast(PlatformSettings, app.state.settings),
            producer=cast(EventProducer | None, app.state.clients.get("kafka")),
        )
        try:
            await checkpoint_service.gc_expired(app.state.settings.checkpoint_retention_days)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _build_checkpoint_gc_scheduler(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run() -> None:
        await _run_checkpoint_gc(app)

    scheduler.add_job(
        _run,
        "interval",
        hours=24,
        id="execution-checkpoint-gc",
    )
    return scheduler


async def _run_debug_logging_capture_gc(app: FastAPI) -> None:
    await purge_debug_captures(
        session_factory=database.AsyncSessionLocal,
        redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
        settings=cast(PlatformSettings, app.state.settings),
        producer=cast(EventProducer | None, app.state.clients.get("kafka")),
    )


def _build_debug_logging_capture_gc_scheduler(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run() -> None:
        await _run_debug_logging_capture_gc(app)

    scheduler.add_job(
        _run,
        "cron",
        hour=2,
        minute=0,
        id="debug-logging-capture-gc",
    )
    return scheduler


async def _run_a2a_idle_timeout_scan(app: FastAPI) -> None:
    async with database.AsyncSessionLocal() as session:
        repository = A2AGatewayRepository(session)
        publisher = A2AEventPublisher(cast(EventProducer | None, app.state.clients.get("kafka")))
        try:
            tasks = await repository.list_tasks_idle_expired()
            for task in tasks:
                await repository.update_task_state(
                    task,
                    a2a_state=A2ATaskState.cancelled,
                    error_code="idle_timeout",
                    error_message="Task was cancelled after waiting for follow-up input.",
                    idle_timeout_at=None,
                )
                audit = await repository.create_audit_record(
                    A2AAuditRecord(
                        task_id=task.id,
                        direction=task.direction,
                        principal_id=task.principal_id,
                        agent_fqn=task.agent_fqn,
                        action="task_cancelled",
                        result="success",
                        workspace_id=task.workspace_id,
                        error_code="idle_timeout",
                    )
                )
                await repository.update_task_state(task, last_event_id=str(audit.id))
                await publisher.publish(
                    event_type=A2AEventType.task_cancelled,
                    key=task.task_id,
                    payload=A2AEventPayload(
                        task_id=task.task_id,
                        workspace_id=task.workspace_id,
                        principal_id=task.principal_id,
                        agent_fqn=task.agent_fqn,
                        state=task.a2a_state.value,
                        direction=task.direction.value,
                        details={
                            "action": "task_cancelled",
                            "error_code": "idle_timeout",
                        },
                    ),
                    correlation_ctx=CorrelationContext(
                        workspace_id=task.workspace_id,
                        conversation_id=task.conversation_id,
                        interaction_id=task.interaction_id,
                        agent_fqn=task.agent_fqn,
                        correlation_id=uuid4(),
                    ),
                )
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _build_a2a_idle_timeout_scheduler(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run() -> None:
        await _run_a2a_idle_timeout_scan(app)

    scheduler.add_job(
        _run,
        "interval",
        minutes=5,
        id="a2a-idle-timeout-scan",
    )
    return scheduler


def _build_mcp_catalog_refresh_scheduler(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run() -> None:
        from platform.mcp.dependencies import build_mcp_service, build_mcp_tool_registry
        from platform.policies.dependencies import build_tool_gateway_service

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
                object_storage=cast(
                    AsyncObjectStorageClient,
                    app.state.clients["object_storage"],
                ),
                opensearch=cast(AsyncOpenSearchClient, app.state.clients["opensearch"]),
                qdrant=cast(AsyncQdrantClient, app.state.clients["qdrant"]),
                workspaces_service=workspaces_service,
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            tool_gateway = build_tool_gateway_service(
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
            service = build_mcp_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
            )
            build_mcp_tool_registry(
                mcp_service=service,
                settings=cast(PlatformSettings, app.state.settings),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                tool_gateway=tool_gateway,
            )
            try:
                await service.refresh_due_catalogs()
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("MCP catalog refresh scheduler failed")

    scheduler.add_job(
        _run,
        "interval",
        seconds=60,
        id="mcp-catalog-refresh",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler


def _build_model_catalog_auto_deprecation_scheduler(app: FastAPI) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None
    from platform.audit.dependencies import build_audit_chain_service
    from platform.model_catalog.repository import ModelCatalogRepository
    from platform.model_catalog.workers.auto_deprecation_scanner import (
        run_auto_deprecation_scan,
    )
    from platform.security_compliance.repository import SecurityComplianceRepository
    from platform.security_compliance.services.compliance_service import ComplianceService

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run() -> None:
        async with database.AsyncSessionLocal() as session:
            settings = cast(PlatformSettings, app.state.settings)
            producer = cast(EventProducer | None, app.state.clients.get("kafka"))
            try:
                compliance = ComplianceService(
                    SecurityComplianceRepository(session),
                    settings,
                    object_storage=cast(
                        AsyncObjectStorageClient | None,
                        app.state.clients.get("object_storage"),
                    ),
                    audit_chain=build_audit_chain_service(session, settings, producer),
                )
                await run_auto_deprecation_scan(
                    repository=ModelCatalogRepository(session),
                    producer=producer,
                    audit_chain=build_audit_chain_service(session, settings, producer),
                    compliance_service=compliance,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Model catalog auto-deprecation scheduler failed")

    scheduler.add_job(
        _run,
        "interval",
        seconds=app.state.settings.model_catalog.auto_deprecation_interval_seconds,
        id="model-catalog-auto-deprecation",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler


def _build_goal_auto_completion_scheduler(app: FastAPI) -> Any | None:
    if not app.state.settings.FEATURE_GOAL_AUTO_COMPLETE:
        return None
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None

    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run_goal_auto_completion() -> None:
        async with database.AsyncSessionLocal() as session:
            try:
                scanner = GoalAutoCompletionScanner(
                    producer=cast(EventProducer | None, app.state.clients.get("kafka"))
                )
                await scanner.scan_and_complete_idle_goals(session)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    scheduler.add_job(
        _run_goal_auto_completion,
        "interval",
        seconds=app.state.settings.interactions.goal_auto_complete_scan_interval_seconds,
        id="goal-auto-completion",
    )
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

    async def _build_context_engineering_runtime(session: Any) -> Any:
        workspaces_service = build_workspaces_service(
            session=session,
            settings=cast(PlatformSettings, app.state.settings),
            producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            accounts_service=None,
        )
        registry_service = build_registry_service(
            session=session,
            settings=cast(PlatformSettings, app.state.settings),
            object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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
            qdrant=cast(AsyncQdrantClient | None, app.state.clients.get("qdrant")),
            workspaces_service=workspaces_service,
            registry_service=registry_service,
        )
        return build_context_engineering_service(
            session=session,
            settings=cast(PlatformSettings, app.state.settings),
            clickhouse_client=cast(AsyncClickHouseClient, app.state.clients["clickhouse"]),
            object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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

    async def _run_drift_analysis() -> None:
        async with database.AsyncSessionLocal() as session:
            service = await _build_context_engineering_runtime(session)
            await DriftMonitorTask(service).run()

    async def _run_correlation_recompute() -> None:
        async with database.AsyncSessionLocal() as session:
            service = await _build_context_engineering_runtime(session)
            await service.run_correlation_recompute()
            await session.commit()

    scheduler.add_job(
        _run_drift_analysis,
        trigger,
        id="context-engineering-drift-analysis",
    )
    scheduler.add_job(
        _run_correlation_recompute,
        "interval",
        hours=app.state.settings.context_engineering.correlation_recompute_interval_hours,
        id="context-engineering-correlation-recompute",
        replace_existing=True,
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

    async def _run_workspace_proximity_recompute() -> None:
        async with database.AsyncSessionLocal() as session:
            service = build_discovery_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
                redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
                qdrant=cast(AsyncQdrantClient | None, app.state.clients.get("qdrant")),
                neo4j=cast(AsyncNeo4jClient | None, app.state.clients.get("neo4j")),
                sandbox_client=cast(
                    SandboxManagerClient | None,
                    app.state.clients.get("sandbox_manager"),
                ),
            )
            try:
                await service.workspace_proximity_recompute_task()
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Discovery proximity scheduler failed")

    scheduler.add_job(
        _run_workspace_proximity_recompute,
        "interval",
        minutes=app.state.settings.discovery.proximity_graph_recompute_interval_minutes,
        id="discovery-proximity-clustering",
        replace_existing=True,
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
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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
            runtime_payload = _workflow_runtime_event_payload(dict(payload))
            try:
                await service.record_runtime_event(
                    UUID(str(execution_id)),
                    step_id=runtime_payload.get("step_id"),
                    event_type=event_enum,
                    payload=runtime_payload,
                    status=status_map.get(event_enum.value),
                )
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Workflow runtime consumer failed")

    return _handle


def _workflow_runtime_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    if "fallback_taken" in normalized:
        normalized["fallback_taken"] = _jsonable_runtime_value(normalized["fallback_taken"])
        return normalized

    router_response = normalized.get("model_router_response")
    fallback_taken: Any | None = None
    if isinstance(router_response, dict):
        fallback_taken = router_response.get("fallback_taken")
    elif router_response is not None:
        fallback_taken = getattr(router_response, "fallback_taken", None)

    if fallback_taken is not None:
        normalized["fallback_taken"] = _jsonable_runtime_value(fallback_taken)
    return normalized


def _jsonable_runtime_value(value: Any) -> Any:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _jsonable_runtime_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable_runtime_value(item) for item in value]
    return value


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
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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
                registry_service=None,
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

    async def _run_ttl_scanner() -> None:
        await _run_handler("ttl_scanner_task")

    async def _run_orphan_scanner() -> None:
        await _run_handler("orphan_scanner_task")

    async def _run_outcome_measurer() -> None:
        await _run_handler("outcome_measurer_task")

    async def _run_signal_poll() -> None:
        await _run_handler("signal_poll_task")

    async def _run_proficiency_recompute() -> None:
        await _run_handler("proficiency_recomputer_task")

    async def _run_snapshot_retention_gc() -> None:
        await _run_handler("snapshot_retention_gc_task")

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
    scheduler.add_job(
        _run_ttl_scanner,
        "interval",
        hours=1,
        id="agentops-adaptation-ttl",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_orphan_scanner,
        "interval",
        hours=1,
        id="agentops-adaptation-orphan",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_outcome_measurer,
        "interval",
        hours=1,
        id="agentops-adaptation-outcome",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_signal_poll,
        "interval",
        minutes=app.state.settings.agentops.adaptation_signal_poll_interval_minutes,
        id="agentops-adaptation-signal-poll",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_proficiency_recompute,
        "interval",
        hours=24,
        id="agentops-proficiency-recompute",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_snapshot_retention_gc,
        "interval",
        hours=24,
        id="agentops-snapshot-retention-gc",
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
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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
            object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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

    async def _run_surveillance_cycle() -> None:
        async with database.AsyncSessionLocal() as session:
            service = build_surveillance_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            try:
                await service.run_surveillance_cycle()
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Trust surveillance cycle failed")

    async def _run_grace_period_check() -> None:
        async with database.AsyncSessionLocal() as session:
            service = build_surveillance_service(
                session=session,
                settings=cast(PlatformSettings, app.state.settings),
                producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            )
            try:
                await service.check_grace_period_expiry()
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Trust grace period expiry scan failed")

    scheduler.add_job(_run_expire_stale, "interval", hours=1, id="trust-expire-stale")
    scheduler.add_job(
        _run_surveillance_cycle,
        "interval",
        hours=1,
        id="trust-surveillance-cycle",
    )
    scheduler.add_job(
        _run_grace_period_check,
        "interval",
        hours=1,
        id="trust-grace-period-check",
    )
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
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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
                object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
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
