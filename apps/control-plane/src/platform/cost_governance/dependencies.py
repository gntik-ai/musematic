from __future__ import annotations

from platform.audit.dependencies import get_audit_chain_service
from platform.audit.service import AuditChainService
from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.cost_governance.clickhouse_repository import ClickHouseCostRepository
from platform.cost_governance.repository import CostGovernanceRepository
from platform.cost_governance.service import CostGovernanceService
from platform.cost_governance.services.anomaly_service import AnomalyService
from platform.cost_governance.services.attribution_service import AttributionService
from platform.cost_governance.services.budget_service import BudgetService
from platform.cost_governance.services.chargeback_service import ChargebackService
from platform.cost_governance.services.forecast_service import ForecastService
from platform.model_catalog.dependencies import get_catalog_service
from platform.model_catalog.services.catalog_service import CatalogService
from platform.notifications.dependencies import get_notifications_service
from platform.notifications.service import AlertService
from platform.workspaces.dependencies import get_workspaces_service
from platform.workspaces.service import WorkspacesService
from typing import Any, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def get_redis_cost_client(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


def get_clickhouse_cost_repository(request: Request) -> ClickHouseCostRepository | None:
    existing = getattr(request.app.state, "cost_clickhouse_repository", None)
    if isinstance(existing, ClickHouseCostRepository):
        return existing
    clickhouse = request.app.state.clients.get("clickhouse")
    if not isinstance(clickhouse, AsyncClickHouseClient):
        return None
    repository = ClickHouseCostRepository(clickhouse, _get_settings(request))
    request.app.state.cost_clickhouse_repository = repository
    return repository


def build_budget_service(
    *,
    repository: CostGovernanceRepository,
    redis_client: AsyncRedisClient | None,
    settings: PlatformSettings,
    producer: EventProducer | None,
    audit_chain_service: AuditChainService | None,
    alert_service: Any | None,
    workspaces_service: WorkspacesService | None,
) -> BudgetService:
    return BudgetService(
        repository=repository,
        redis_client=redis_client,
        settings=settings,
        kafka_producer=producer,
        audit_chain_service=audit_chain_service,
        alert_service=alert_service,
        workspaces_service=workspaces_service,
    )


def build_cost_governance_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    redis_client: AsyncRedisClient | None,
    clickhouse_repository: ClickHouseCostRepository | None,
    audit_chain_service: AuditChainService | None = None,
    alert_service: Any | None = None,
    workspaces_service: WorkspacesService | None = None,
    model_catalog_service: CatalogService | None = None,
) -> CostGovernanceService:
    repository = CostGovernanceRepository(session)
    budget_service = build_budget_service(
        repository=repository,
        redis_client=redis_client,
        settings=settings,
        producer=producer,
        audit_chain_service=audit_chain_service,
        alert_service=alert_service,
        workspaces_service=workspaces_service,
    )
    attribution_service = AttributionService(
        repository=repository,
        settings=settings,
        clickhouse_repository=clickhouse_repository,
        kafka_producer=producer,
        model_catalog_service=model_catalog_service,
        budget_service=budget_service,
        fail_open=settings.cost_governance.attribution_fail_open,
    )
    chargeback_service = ChargebackService(
        repository=repository,
        clickhouse_repository=clickhouse_repository,
        workspaces_service=workspaces_service,
        audit_chain_service=audit_chain_service,
        default_currency=settings.cost_governance.default_currency,
    )
    forecast_service = ForecastService(
        repository=repository,
        clickhouse_repository=clickhouse_repository,
        minimum_history_periods=settings.cost_governance.minimum_history_periods_for_forecast,
        default_currency=settings.cost_governance.default_currency,
        kafka_producer=producer,
    )
    anomaly_service = AnomalyService(
        repository=repository,
        clickhouse_repository=clickhouse_repository,
        kafka_producer=producer,
        audit_chain_service=audit_chain_service,
        alert_service=alert_service,
    )
    return CostGovernanceService(
        attribution_service=attribution_service,
        chargeback_service=chargeback_service,
        budget_service=budget_service,
        forecast_service=forecast_service,
        anomaly_service=anomaly_service,
        repository=repository,
    )


async def get_budget_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    redis_client: AsyncRedisClient = Depends(get_redis_cost_client),
    audit_chain_service: AuditChainService = Depends(get_audit_chain_service),
    alert_service: AlertService = Depends(get_notifications_service),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> BudgetService:
    return build_budget_service(
        repository=CostGovernanceRepository(session),
        redis_client=redis_client,
        settings=_get_settings(request),
        producer=_get_producer(request),
        audit_chain_service=audit_chain_service,
        alert_service=alert_service,
        workspaces_service=workspaces_service,
    )


async def get_cost_attribution_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    clickhouse_repository: ClickHouseCostRepository | None = Depends(
        get_clickhouse_cost_repository
    ),
    catalog_service: CatalogService = Depends(get_catalog_service),
    budget_service: BudgetService = Depends(get_budget_service),
) -> AttributionService:
    settings = _get_settings(request)
    return AttributionService(
        repository=CostGovernanceRepository(session),
        settings=settings,
        clickhouse_repository=clickhouse_repository,
        kafka_producer=_get_producer(request),
        model_catalog_service=catalog_service,
        budget_service=budget_service,
        fail_open=settings.cost_governance.attribution_fail_open,
    )


async def get_chargeback_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    clickhouse_repository: ClickHouseCostRepository | None = Depends(
        get_clickhouse_cost_repository
    ),
    audit_chain_service: AuditChainService = Depends(get_audit_chain_service),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> ChargebackService:
    settings = _get_settings(request)
    return ChargebackService(
        repository=CostGovernanceRepository(session),
        clickhouse_repository=clickhouse_repository,
        workspaces_service=workspaces_service,
        audit_chain_service=audit_chain_service,
        default_currency=settings.cost_governance.default_currency,
    )


async def get_forecast_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    clickhouse_repository: ClickHouseCostRepository | None = Depends(
        get_clickhouse_cost_repository
    ),
) -> ForecastService:
    settings = _get_settings(request)
    return ForecastService(
        repository=CostGovernanceRepository(session),
        clickhouse_repository=clickhouse_repository,
        minimum_history_periods=settings.cost_governance.minimum_history_periods_for_forecast,
        default_currency=settings.cost_governance.default_currency,
        kafka_producer=_get_producer(request),
    )


async def get_anomaly_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    clickhouse_repository: ClickHouseCostRepository | None = Depends(
        get_clickhouse_cost_repository
    ),
    audit_chain_service: AuditChainService = Depends(get_audit_chain_service),
    alert_service: AlertService = Depends(get_notifications_service),
) -> AnomalyService:
    return AnomalyService(
        repository=CostGovernanceRepository(session),
        clickhouse_repository=clickhouse_repository,
        kafka_producer=_get_producer(request),
        audit_chain_service=audit_chain_service,
        alert_service=alert_service,
    )


async def get_cost_governance_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    redis_client: AsyncRedisClient = Depends(get_redis_cost_client),
    clickhouse_repository: ClickHouseCostRepository | None = Depends(
        get_clickhouse_cost_repository
    ),
    audit_chain_service: AuditChainService = Depends(get_audit_chain_service),
    alert_service: AlertService = Depends(get_notifications_service),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
    catalog_service: CatalogService = Depends(get_catalog_service),
) -> CostGovernanceService:
    return build_cost_governance_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        redis_client=redis_client,
        clickhouse_repository=clickhouse_repository,
        audit_chain_service=audit_chain_service,
        alert_service=alert_service,
        workspaces_service=workspaces_service,
        model_catalog_service=catalog_service,
    )
