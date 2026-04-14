from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.workflows.dependencies import (
    _get_producer,
    _get_settings,
    build_workflow_service,
    get_workflow_service,
)
from platform.workflows.repository import WorkflowRepository
from platform.workflows.service import WorkflowService
from types import SimpleNamespace

import pytest

from tests.workflow_execution_support import FakeProducer


def _request(settings: PlatformSettings, producer: FakeProducer) -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={"kafka": producer},
                workflow_scheduler="scheduler",
            )
        )
    )


def test_workflow_dependency_helpers_read_from_request_state() -> None:
    settings = PlatformSettings()
    producer = FakeProducer()
    request = _request(settings, producer)

    assert _get_settings(request) is settings
    assert _get_producer(request) is producer


@pytest.mark.asyncio
async def test_workflow_dependency_factories_build_service() -> None:
    settings = PlatformSettings()
    producer = FakeProducer()
    session = object()
    request = _request(settings, producer)

    built = build_workflow_service(
        session=session,  # type: ignore[arg-type]
        settings=settings,
        producer=producer,  # type: ignore[arg-type]
        scheduler="scheduler",
    )
    resolved = await get_workflow_service(
        request=request,
        session=session,  # type: ignore[arg-type]
    )

    assert isinstance(built, WorkflowService)
    assert isinstance(built.repository, WorkflowRepository)
    assert built.repository.session is session
    assert built.scheduler == "scheduler"
    assert isinstance(resolved, WorkflowService)
    assert resolved.repository.session is session
    assert resolved.scheduler == "scheduler"
