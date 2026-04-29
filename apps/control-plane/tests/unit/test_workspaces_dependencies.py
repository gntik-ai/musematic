from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.workspaces.dependencies import (
    _get_producer,
    _get_registry_service_for_workspace_governance,
    _get_settings,
    build_workspace_governance_service,
    build_workspaces_service,
    get_workspace_governance_service,
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
    assert captured["session"] is session
    assert captured["settings"] is settings
    assert captured["producer"] is producer
    assert captured["accounts_service"] is accounts_service
    assert "saved_view_service" in captured
    assert "tagging_service" in captured


def test_build_workspace_governance_service_wires_repositories(monkeypatch) -> None:
    captured: dict[str, object] = {}
    session = object()
    registry_service = object()

    def _fake_pipeline(**kwargs):
        captured.update(kwargs)
        return "pipeline"

    monkeypatch.setattr(
        "platform.governance.dependencies.build_pipeline_config_service",
        _fake_pipeline,
    )

    service = build_workspace_governance_service(
        session=session,  # type: ignore[arg-type]
        registry_service=registry_service,  # type: ignore[arg-type]
    )

    assert isinstance(service.workspaces_repo, WorkspacesRepository)
    assert service.pipeline_config == "pipeline"
    assert captured == {"session": session, "registry_service": registry_service}


@pytest.mark.asyncio
async def test_workspace_governance_dependencies_build_from_request_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = PlatformSettings()
    producer = RecordingProducer()
    object_storage = object()
    opensearch = object()
    qdrant = object()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={
                    "kafka": producer,
                    "object_storage": object_storage,
                    "opensearch": opensearch,
                    "qdrant": qdrant,
                },
            )
        )
    )
    session = object()
    accounts_service = AccountsServiceStub(limit=4)
    captured_registry: dict[str, object] = {}
    captured_governance: dict[str, object] = {}

    def _fake_registry_builder(**kwargs):
        captured_registry.update(kwargs)
        return "registry-service"

    def _fake_governance_builder(**kwargs):
        captured_governance.update(kwargs)
        return "workspace-governance-service"

    monkeypatch.setattr(
        "platform.registry.dependencies.build_registry_service",
        _fake_registry_builder,
    )
    monkeypatch.setattr(
        "platform.workspaces.dependencies.build_workspace_governance_service",
        _fake_governance_builder,
    )

    registry_service = await _get_registry_service_for_workspace_governance(
        request,  # type: ignore[arg-type]
        session=session,  # type: ignore[arg-type]
        accounts_service=accounts_service,  # type: ignore[arg-type]
    )
    governance_service = await get_workspace_governance_service(
        request,  # type: ignore[arg-type]
        session=session,  # type: ignore[arg-type]
        registry_service=registry_service,  # type: ignore[arg-type]
    )

    assert registry_service == "registry-service"
    assert governance_service == "workspace-governance-service"
    assert captured_registry["session"] is session
    assert captured_registry["settings"] is settings
    assert captured_registry["object_storage"] is object_storage
    assert captured_registry["opensearch"] is opensearch
    assert captured_registry["qdrant"] is qdrant
    assert captured_registry["producer"] is producer
    assert captured_registry["workspaces_service"].accounts_service is accounts_service
    assert captured_governance == {
        "session": session,
        "registry_service": "registry-service",
    }
