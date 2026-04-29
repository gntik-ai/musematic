from __future__ import annotations

import inspect
from platform.accounts import admin_router as accounts_admin
from platform.admin import health_router, lifecycle_router, operations_router, settings_router
from platform.admin.rbac import rate_limit_admin, require_admin, require_superadmin
from platform.admin.responses import AdminActionResponse, AdminDetailResponse, AdminListResponse
from platform.audit import admin_router as audit_admin
from platform.auth import admin_router as auth_admin
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user, get_workspace
from platform.common.exceptions import AuthorizationError, NotFoundError
from platform.connectors import admin_router as connectors_admin
from platform.cost_governance import admin_router as cost_admin
from platform.incident_response import admin_router as incident_admin
from platform.model_catalog import admin_router as model_catalog_admin
from platform.multi_region_ops import admin_router as multi_region_admin
from platform.notifications import admin_router as notifications_admin
from platform.policies import admin_router as policies_admin
from platform.privacy_compliance import admin_router as privacy_admin
from platform.security_compliance import admin_router as security_admin
from platform.workspaces import admin_router as workspaces_admin
from typing import Any, get_origin
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from starlette.requests import Request
from tests.unit.admin.test_workbench_services import _actor, _AuditChain, _QueueSession, _Result


def _request(
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    user: dict[str, Any] | None = None,
    clients: dict[str, Any] | None = None,
    settings: Any = None,
) -> Request:
    app = FastAPI()
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/admin/test",
            "headers": headers or [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("203.0.113.1", 50000),
            "app": app,
        }
    )
    request.state.correlation_id = "corr-router"
    request.app.state.clients = clients or {}
    if settings is not None:
        request.app.state.settings = settings
    if user is not None:
        request.state.user = user
    return request


def _dummy_value(name: str, annotation: Any) -> Any:
    annotation_name = (
        annotation if isinstance(annotation, str) else getattr(annotation, "__name__", "")
    )
    if name in {"current_user", "_current_user"}:
        return _actor(roles=["platform_admin", "superadmin"]) | {"tenant_id": str(uuid4())}
    if name == "audit_chain":
        return _AuditChain()
    if name == "session":
        return _QueueSession([_Result(), _Result(), _Result()])
    if name == "user_ids" or name == "session_ids":
        return ["a", "b"]
    if name == "tenant_id":
        return "tenant-id"
    if name == "request":
        return _request(settings=PlatformSettings())
    if name == "limit":
        return 25
    if name == "since":
        return None
    if name == "preview":
        return True
    if name == "payload":
        if (
            annotation is auth_admin.ChecklistStateUpdate
            or annotation_name == "ChecklistStateUpdate"
        ):
            return auth_admin.ChecklistStateUpdate(state={"done": True})
        if annotation is auth_admin.ReadOnlyModeUpdate or annotation_name == "ReadOnlyModeUpdate":
            return auth_admin.ReadOnlyModeUpdate(enabled=True)
    if annotation is UUID:
        return uuid4()
    origin = get_origin(annotation)
    if origin is list:
        return ["a", "b"]
    return f"{name}-id"


async def _call_endpoint(route: APIRoute) -> Any:
    kwargs: dict[str, Any] = {}
    for name, parameter in inspect.signature(route.endpoint).parameters.items():
        kwargs[name] = _dummy_value(name, parameter.annotation)
    try:
        return await route.endpoint(**kwargs)
    except HTTPException as exc:
        return exc


@pytest.mark.asyncio
async def test_simple_admin_router_endpoints_return_contract_responses() -> None:
    routers = [
        accounts_admin.router,
        auth_admin.router,
        connectors_admin.router,
        cost_admin.router,
        incident_admin.router,
        notifications_admin.router,
        operations_router.router,
        privacy_admin.router,
        model_catalog_admin.router,
        policies_admin.router,
        security_admin.router,
        workspaces_admin.router,
    ]
    responses: list[Any] = []

    for router in routers:
        for route in router.routes:
            if isinstance(route, APIRoute):
                responses.append(await _call_endpoint(route))

    assert any(isinstance(response, AdminListResponse) for response in responses)
    assert any(isinstance(response, AdminDetailResponse) for response in responses)
    assert any(isinstance(response, AdminActionResponse) for response in responses)
    assert any(
        isinstance(response, AdminActionResponse) and response.preview for response in responses
    )


