from __future__ import annotations

from platform.accounts.dependencies import get_accounts_service
from platform.accounts.service import AccountsService
from platform.audit.dependencies import build_audit_chain_service
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.opensearch import AsyncOpenSearchClient
from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.workspaces.governance import (
    WorkspaceGovernanceChainRepository,
    WorkspaceGovernanceChainService,
)
from platform.workspaces.repository import WorkspacesRepository
from platform.workspaces.service import WorkspacesService
from typing import TYPE_CHECKING, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from platform.registry.service import RegistryService


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    producer = request.app.state.clients.get("kafka")
    return cast(EventProducer | None, producer)


def build_workspaces_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    accounts_service: AccountsService | None = None,
    saved_view_service: object | None = None,
    tagging_service: object | None = None,
) -> WorkspacesService:
    return WorkspacesService(
        repo=WorkspacesRepository(session),
        settings=settings,
        kafka_producer=producer,
        accounts_service=accounts_service,
        saved_view_service=saved_view_service,
        tagging_service=tagging_service,
    )


async def get_workspaces_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> WorkspacesService:
    from platform.common.tagging.dependencies import build_saved_view_service, get_tagging_service

    tagging_service = await get_tagging_service(request, session)
    return build_workspaces_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        accounts_service=accounts_service,
        saved_view_service=build_saved_view_service(
            session,
            build_audit_chain_service(session, _get_settings(request), _get_producer(request)),
        ),
        tagging_service=tagging_service,
    )


def build_workspace_governance_service(
    *,
    session: AsyncSession,
    registry_service: RegistryService | None,
) -> WorkspaceGovernanceChainService:
    from platform.governance.dependencies import build_pipeline_config_service

    return WorkspaceGovernanceChainService(
        workspaces_repo=WorkspacesRepository(session),
        governance_repo=WorkspaceGovernanceChainRepository(session),
        pipeline_config=build_pipeline_config_service(
            session=session,
            registry_service=registry_service,
        ),
    )


async def _get_registry_service_for_workspace_governance(
    request: Request,
    session: AsyncSession = Depends(get_db),
    accounts_service: AccountsService = Depends(get_accounts_service),
) -> RegistryService:
    from platform.registry.dependencies import build_registry_service

    return build_registry_service(
        session=session,
        settings=_get_settings(request),
        object_storage=cast(AsyncObjectStorageClient, request.app.state.clients["object_storage"]),
        opensearch=cast(AsyncOpenSearchClient, request.app.state.clients["opensearch"]),
        qdrant=cast(AsyncQdrantClient, request.app.state.clients["qdrant"]),
        workspaces_service=build_workspaces_service(
            session=session,
            settings=_get_settings(request),
            producer=_get_producer(request),
            accounts_service=accounts_service,
        ),
        producer=_get_producer(request),
    )


async def get_workspace_governance_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    registry_service: RegistryService = Depends(_get_registry_service_for_workspace_governance),
) -> WorkspaceGovernanceChainService:
    del request
    return build_workspace_governance_service(
        session=session,
        registry_service=registry_service,
    )
