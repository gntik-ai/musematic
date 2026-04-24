from __future__ import annotations

import platform.main as main_module
from platform.common.config import PlatformSettings
from platform.main import create_app

import pytest


class DummyClient:
    async def close(self) -> None:
        return None

    async def health_check(self) -> bool:
        return True


def _fake_clients() -> dict[str, DummyClient]:
    return {
        "redis": DummyClient(),
        "kafka": DummyClient(),
        "kafka_consumer": DummyClient(),
        "qdrant": DummyClient(),
        "neo4j": DummyClient(),
        "clickhouse": DummyClient(),
        "opensearch": DummyClient(),
        "object_storage": DummyClient(),
        "runtime_controller": DummyClient(),
        "reasoning_engine": DummyClient(),
        "sandbox_manager": DummyClient(),
        "simulation_controller": DummyClient(),
    }


def test_openapi_and_docs_are_mounted_under_api_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module.database, "configure_database", lambda settings: None)
    monkeypatch.setattr(main_module, "_build_clients", lambda settings: _fake_clients())
    monkeypatch.setattr(main_module, "setup_telemetry", lambda **kwargs: None)

    app = create_app(settings=PlatformSettings())

    assert app.openapi_url == "/api/openapi.json"
    assert app.docs_url == "/api/docs"
    assert app.redoc_url == "/api/redoc"
