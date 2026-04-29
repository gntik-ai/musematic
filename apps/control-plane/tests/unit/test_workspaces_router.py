from __future__ import annotations

from platform.common.auth_middleware import AuthMiddleware
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.common.tagging.dependencies import get_label_service, get_tag_service
from platform.workspaces.dependencies import get_workspaces_service
from platform.workspaces.router import router
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from tests.auth_support import role_claim
from tests.workspaces_support import RouterServiceStub


def _test_settings() -> PlatformSettings:
    return PlatformSettings(AUTH_JWT_SECRET_KEY="router-test-secret", AUTH_JWT_ALGORITHM="HS256")


def _build_app(service: RouterServiceStub, settings: PlatformSettings) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.dependency_overrides[get_workspaces_service] = lambda: service
    app.dependency_overrides[get_tag_service] = lambda: object()
    app.dependency_overrides[get_label_service] = lambda: object()
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_router_requires_auth_for_real_app() -> None:
    settings = _test_settings()
    app = FastAPI()
    app.state.settings = settings
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.add_middleware(AuthMiddleware)
    app.dependency_overrides[get_workspaces_service] = lambda: RouterServiceStub()
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/workspaces")
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "path", "payload", "expected_status"),
    [
        ("post", "/api/v1/workspaces", {"name": "Finance"}, 201),
        ("get", "/api/v1/workspaces", None, 200),
        ("get", f"/api/v1/workspaces/{uuid4()}", None, 200),
        ("patch", f"/api/v1/workspaces/{uuid4()}", {"name": "Ops"}, 200),
        ("post", f"/api/v1/workspaces/{uuid4()}/archive", None, 200),
        ("post", f"/api/v1/workspaces/{uuid4()}/restore", None, 200),
        ("delete", f"/api/v1/workspaces/{uuid4()}", None, 202),
        (
            "post",
            f"/api/v1/workspaces/{uuid4()}/members",
            {"user_id": str(uuid4()), "role": "member"},
            201,
        ),
        ("get", f"/api/v1/workspaces/{uuid4()}/members", None, 200),
        ("patch", f"/api/v1/workspaces/{uuid4()}/members/{uuid4()}", {"role": "admin"}, 200),
        ("delete", f"/api/v1/workspaces/{uuid4()}/members/{uuid4()}", None, 204),
        ("post", f"/api/v1/workspaces/{uuid4()}/goals", {"title": "Goal"}, 201),
        ("get", f"/api/v1/workspaces/{uuid4()}/goals", None, 200),
        ("get", f"/api/v1/workspaces/{uuid4()}/goals/{uuid4()}", None, 200),
        ("patch", f"/api/v1/workspaces/{uuid4()}/goals/{uuid4()}", {"status": "in_progress"}, 200),
        (
            "put",
            f"/api/v1/workspaces/{uuid4()}/visibility",
            {"visibility_agents": ["finance:*"], "visibility_tools": ["tools:*"]},
            200,
        ),
        ("get", f"/api/v1/workspaces/{uuid4()}/visibility", None, 200),
        ("delete", f"/api/v1/workspaces/{uuid4()}/visibility", None, 204),
        ("get", f"/api/v1/workspaces/{uuid4()}/settings", None, 200),
        (
            "patch",
            f"/api/v1/workspaces/{uuid4()}/settings",
            {"subscribed_agents": ["planner:*"]},
            200,
        ),
    ],
)
@pytest.mark.asyncio
async def test_router_endpoints_validate_and_delegate(
    method: str,
    path: str,
    payload: dict[str, object] | None,
    expected_status: int,
) -> None:
    settings = _test_settings()
    service = RouterServiceStub()
    app = _build_app(service, settings)

    async def _current_user_override() -> dict[str, object]:
        return {
            "sub": str(uuid4()),
            "roles": [role_claim("workspace_admin")],
        }

    async def _service_override() -> RouterServiceStub:
        return service

    app.dependency_overrides[get_current_user] = _current_user_override
    app.dependency_overrides[get_workspaces_service] = _service_override
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        request_kwargs: dict[str, object] = {}
        if payload is not None:
            request_kwargs["json"] = payload
        response = await client.request(method.upper(), path, **request_kwargs)
    assert response.status_code == expected_status


@pytest.mark.asyncio
async def test_router_validation_errors_surface_as_422() -> None:
    settings = _test_settings()
    service = RouterServiceStub()
    app = _build_app(service, settings)

    async def _current_user_override() -> dict[str, object]:
        return {
            "sub": str(uuid4()),
            "roles": [role_claim("workspace_admin")],
        }

    async def _service_override() -> RouterServiceStub:
        return service

    app.dependency_overrides[get_current_user] = _current_user_override
    app.dependency_overrides[get_workspaces_service] = _service_override
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/workspaces",
            json={"name": ""},
        )
    assert response.status_code == 422
