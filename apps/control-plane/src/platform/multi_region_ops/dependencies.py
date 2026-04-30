from __future__ import annotations

from platform.analytics.dependencies import get_analytics_service
from platform.analytics.service import AnalyticsService
from platform.audit.dependencies import get_audit_chain_service
from platform.audit.service import AuditChainService
from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.clients.model_router import SecretProvider
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.common.secret_provider import MockSecretProvider as CanonicalMockSecretProvider
from platform.common.secret_provider import SecretProvider as CanonicalSecretProvider
from platform.cost_governance.dependencies import build_cost_governance_service
from platform.incident_response.dependencies import get_incident_service
from platform.incident_response.services.incident_service import IncidentService
from platform.incident_response.trigger_interface import (
    IncidentTriggerInterface,
)
from platform.incident_response.trigger_interface import (
    get_incident_trigger as get_registered_incident_trigger,
)
from platform.multi_region_ops.repository import MultiRegionOpsRepository
from platform.multi_region_ops.service import MultiRegionOpsService
from platform.multi_region_ops.services.capacity_service import CapacityService
from platform.multi_region_ops.services.failover_service import FailoverService
from platform.multi_region_ops.services.maintenance_mode_service import MaintenanceModeService
from platform.multi_region_ops.services.probes.base import ReplicationProbeRegistry
from platform.multi_region_ops.services.probes.clickhouse import ClickHouseReplicationProbe
from platform.multi_region_ops.services.probes.kafka import KafkaReplicationProbe
from platform.multi_region_ops.services.probes.neo4j import Neo4jReplicationProbe
from platform.multi_region_ops.services.probes.opensearch import OpenSearchReplicationProbe
from platform.multi_region_ops.services.probes.postgres import PostgresReplicationProbe
from platform.multi_region_ops.services.probes.qdrant import QdrantReplicationProbe
from platform.multi_region_ops.services.probes.s3 import S3ReplicationProbe
from platform.multi_region_ops.services.region_service import RegionService
from platform.multi_region_ops.services.replication_monitor import ReplicationMonitor
from platform.security_compliance.providers.rotatable_secret_provider import RotatableSecretProvider
from platform.workspaces.dependencies import get_workspaces_service
from platform.workspaces.service import WorkspacesService
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _get_redis(request: Request) -> AsyncRedisClient | None:
    return cast(AsyncRedisClient | None, request.app.state.clients.get("redis"))


def _get_clickhouse(request: Request) -> AsyncClickHouseClient | None:
    return cast(AsyncClickHouseClient | None, request.app.state.clients.get("clickhouse"))


def get_secret_provider(request: Request) -> SecretProvider:
    existing = getattr(request.app.state, "multi_region_ops_secret_provider", None)
    if existing is not None:
        return cast(SecretProvider, existing)
    provider = RotatableSecretProvider(
        settings=_get_settings(request),
        redis_client=_get_redis(request),
        secret_provider=cast(
            CanonicalSecretProvider,
            getattr(request.app.state, "secret_provider", None)
            or CanonicalMockSecretProvider(_get_settings(request), validate_paths=False),
        ),
    )
    request.app.state.multi_region_ops_secret_provider = provider
    return provider


def get_redis_failover_lock(request: Request) -> AsyncRedisClient | None:
    return _get_redis(request)


def get_redis_active_window_cache(request: Request) -> AsyncRedisClient | None:
    return _get_redis(request)