@pytest.mark.asyncio
async def test_secondary_admin_router_endpoints_return_contract_responses() -> None:
    routers = [
        audit_admin.router,
        health_router.router,
        lifecycle_router.router,
        multi_region_admin.router,
    ]
    responses: list[Any] = []

    for router in routers:
        for route in router.routes:
            if isinstance(route, APIRoute):
                responses.append(await _call_endpoint(route))

    assert any(isinstance(response, AdminListResponse) for response in responses)
    assert any(response.__class__.__name__ == "AdminHealthResponse" for response in responses)
    assert any(isinstance(response, AdminActionResponse) for response in responses)


@pytest.mark.asyncio
async def test_settings_router_lists_updates_and_inserts_global_settings() -> None:
    actor = _actor(roles=["platform_admin"])
    audit_chain = _AuditChain()
    session = _QueueSession(
        [
            _Result(mappings=[{"key": "instance_name", "value": "old", "scope": "global"}]),
            _Result(mappings=[{"key": "instance_name", "value": "old", "scope": "global"}]),
            _Result(mappings=[{"key": "instance_name", "value": "old"}]),
            _Result(rowcount=0),
            _Result(),
            _Result(mappings=[{"key": "instance_name", "value": "new", "scope": "global"}]),
            _Result(rowcount=1),
        ]
    )

    listed = await settings_router.list_platform_settings(actor, session)
    empty_update = await settings_router.update_platform_settings(
        settings_router.PlatformSettingsUpdate(),
        actor,
        session,
        audit_chain,
    )
    updated = await settings_router.update_platform_settings(
        settings_router.PlatformSettingsUpdate(settings={"instance_name": "new"}),
        actor,
        session,
        audit_chain,
    )
    await settings_router._upsert_global_setting(session, "instance_name", "newer")

    assert listed[0].key == "instance_name"
    assert empty_update[0].value == "old"
    assert updated[0].value == "new"
    assert audit_chain.appended[-1]["event_type"] == "admin.settings.updated"


class _RateLimitResult:
    def __init__(self, *, allowed: bool, retry_after_ms: int = 0) -> None:
        self.allowed = allowed
        self.retry_after_ms = retry_after_ms


class _AdminRedis:
    def __init__(self, result: _RateLimitResult) -> None:
        self.result = result
        self.calls: list[tuple[Any, ...]] = []

    async def check_rate_limit(self, *args: Any) -> _RateLimitResult:
        self.calls.append(args)
        return self.result


@pytest.mark.asyncio
async def test_admin_rbac_dependencies_allow_deny_and_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_user = _actor(roles=["platform_admin"])
    superadmin_user = _actor(roles=["superadmin"])
    request = _request(user=admin_user)

    assert await require_admin(request, admin_user) is admin_user
    assert await require_superadmin(request, superadmin_user) is superadmin_user

    with pytest.raises(HTTPException) as admin_error:
        await require_admin(request, {"roles": ["viewer"]})
    assert admin_error.value.detail["correlation_id"] == "corr-router"

    with pytest.raises(HTTPException) as superadmin_error:
        await require_superadmin(request, admin_user)
    assert superadmin_error.value.detail["error_code"] == "superadmin_required"

    request = _request(clients={})
    await rate_limit_admin(request, admin_user)

    import platform.admin.rbac as rbac_module

    monkeypatch.setattr(rbac_module, "AsyncRedisClient", _AdminRedis)
    redis = _AdminRedis(_RateLimitResult(allowed=True))
    request = _request(clients={"redis": redis})
    await rate_limit_admin(request, admin_user)
    assert redis.calls[0][0] == "admin"

    redis = _AdminRedis(_RateLimitResult(allowed=False, retry_after_ms=2500))
    request = _request(clients={"redis": redis})
    with pytest.raises(HTTPException) as rate_error:
        await rate_limit_admin(request, admin_user)
    assert rate_error.value.status_code == 429
    assert rate_error.value.headers == {"Retry-After": "2"}


