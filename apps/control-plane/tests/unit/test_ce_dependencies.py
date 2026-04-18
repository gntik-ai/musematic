from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.context_engineering.dependencies import (
    _get_optional_state_service,
    build_context_engineering_service,
    get_context_engineering_service,
)
from platform.context_engineering.service import ContextEngineeringService
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.analytics_support import ClickHouseClientStub
from tests.context_engineering_support import WorkspacesServiceStub
from tests.registry_support import (
    AsyncOpenSearchStub,
    AsyncQdrantStub,
    ObjectStorageStub,
    SessionStub,
)


def test_build_context_engineering_service_wires_components() -> None:
    service = build_context_engineering_service(
        session=SessionStub(),
        settings=PlatformSettings(),
        clickhouse_client=ClickHouseClientStub(),  # type: ignore[arg-type]
        object_storage=ObjectStorageStub(),
        producer=None,
        workspaces_service=WorkspacesServiceStub(),
    )

    assert isinstance(service, ContextEngineeringService)
    assert service.settings.context_engineering.bundle_bucket == "context-assembly-records"


@pytest.mark.asyncio
async def test_get_context_engineering_service_reads_state_and_optional_services() -> None:
    workspace_id = uuid4()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=PlatformSettings(),
                clients={
                    "clickhouse": ClickHouseClientStub(),
                    "object_storage": ObjectStorageStub(),
                    "kafka": None,
                    "opensearch": AsyncOpenSearchStub(),
                    "qdrant": AsyncQdrantStub(),
                },
                execution_service=SimpleNamespace(),
                interactions_service=SimpleNamespace(),
                memory_service=SimpleNamespace(),
                connectors_service=SimpleNamespace(),
                policies_service=SimpleNamespace(),
            )
        )
    )

    service = await get_context_engineering_service(
        request,
        session=SessionStub(),
        workspaces_service=WorkspacesServiceStub(workspace_ids=[workspace_id]),
    )

    assert isinstance(service, ContextEngineeringService)
    assert "system_instructions" in {item.value for item in service.adapters}
    request.app.state.services = {"planner_service": "memoized"}
    assert _get_optional_state_service(request, "planner_service") == "memoized"
