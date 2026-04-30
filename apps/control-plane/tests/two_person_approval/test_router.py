from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.two_person_approval.dependencies import get_two_person_approval_service
from platform.two_person_approval.router import router
from platform.two_person_approval.schemas import ChallengeResponse
from platform.workspaces.dependencies import get_workspaces_service
from platform.workspaces.schemas import WorkspaceResponse
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from tests.auth_support import role_claim


class _TwoPAService:
    def __init__(self) -> None:
        self.initiator_id = uuid4()
        self.challenge_id = uuid4()
        self.payload = {"workspace_id": str(uuid4()), "new_owner_id": str(uuid4())}
        self.calls: list[str] = []

    def _response(self, status: str, co_signer_id: UUID | None = None) -> ChallengeResponse:
        now = datetime.now(UTC)
        return ChallengeResponse(
            id=self.challenge_id,
            action_type="workspace_transfer_ownership",
            status=status,
            initiator_id=self.initiator_id,
            co_signer_id=co_signer_id,
            created_at=now,
            expires_at=now + timedelta(minutes=5),
            approved_at=now if status in {"approved", "consumed"} else None,
            consumed_at=now if status == "consumed" else None,
        )

    async def create_challenge(self, **kwargs):
        self.calls.append("create")
        self.initiator_id = kwargs["initiator_id"]
        self.payload = dict(kwargs["action_payload"])
        return self._response("pending")

    async def get_challenge(self, challenge_id: UUID):
        self.calls.append(f"get:{challenge_id}")
        return self._response("pending")

    async def approve_challenge(self, *, challenge_id: UUID, co_signer_id: UUID):
        self.calls.append(f"approve:{challenge_id}")
        return self._response("approved", co_signer_id)

    async def consume_challenge(self, *, challenge_id: UUID, requester_id: UUID):
        self.calls.append(f"consume:{challenge_id}:{requester_id}")
        return self._response("consumed"), self.payload


class _WorkspacesService:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, object], UUID]] = []

    async def commit_ownership_transfer_payload(
        self,
        payload: dict[str, object],
        requester_id: UUID,
    ):
        self.calls.append((payload, requester_id))
        now = datetime.now(UTC)
        return WorkspaceResponse(
            id=UUID(str(payload["workspace_id"])),
            name="Workspace",
            description=None,
            status="active",
            owner_id=UUID(str(payload["new_owner_id"])),
            is_default=False,
            created_at=now,
            updated_at=now,
        )


def _app(
    two_pa_service: _TwoPAService,
    workspaces_service: _WorkspacesService,
    *,
    user_id: UUID | None = None,
    roles: list[str] | None = None,
) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router, prefix="/api/v1")
    resolved_user_id = user_id or uuid4()

    async def _user() -> dict[str, object]:
        return {
            "sub": str(resolved_user_id),
            "roles": [role_claim(role) for role in (roles or ["platform_admin"])],
        }

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_two_person_approval_service] = lambda: two_pa_service
    app.dependency_overrides[get_workspaces_service] = lambda: workspaces_service
    return app


@pytest.mark.asyncio
async def test_challenge_router_happy_path_dispatches_frozen_workspace_action() -> None:
    two_pa_service = _TwoPAService()
    workspaces_service = _WorkspacesService()
    user_id = uuid4()
    app = _app(two_pa_service, workspaces_service, user_id=user_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        create = await client.post(
            "/api/v1/2pa/challenges",
            json={
                "action_type": "workspace_transfer_ownership",
                "action_payload": two_pa_service.payload,
            },
        )
        fetch = await client.get(f"/api/v1/2pa/challenges/{two_pa_service.challenge_id}")
        approve = await client.post(
            f"/api/v1/2pa/challenges/{two_pa_service.challenge_id}/approve"
        )
        consume = await client.post(
            f"/api/v1/2pa/challenges/{two_pa_service.challenge_id}/consume"
        )

    assert create.status_code == 201
    assert fetch.status_code == 200
    assert approve.status_code == 200
    assert consume.status_code == 200
    assert (
        consume.json()["action_result"]["workspace"]["id"]
        == two_pa_service.payload["workspace_id"]
    )
    assert workspaces_service.calls == [(two_pa_service.payload, user_id)]


@pytest.mark.asyncio
async def test_approve_requires_platform_admin() -> None:
    two_pa_service = _TwoPAService()
    app = _app(two_pa_service, _WorkspacesService(), roles=["viewer"])

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/2pa/challenges/{two_pa_service.challenge_id}/approve"
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
    assert two_pa_service.calls == []
