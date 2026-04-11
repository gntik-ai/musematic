from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.workspaces.dependencies import (
    _get_producer,
    _get_settings,
    build_workspaces_service,
    get_workspaces_service,
)
from platform.workspaces.repository import WorkspacesRepository
from types import SimpleNamespace

import pytest

from tests.auth_support import RecordingProducer
from tests.workspaces_support import AccountsServiceStub


def test_build_workspaces_service_wires_repository_and_accounts_service() -> None:
    settings = PlatformSettings()
    session = object()
    accounts_service = AccountsServiceStub(limit=3)
    producer = RecordingProducer()
    service = build_workspaces_service(
        session=session,  # type: ignore[arg-type]
        settings=settings,
        producer=producer,
        accounts_service=accounts_service,  # type: ignore[arg-type]
    )

    assert isinstance(service.repo, WorkspacesRepository)
    assert service.accounts_service is accounts_service
    assert service.kafka_producer is producer


def test_dependency_helpers_read_app_state() -> None:
    settings = PlatformSettings()
    producer = RecordingProducer()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={"kafka": producer},
            )
        )
    )

    assert _get_settings(request) is settings
    assert _get_producer(request) is producer


@pytest.mark.asyncio
async def test_get_workspaces_service_builds_from_request_state(monkeypatch) -> None:
    settings = PlatformSettings()
    producer = RecordingProducer()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={"kafka": producer},
            )
        )
    )
    session = object()
    accounts_service = AccountsServiceStub(limit=4)
    captured: dict[str, object] = {}

    def _fake_builder(**kwargs):
        captured.update(kwargs)
        return "service"

    monkeypatch.setattr("platform.workspaces.dependencies.build_workspaces_service", _fake_builder)

    service = await get_workspaces_service(
        request,  # type: ignore[arg-type]
        session=session,  # type: ignore[arg-type]
        accounts_service=accounts_service,  # type: ignore[arg-type]
    )

    assert service == "service"
    assert captured == {
        "session": session,
        "settings": settings,
        "producer": producer,
        "accounts_service": accounts_service,
    }
