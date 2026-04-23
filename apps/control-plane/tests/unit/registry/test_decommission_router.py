from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.execution.dependencies import get_runtime_controller_client
from platform.registry.dependencies import get_registry_service
from platform.registry.models import LifecycleStatus
from platform.registry.router import router as registry_router
from platform.registry.service import RegistryService
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from tests.auth_support import role_claim
from tests.registry_support import (
    AsyncOpenSearchStub,
    AsyncQdrantStub,
    ObjectStorageStub,
    RegistryRepoStub,
    build_namespace,
    build_profile,
    build_registry_settings,
)


class WorkspaceServiceStub:
    def __init__(self, workspace_id: UUID, actor_id: UUID, *, role: str = "owner") -> None:
        self.workspace_id = workspace_id
        self.actor_id = actor_id
        self.role = role

    async def get_user_workspace_ids(self, user_id: UUID) -> list[UUID]:
        if user_id == self.actor_id:
            return [self.workspace_id]
        return []

    async def get_membership(self, workspace_id: UUID, actor_id: UUID):
        if workspace_id == self.workspace_id and actor_id == self.actor_id:
            return SimpleNamespace(role=self.role)
        return None


class RuntimeControllerStub:
    async def list_active_instances(self, agent_fqn: str) -> list[str]:
        del agent_fqn
        return []

    async def stop_runtime(self, execution_id: str) -> None:
        del execution_id
        return None


def _build_service(
    *, workspace_id: UUID, actor_id: UUID, role: str, with_profile: bool
) -> RegistryService:
    repo = RegistryRepoStub()
    if with_profile:
        namespace = build_namespace(workspace_id=workspace_id, name="finance", created_by=actor_id)
        profile = build_profile(
            workspace_id=workspace_id,
            namespace=namespace,
            status=LifecycleStatus.published,
        )
        repo.profiles_by_id[profile.id] = profile
        repo.profiles_by_fqn[(workspace_id, profile.fqn)] = profile
    return RegistryService(
        repository=repo,
        object_storage=ObjectStorageStub(),
        opensearch=AsyncOpenSearchStub(),
        qdrant=AsyncQdrantStub(),
        workspaces_service=WorkspaceServiceStub(workspace_id, actor_id, role=role),
        event_producer=None,
        settings=build_registry_settings(),
    )


def _build_app(service: RegistryService, current_user: dict[str, object]) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(registry_router)

    async def _user() -> dict[str, object]:
        return current_user

    async def _service() -> RegistryService:
        return service

    async def _runtime() -> RuntimeControllerStub:
        return RuntimeControllerStub()

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_registry_service] = _service
    app.dependency_overrides[get_runtime_controller_client] = _runtime
    return app


@pytest.mark.asyncio
async def test_decommission_router_returns_403_for_non_owner_actor() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _build_service(
        workspace_id=workspace_id, actor_id=actor_id, role="member", with_profile=True
    )
    agent_id = next(iter(service.repository.profiles_by_id))
    app = _build_app(
        service,
        {"sub": str(actor_id), "roles": [role_claim("viewer")]},
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/registry/{workspace_id}/agents/{agent_id}/decommission",
            json={"reason": "Regulatory retirement Q2 2026"},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "REGISTRY_WORKSPACE_ACCESS_DENIED"


@pytest.mark.asyncio
async def test_decommission_router_returns_422_for_short_reason() -> None:
    app = _build_app(
        _build_service(workspace_id=uuid4(), actor_id=uuid4(), role="owner", with_profile=True),
        {"sub": str(uuid4()), "roles": [role_claim("platform_admin")]},
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/registry/{uuid4()}/agents/{uuid4()}/decommission",
            json={"reason": "too short"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_decommission_router_returns_404_for_missing_agent() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _build_service(
        workspace_id=workspace_id, actor_id=actor_id, role="owner", with_profile=False
    )
    app = _build_app(
        service,
        {"sub": str(actor_id), "roles": [role_claim("platform_admin")]},
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/registry/{workspace_id}/agents/{uuid4()}/decommission",
            json={"reason": "Regulatory retirement Q2 2026"},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "REGISTRY_AGENT_NOT_FOUND"
