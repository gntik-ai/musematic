from __future__ import annotations

from platform.common.auth_middleware import AuthMiddleware
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, ValidationError, platform_exception_handler
from platform.registry.dependencies import get_registry_service
from platform.registry.models import LifecycleStatus
from platform.registry.router import (
    _workspace_id,
    create_namespace,
    delete_namespace,
    list_agents,
    list_lifecycle_audit,
    list_namespaces,
    list_revisions,
    patch_agent,
    resolve_fqn,
    router,
    transition_lifecycle,
    update_maturity,
    upload_agent,
)
from platform.registry.schemas import NamespaceCreate
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, Response

from tests.auth_support import role_claim
from tests.registry_support import RouterRegistryServiceStub


def _settings() -> PlatformSettings:
    return PlatformSettings(
        AUTH_JWT_SECRET_KEY="registry-router-secret",
        AUTH_JWT_ALGORITHM="HS256",
    )


def _app(service: RouterRegistryServiceStub) -> FastAPI:
    app = FastAPI()
    app.state.settings = _settings()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.dependency_overrides[get_registry_service] = lambda: service
    app.include_router(router)
    return app


def _headers() -> dict[str, str]:
    return {"X-Workspace-ID": str(uuid4())}


@pytest.mark.asyncio
async def test_registry_router_requires_auth_on_real_app() -> None:
    app = FastAPI()
    app.state.settings = _settings()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.add_middleware(AuthMiddleware)
    app.dependency_overrides[get_registry_service] = lambda: RouterRegistryServiceStub()
    app.include_router(router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/namespaces", headers=_headers())

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "path", "payload", "expected_status"),
    [
        ("post", "/api/v1/namespaces", {"name": "finance"}, 201),
        ("get", "/api/v1/namespaces", None, 200),
        ("delete", f"/api/v1/namespaces/{uuid4()}", None, 204),
        ("get", "/api/v1/agents/resolve/finance:kyc-verifier", None, 200),
        ("get", "/api/v1/agents", None, 200),
        ("get", f"/api/v1/agents/{uuid4()}", None, 200),
        ("patch", f"/api/v1/agents/{uuid4()}", {"display_name": "Updated"}, 200),
        ("post", f"/api/v1/agents/{uuid4()}/transition", {"target_status": "validated"}, 200),
        ("post", f"/api/v1/agents/{uuid4()}/maturity", {"maturity_level": 2}, 200),
        ("get", f"/api/v1/agents/{uuid4()}/revisions", None, 200),
        ("get", f"/api/v1/agents/{uuid4()}/lifecycle-audit", None, 200),
    ],
)
@pytest.mark.asyncio
async def test_registry_router_endpoints_delegate_for_human_users(
    method: str,
    path: str,
    payload: dict[str, object] | None,
    expected_status: int,
) -> None:
    service = RouterRegistryServiceStub()
    app = _app(service)

    async def _current_user() -> dict[str, object]:
        return {"sub": str(uuid4()), "roles": [role_claim("workspace_admin")]}

    async def _service() -> RouterRegistryServiceStub:
        return service

    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_registry_service] = _service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.request(
            method.upper(),
            path,
            headers=_headers(),
            json=payload,
        )

    assert response.status_code == expected_status
    assert service.calls


@pytest.mark.asyncio
async def test_registry_router_upload_endpoint_and_agent_resolution_mode() -> None:
    service = RouterRegistryServiceStub()

    async def _agent_user() -> dict[str, object]:
        return {"sub": str(uuid4()), "agent_profile_id": str(uuid4())}

    class UploadStub:
        filename = "agent.tar.gz"

        async def read(self) -> bytes:
            return b"content"

    upload_response = await upload_agent(
        request=SimpleNamespace(headers=_headers()),
        response=Response(),
        namespace_name="finance",
        package=UploadStub(),
        current_user={"sub": str(uuid4()), "roles": [role_claim("workspace_admin")]},
        registry_service=service,
    )
    listed_response = await list_agents(
        request=SimpleNamespace(headers=_headers()),
        status=LifecycleStatus.published,
        maturity_min=0,
        fqn_pattern=None,
        keyword=None,
        limit=20,
        offset=0,
        current_user=await _agent_user(),
        registry_service=service,
    )
    resolved_response = await resolve_fqn(
        fqn="finance:kyc-verifier",
        request=SimpleNamespace(headers=_headers()),
        current_user=await _agent_user(),
        registry_service=service,
    )

    assert upload_response.created is True
    assert listed_response.total == 1
    assert resolved_response.fqn == "finance-ops:kyc-verifier"


@pytest.mark.asyncio
async def test_registry_router_rejects_agent_for_human_only_endpoints() -> None:
    service = RouterRegistryServiceStub()
    with pytest.raises(PlatformError) as exc_info:
        await create_namespace(
            payload=NamespaceCreate(name="finance"),
            request=SimpleNamespace(headers=_headers()),
            current_user={"sub": str(uuid4()), "agent_profile_id": str(uuid4())},
            registry_service=service,
        )

    assert exc_info.value.code == "USER_ID_REQUIRED"


def test_registry_router_workspace_header_validation() -> None:
    with pytest.raises(ValidationError) as missing_exc:
        _workspace_id(SimpleNamespace(headers={}))
    with pytest.raises(ValidationError) as invalid_exc:
        _workspace_id(SimpleNamespace(headers={"X-Workspace-ID": "bad"}))

    assert missing_exc.value.code == "WORKSPACE_HEADER_REQUIRED"
    assert invalid_exc.value.code == "WORKSPACE_HEADER_INVALID"


@pytest.mark.parametrize(
    ("callable_obj", "kwargs"),
    [
        (list_namespaces, {}),
        (delete_namespace, {"namespace_id": uuid4()}),
        (
            upload_agent,
            {
                "response": Response(),
                "namespace_name": "finance",
                "package": type(
                    "UploadStub",
                    (),
                    {"filename": "agent.tar.gz", "read": lambda self: _async_bytes()},
                )(),
            },
        ),
        (patch_agent, {"agent_id": uuid4(), "payload": {"display_name": "Updated"}}),
        (
            transition_lifecycle,
            {"agent_id": uuid4(), "payload": {"target_status": "validated"}},
        ),
        (update_maturity, {"agent_id": uuid4(), "payload": {"maturity_level": 2}}),
        (list_revisions, {"agent_id": uuid4()}),
        (list_lifecycle_audit, {"agent_id": uuid4()}),
    ],
)
@pytest.mark.asyncio
async def test_registry_router_human_only_endpoints_reject_agent_principals(
    callable_obj,
    kwargs,
) -> None:
    service = RouterRegistryServiceStub()
    common_kwargs = {
        "request": SimpleNamespace(headers=_headers()),
        "current_user": {"sub": str(uuid4()), "agent_profile_id": str(uuid4())},
        "registry_service": service,
    }

    with pytest.raises(PlatformError) as exc_info:
        await callable_obj(**common_kwargs, **kwargs)

    assert exc_info.value.code == "USER_ID_REQUIRED"


async def _async_bytes() -> bytes:
    return b"content"
