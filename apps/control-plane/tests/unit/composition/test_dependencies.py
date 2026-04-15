from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.composition.dependencies import build_composition_service
from platform.composition.service import CompositionService
from types import SimpleNamespace


def test_build_composition_service_wires_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(
        "platform.composition.dependencies.build_workspaces_service",
        lambda **kwargs: SimpleNamespace(name="workspaces", kwargs=kwargs),
    )
    monkeypatch.setattr(
        "platform.composition.dependencies.build_registry_service",
        lambda **kwargs: SimpleNamespace(name="registry", kwargs=kwargs),
    )
    monkeypatch.setattr(
        "platform.composition.dependencies.build_policy_service",
        lambda **kwargs: SimpleNamespace(name="policy", kwargs=kwargs),
    )
    monkeypatch.setattr(
        "platform.composition.dependencies.build_connectors_service",
        lambda **kwargs: SimpleNamespace(name="connectors", kwargs=kwargs),
    )

    service = build_composition_service(
        session=object(),
        settings=PlatformSettings(),
        producer=None,
        redis_client=object(),
        object_storage=object(),
        opensearch=object(),
        qdrant=object(),
        reasoning_client=None,
    )

    assert isinstance(service, CompositionService)
    assert service.services.registry.name == "registry"
    assert service.services.policy.name == "policy"
    assert service.services.connector.name == "connectors"
