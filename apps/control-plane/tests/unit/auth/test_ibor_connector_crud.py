from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.auth.ibor_service import IBORConnectorService
from platform.auth.models import IBORSyncMode, IBORSyncRunStatus
from platform.auth.router import router as auth_router
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from tests.auth_ibor_support import InMemoryIBORRepository
from tests.auth_support import role_claim


def _payload(*, name: str, source_type: str = "oidc", sync_mode: str = "pull") -> dict[str, object]:
    return {
        "name": name,
        "source_type": source_type,
        "sync_mode": sync_mode,
        "cadence_seconds": 3600,
        "credential_ref": f"{name}-creds",
        "role_mapping_policy": [
            {
                "directory_group": "Platform-Admins",
                "platform_role": "platform_admin",
                "workspace_scope": None,
            }
        ],
        "enabled": True,
    }


def _build_app(
    service: IBORConnectorService,
    *,
    current_user: dict[str, object] | None = None,
    refresh_calls: list[str] | None = None,
) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.state.refresh_ibor_sync_scheduler = (
        (lambda: refresh_calls.append("refresh")) if refresh_calls is not None else None
    )
    app.include_router(auth_router)

    async def _user() -> dict[str, object]:
        return current_user or {
            "sub": str(uuid4()),
            "roles": [role_claim("platform_admin")],
        }

    async def _service() -> IBORConnectorService:
        return service

    from platform.auth.dependencies import get_ibor_service

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_ibor_service] = _service
    return app


@pytest.mark.asyncio
async def test_ibor_connector_crud_routes_cover_lifecycle_and_runs_pagination() -> None:
    actor_id = uuid4()
    repository = InMemoryIBORRepository()
    service = IBORConnectorService(repository=repository)
    refresh_calls: list[str] = []
    app = _build_app(
        service,
        current_user={
            "sub": str(actor_id),
            "roles": [role_claim("platform_admin")],
        },
        refresh_calls=refresh_calls,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        first = await client.post("/api/v1/auth/ibor/connectors", json=_payload(name="z-sync"))
        second = await client.post(
            "/api/v1/auth/ibor/connectors", json=_payload(name="a-sync", source_type="ldap")
        )
        duplicate = await client.post("/api/v1/auth/ibor/connectors", json=_payload(name="z-sync"))

        assert first.status_code == 201
        assert second.status_code == 201
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "IBOR_CONNECTOR_CONFLICT"

        first_id = first.json()["id"]
        second_id = second.json()["id"]

        listing = await client.get("/api/v1/auth/ibor/connectors")
        assert listing.status_code == 200
        assert [item["name"] for item in listing.json()["items"]] == ["a-sync", "z-sync"]

        detail = await client.get(f"/api/v1/auth/ibor/connectors/{first_id}")
        assert detail.status_code == 200
        assert detail.json()["credential_ref"] == "z-sync-creds"

        updated = await client.put(
            f"/api/v1/auth/ibor/connectors/{first_id}",
            json=_payload(name="z-sync-updated", sync_mode="push"),
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "z-sync-updated"
        assert updated.json()["sync_mode"] == "push"

        connector = repository.connectors[UUID(first_id)]
        runs = []
        for offset in range(3):
            run = await repository.create_sync_run(
                connector_id=connector.id,
                mode=IBORSyncMode.pull,
                status=IBORSyncRunStatus.succeeded,
                triggered_by=actor_id,
            )
            run.started_at = datetime.now(UTC) - timedelta(minutes=offset)
            run.finished_at = run.started_at + timedelta(seconds=5)
            run.counts = {"roles_added": offset}
            runs.append(run)

        runs_response = await client.get(
            f"/api/v1/auth/ibor/connectors/{connector.id}/runs",
            params={"limit": 2},
        )
        assert runs_response.status_code == 200
        payload = runs_response.json()
        assert len(payload["items"]) == 2
        assert payload["next_cursor"] is not None

        next_page = await client.get(
            f"/api/v1/auth/ibor/connectors/{connector.id}/runs",
            params={"limit": 2, "cursor": payload["next_cursor"]},
        )
        assert next_page.status_code == 200
        assert len(next_page.json()["items"]) == 1

        deleted = await client.delete(f"/api/v1/auth/ibor/connectors/{second_id}")
        assert deleted.status_code == 204

        after_delete = await client.get(f"/api/v1/auth/ibor/connectors/{second_id}")
        assert after_delete.status_code == 200
        assert after_delete.json()["enabled"] is False

    assert len(refresh_calls) == 4


@pytest.mark.asyncio
async def test_ibor_connector_routes_require_platform_admin() -> None:
    repository = InMemoryIBORRepository()
    service = IBORConnectorService(repository=repository)
    app = _build_app(
        service,
        current_user={"sub": str(uuid4()), "roles": [role_claim("viewer")]},
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/api/v1/auth/ibor/connectors", json=_payload(name="blocked"))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
