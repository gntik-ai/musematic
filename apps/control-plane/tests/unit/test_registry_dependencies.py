from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.registry.dependencies import build_registry_service, get_registry_service
from platform.registry.service import RegistryService
from types import SimpleNamespace

import pytest

from tests.registry_support import (
    AsyncOpenSearchStub,
    AsyncQdrantStub,
    ObjectStorageStub,
    SessionStub,
    WorkspacesServiceStub,
)


def test_build_registry_service_wires_expected_dependencies() -> None:
    service = build_registry_service(
        session=SessionStub(),
        settings=PlatformSettings(),
        object_storage=ObjectStorageStub(),
        opensearch=AsyncOpenSearchStub(),
        qdrant=AsyncQdrantStub(),
        workspaces_service=WorkspacesServiceStub(),
        producer=None,
    )

    assert isinstance(service, RegistryService)
    assert service.settings.registry.search_index == "marketplace-agents"


@pytest.mark.asyncio
async def test_get_registry_service_reads_from_request_state() -> None:
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=PlatformSettings(),
                clients={
                    "object_storage": ObjectStorageStub(),
                    "opensearch": AsyncOpenSearchStub(),
                    "qdrant": AsyncQdrantStub(),
                    "kafka": None,
                },
            )
        )
    )

    service = await get_registry_service(
        request,
        session=SessionStub(),
        workspaces_service=WorkspacesServiceStub(),
    )

    assert isinstance(service, RegistryService)
