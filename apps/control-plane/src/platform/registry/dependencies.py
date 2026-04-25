from __future__ import annotations

from platform.audit.dependencies import build_audit_chain_service
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.opensearch import AsyncOpenSearchClient
from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.model_catalog.repository import ModelCatalogRepository
from platform.privacy_compliance.dependencies import build_pia_service
from platform.registry.package_validator import PackageValidator
from platform.registry.repository import RegistryRepository
from platform.registry.service import RegistryService
from platform.workspaces.dependencies import get_workspaces_service
from platform.workspaces.service import WorkspacesService
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_object_storage(request: Request) -> AsyncObjectStorageClient:
    return cast(AsyncObjectStorageClient, request.app.state.clients["object_storage"])


def _get_opensearch(request: Request) -> AsyncOpenSearchClient:
    return cast(AsyncOpenSearchClient, request.app.state.clients["opensearch"])


def _get_qdrant(request: Request) -> AsyncQdrantClient:
    return cast(AsyncQdrantClient, request.app.state.clients["qdrant"])


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def build_registry_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    object_storage: AsyncObjectStorageClient,
    opensearch: AsyncOpenSearchClient,
    qdrant: AsyncQdrantClient,
    workspaces_service: WorkspacesService,
    producer: EventProducer | None,
) -> RegistryService:
    return RegistryService(
        repository=RegistryRepository(
            session,
            opensearch,
            build_audit_chain_service(session, settings, producer),
        ),
        object_storage=object_storage,
        opensearch=opensearch,
        qdrant=qdrant,
        model_catalog_repository=ModelCatalogRepository(session),
        workspaces_service=workspaces_service,
        event_producer=producer,
        settings=settings,
        pia_service=build_pia_service(session=session, producer=producer),
        package_validator=PackageValidator(settings),
    )


async def get_registry_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> RegistryService:
    return build_registry_service(
        session=session,
        settings=_get_settings(request),
        object_storage=_get_object_storage(request),
        opensearch=_get_opensearch(request),
        qdrant=_get_qdrant(request),
        workspaces_service=workspaces_service,
        producer=_get_producer(request),
    )
