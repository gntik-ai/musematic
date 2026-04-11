from __future__ import annotations

from platform.common.auth_middleware import AuthMiddleware
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, ValidationError, platform_exception_handler
from platform.context_engineering.dependencies import get_context_engineering_service
from platform.context_engineering.router import _actor_id, _workspace_id, router
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from tests.context_engineering_support import RouterContextEngineeringServiceStub


def _app(service: RouterContextEngineeringServiceStub) -> FastAPI:
    app = FastAPI()
    app.state.settings = PlatformSettings(AUTH_JWT_SECRET_KEY="secret", AUTH_JWT_ALGORITHM="HS256")
    app.add_exception_handler(PlatformError, platform_exception_handler)

    async def _service_override() -> RouterContextEngineeringServiceStub:
        return service

    app.dependency_overrides[get_context_engineering_service] = _service_override
    app.include_router(router)
    return app


def _headers() -> dict[str, str]:
    return {"X-Workspace-ID": str(uuid4())}


@pytest.mark.asyncio
async def test_context_engineering_router_requires_auth() -> None:
    app = FastAPI()
    app.state.settings = PlatformSettings(AUTH_JWT_SECRET_KEY="secret", AUTH_JWT_ALGORITHM="HS256")
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.add_middleware(AuthMiddleware)

    async def _service_override() -> RouterContextEngineeringServiceStub:
        return RouterContextEngineeringServiceStub(workspace_id=uuid4())

    app.dependency_overrides[get_context_engineering_service] = _service_override
    app.include_router(router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/context-engineering/profiles", headers=_headers())

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "path", "payload", "expected_status"),
    [
        ("post", "/api/v1/context-engineering/profiles", {"name": "p1"}, 201),
        ("get", "/api/v1/context-engineering/profiles", None, 200),
        ("get", f"/api/v1/context-engineering/profiles/{uuid4()}", None, 200),
        ("put", f"/api/v1/context-engineering/profiles/{uuid4()}", {"name": "p2"}, 200),
        ("delete", f"/api/v1/context-engineering/profiles/{uuid4()}", None, 204),
        (
            "post",
            f"/api/v1/context-engineering/profiles/{uuid4()}/assign",
            {"assignment_level": "workspace"},
            201,
        ),
        ("get", "/api/v1/context-engineering/assembly-records", None, 200),
        ("get", f"/api/v1/context-engineering/assembly-records/{uuid4()}", None, 200),
        ("get", "/api/v1/context-engineering/drift-alerts", None, 200),
        (
            "post",
            "/api/v1/context-engineering/ab-tests",
            {"name": "exp", "control_profile_id": str(uuid4()), "variant_profile_id": str(uuid4())},
            201,
        ),
        ("get", "/api/v1/context-engineering/ab-tests", None, 200),
        ("get", f"/api/v1/context-engineering/ab-tests/{uuid4()}", None, 200),
        ("post", f"/api/v1/context-engineering/ab-tests/{uuid4()}/end", None, 200),
    ],
)
@pytest.mark.asyncio
async def test_context_engineering_router_delegates_for_human_users(
    method: str,
    path: str,
    payload: dict[str, object] | None,
    expected_status: int,
) -> None:
    service = RouterContextEngineeringServiceStub(workspace_id=uuid4())
    app = _app(service)

    async def _current_user() -> dict[str, object]:
        return {"sub": str(uuid4())}

    app.dependency_overrides[get_current_user] = _current_user

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.request(method.upper(), path, headers=_headers(), json=payload)

    assert response.status_code == expected_status
    assert service.calls


def test_context_engineering_router_workspace_header_validation() -> None:
    with pytest.raises(ValidationError):
        _workspace_id(SimpleNamespace(headers={}))
    with pytest.raises(ValidationError):
        _workspace_id(SimpleNamespace(headers={"X-Workspace-ID": "bad"}))
    with pytest.raises(ValidationError):
        _actor_id({"agent_id": str(uuid4())})
    with pytest.raises(ValidationError):
        _actor_id({})