class _ImpersonationSession:
    async def execute(self, _statement: Any, params: dict[str, Any]) -> _Result:
        session_id = params.get("session_id")
        if session_id == _ImpersonationSessionState.active_session_id:
            return _Result(
                mappings=[
                    {
                        "session_id": session_id,
                        "impersonating_user_id": _ImpersonationSessionState.admin_id,
                        "effective_user_id": _ImpersonationSessionState.effective_id,
                        "email": "effective@example.test",
                    }
                ]
            )
        if params.get("user_id") == _ImpersonationSessionState.effective_id:
            return _Result(rows=[type("RoleRow", (), {"role": "viewer", "workspace_id": None})()])
        return _Result(mappings=[])


class _ImpersonationFactory:
    def __call__(self) -> _ImpersonationFactory:
        return self

    async def __aenter__(self) -> _ImpersonationSession:
        return _ImpersonationSession()

    async def __aexit__(self, *_args: Any) -> None:
        return None


class _ImpersonationSessionState:
    active_session_id = uuid4()
    admin_id = uuid4()
    effective_id = uuid4()


@pytest.mark.asyncio
async def test_common_dependencies_auth_workspace_and_impersonation_paths(
    auth_settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_user = {"sub": str(uuid4())}
    assert await get_current_user(_request(user=state_user)) == state_user

    with pytest.raises(AuthorizationError):
        await get_current_user(_request())
    with pytest.raises(AuthorizationError):
        await get_current_user(_request(headers=[(b"authorization", b"Bearer ")]))

    invalid_type = jwt.encode(
        {"sub": str(uuid4()), "type": "refresh"},
        auth_settings.auth.signing_key,
        algorithm=auth_settings.auth.jwt_algorithm,
    )
    with pytest.raises(AuthorizationError):
        await get_current_user(
            _request(
                headers=[(b"authorization", f"Bearer {invalid_type}".encode())],
                settings=auth_settings,
            )
        )

    token = jwt.encode(
        {"sub": str(uuid4()), "type": "access"},
        auth_settings.auth.signing_key,
        algorithm=auth_settings.auth.jwt_algorithm,
    )
    assert (
        await get_current_user(
            _request(
                headers=[(b"authorization", f"Bearer {token}".encode())],
                settings=auth_settings,
            )
        )
    )["sub"]

    bad_impersonation = jwt.encode(
        {
            "sub": str(uuid4()),
            "type": "access",
            "impersonation_session_id": "bad",
        },
        auth_settings.auth.signing_key,
        algorithm=auth_settings.auth.jwt_algorithm,
    )
    with pytest.raises(AuthorizationError):
        await get_current_user(
            _request(
                headers=[(b"authorization", f"Bearer {bad_impersonation}".encode())],
                settings=auth_settings,
            )
        )

    import platform.common.dependencies as dependencies_module

    monkeypatch.setattr(
        dependencies_module.database,
        "AsyncSessionLocal",
        _ImpersonationFactory(),
    )
    active_impersonation = jwt.encode(
        {
            "sub": str(uuid4()),
            "type": "access",
            "impersonation_session_id": str(_ImpersonationSessionState.active_session_id),
        },
        auth_settings.auth.signing_key,
        algorithm=auth_settings.auth.jwt_algorithm,
    )
    request = _request(
        headers=[(b"authorization", f"Bearer {active_impersonation}".encode())],
        settings=auth_settings,
    )
    decorated = await get_current_user(request)

    assert decorated["sub"] == str(_ImpersonationSessionState.effective_id)
    assert request.scope["impersonation_user_id"] == str(_ImpersonationSessionState.admin_id)

    with pytest.raises(NotFoundError):
        await get_workspace(_request())
    assert await get_workspace(_request(headers=[(b"x-workspace-id", b"workspace-1")])) == {
        "workspace_id": "workspace-1"
    }
