from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.main import create_app
from platform.testing.router_e2e import router as e2e_router

import httpx
import jwt
import pytest


class FakeClient:
    def __init__(self) -> None:
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        return None

    async def health_check(self) -> bool:
        return True


def _fake_clients() -> dict[str, FakeClient]:
    return {
        'redis': FakeClient(),
        'kafka': FakeClient(),
        'kafka_consumer': FakeClient(),
        'qdrant': FakeClient(),
        'neo4j': FakeClient(),
        'clickhouse': FakeClient(),
        'opensearch': FakeClient(),
        'object_storage': FakeClient(),
        'runtime_controller': FakeClient(),
        'reasoning_engine': FakeClient(),
        'sandbox_manager': FakeClient(),
        'simulation_controller': FakeClient(),
    }


async def _async_true() -> bool:
    return True


async def _async_none() -> None:
    return None


async def _async_none_with_app(app) -> None:
    del app
    return None


@pytest.mark.asyncio
async def test_router_e2e_paths_return_404_when_flag_off(monkeypatch) -> None:
    import platform.main as main_module

    monkeypatch.setattr('platform.main._build_clients', lambda settings: _fake_clients())
    monkeypatch.setattr('platform.api.health.database_health_check', lambda: _async_true())
    monkeypatch.setattr(main_module, '_load_trust_runtime_assets', _async_none_with_app)
    monkeypatch.setattr(
        main_module.RubricTemplateLoader,
        'load_templates',
        lambda self, service: _async_none(),
    )

    settings = PlatformSettings(
        feature_e2e_mode=False,
        auth={'jwt_secret_key': 'e2e-secret-key-with-minimum-length-32', 'jwt_algorithm': 'HS256'},
        api_governance={'rate_limiting_enabled': False},
    )
    app = create_app(profile='api', settings=settings)
    candidate_paths = sorted({route.path for route in e2e_router.routes})
    registered_paths = {route.path for route in app.routes}

    assert not (registered_paths & set(candidate_paths))

    token = jwt.encode(
        {'sub': 'user-1', 'type': 'access'},
        'e2e-secret-key-with-minimum-length-32',
        algorithm='HS256',
    )

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url='http://testserver',
            headers={'Authorization': f'Bearer {token}'},
        ) as client:
            for path in candidate_paths:
                response = await client.get(path)
                assert response.status_code == 404, path


def test_router_e2e_paths_register_when_flag_on(monkeypatch) -> None:
    monkeypatch.setattr('platform.main._build_clients', lambda settings: _fake_clients())
    app = create_app(profile='api', settings=PlatformSettings(feature_e2e_mode=True))
    registered_paths = {route.path for route in app.routes}
    candidate_paths = {route.path for route in e2e_router.routes}
    assert candidate_paths <= registered_paths
