from __future__ import annotations

import platform.main as main_module
import re
from platform.common.config import PlatformSettings
from platform.main import create_app
from typing import Any

import pytest

PUBLIC_OPENAPI_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        "/healthz",
        "/api/v1/healthz",
        "/api/v1/accounts/register",
        "/api/v1/accounts/verify-email",
        "/api/v1/accounts/resend-verification",
        "/api/v1/accounts/invitations/{token}",
        "/api/v1/accounts/invitations/{token}/accept",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/mfa/verify",
        "/api/v1/auth/oauth/providers",
        "/api/v1/auth/oauth/{provider}/authorize",
        "/api/v1/auth/oauth/{provider}/callback",
        "/api/v1/security/audit-chain/public-key",
        "/.well-known/agent.json",
    }
)


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


def _build_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main_module.database, "configure_database", lambda settings: None)
    monkeypatch.setattr(main_module, "_build_clients", lambda settings: _fake_clients())
    monkeypatch.setattr(main_module, "setup_telemetry", lambda **kwargs: None)
    return create_app(settings=PlatformSettings())


def _iter_openapi_operations(spec: dict[str, Any]):
    for path, methods in spec["paths"].items():
        for method, operation in methods.items():
            if method.startswith("x-"):
                continue
            yield path, method, operation


def test_openapi_info_and_security_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(monkeypatch)

    spec = app.openapi()

    assert spec["info"]["title"] == "musematic Control Plane API"
    assert spec["info"]["version"] == app.version
    assert spec["info"]["contact"] == {
        "name": "musematic platform",
        "email": "platform@musematic.ai",
    }
    assert set(spec["components"]["securitySchemes"]) >= {"session", "oauth2", "apiKey"}

    for path, _method, operation in _iter_openapi_operations(spec):
        assert operation.get("tags"), f"{path} is missing tags"
        if path.startswith("/api/v1/admin/"):
            assert "admin" in operation["tags"], f"{path} is missing the admin tag"
        if path not in PUBLIC_OPENAPI_PATHS:
            assert operation.get("security"), f"{path} is missing security requirements"


def test_openapi_path_templates_are_unique(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app(monkeypatch)
    spec = app.openapi()
    normalized_paths: dict[str, str] = {}

    for path in spec["paths"]:
        normalized = re.sub(r"\{[^}/]+\}", "{}", path)
        assert normalized not in normalized_paths, (
            f"{path} conflicts with {normalized_paths[normalized]}"
        )
        normalized_paths[normalized] = path