def get_replication_probe_registry(
    request: Request,
    secret_provider: SecretProvider = Depends(get_secret_provider),
) -> ReplicationProbeRegistry:
    existing = getattr(request.app.state, "multi_region_ops_probe_registry", None)
    if isinstance(existing, ReplicationProbeRegistry):
        return existing
    settings = _get_settings(request)
    registry = ReplicationProbeRegistry()
    registry.register(PostgresReplicationProbe(secret_provider))
    registry.register(
        KafkaReplicationProbe(
            secret_provider,
            timeout_seconds=settings.multi_region_ops.replication_probe_request_timeout_seconds,
        )
    )
    registry.register(S3ReplicationProbe(secret_provider))
    registry.register(ClickHouseReplicationProbe(_get_clickhouse(request)))
    registry.register(
        QdrantReplicationProbe(
            secret_provider,
            timeout_seconds=settings.multi_region_ops.replication_probe_request_timeout_seconds,
        )
    )
    registry.register(Neo4jReplicationProbe(secret_provider))
    registry.register(
        OpenSearchReplicationProbe(
            secret_provider,
            timeout_seconds=settings.multi_region_ops.replication_probe_request_timeout_seconds,
        )
    )
    request.app.state.multi_region_ops_probe_registry = registry
    return registry


async def get_region_service(
    session: AsyncSession = Depends(get_db),
    audit_chain_service: AuditChainService = Depends(get_audit_chain_service),
) -> RegionService:
    return RegionService(
        repository=MultiRegionOpsRepository(session),
        audit_chain_service=audit_chain_service,
    )


async def get_incident_trigger() -> IncidentTriggerInterface:
    return get_registered_incident_trigger()


async def get_replication_monitor(
    request: Request,
    session: AsyncSession = Depends(get_db),
    probe_registry: ReplicationProbeRegistry = Depends(get_replication_probe_registry),
    incident_trigger: IncidentTriggerInterface = Depends(get_incident_trigger),
    incident_service: IncidentService = Depends(get_incident_service),
) -> ReplicationMonitor:
    return ReplicationMonitor(
        repository=MultiRegionOpsRepository(session),
        settings=_get_settings(request),
        probe_registry=probe_registry,
        incident_trigger=incident_trigger,
        producer=_get_producer(request),
        incident_service=incident_service,
    )


async def get_failover_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    audit_chain_service: AuditChainService = Depends(get_audit_chain_service),
) -> FailoverService:
    return FailoverService(
        repository=MultiRegionOpsRepository(session),
        settings=_get_settings(request),
        redis_client=_get_redis(request),
        producer=_get_producer(request),
        audit_chain_service=audit_chain_service,
    )


async def get_maintenance_mode_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    incident_trigger: IncidentTriggerInterface = Depends(get_incident_trigger),
    audit_chain_service: AuditChainService = Depends(get_audit_chain_service),
) -> MaintenanceModeService:
    return MaintenanceModeService(
        repository=MultiRegionOpsRepository(session),
        settings=_get_settings(request),
        redis_client=_get_redis(request),
        producer=_get_producer(request),
        incident_trigger=incident_trigger,
        audit_chain_service=audit_chain_service,
    )


async def get_capacity_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    incident_trigger: IncidentTriggerInterface = Depends(get_incident_trigger),
    incident_service: IncidentService = Depends(get_incident_service),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> CapacityService:
    settings = _get_settings(request)
    cost_governance = build_cost_governance_service(
        session=session,
        settings=settings,
        producer=_get_producer(request),
        redis_client=_get_redis(request),
        clickhouse_repository=getattr(request.app.state, "cost_clickhouse_repository", None),
        workspaces_service=workspaces_service,
    )
    return CapacityService(
        settings=settings,
        cost_governance_service=cost_governance,
        analytics_service=analytics_service,
        incident_trigger=incident_trigger,
        incident_service=incident_service,
    )


async def get_multi_region_ops_service(
    region_service: RegionService = Depends(get_region_service),
    replication_monitor: ReplicationMonitor = Depends(get_replication_monitor),
    failover_service: FailoverService = Depends(get_failover_service),
    maintenance_mode_service: MaintenanceModeService = Depends(get_maintenance_mode_service),
    capacity_service: CapacityService = Depends(get_capacity_service),
) -> MultiRegionOpsService:
    return MultiRegionOpsService(
        region_service=region_service,
        replication_monitor=replication_monitor,
        failover_service=failover_service,
        maintenance_mode_service=maintenance_mode_service,
        capacity_service=capacity_service,
    )
