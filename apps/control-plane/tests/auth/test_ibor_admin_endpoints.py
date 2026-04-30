from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.auth.ibor_service import IBORConnectorService
from platform.auth.models import IBORSyncMode, IBORSyncRunStatus
from platform.auth.router import router as auth_router
from platform.auth.schemas import IBORSyncTriggerResponse
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from tests.auth_ibor_support import InMemoryIBORRepository
from tests.auth_support import role_claim


def _connector_payload() -> dict[str, object]:
    return {
        "name": "ldap-directory",
        "source_type": "ldap",
        "sync_mode": "pull",
        "cadence_seconds": 3600,
        "credential_ref": "secret/data/musematic/test/ibor/ldap-directory",
        "role_mapping_policy": [
            {
                "directory_group": "Platform-Admins",
                "platform_role": "platform_admin",
                "workspace_scope": None,
            }
        ],
        "enabled": True,
    }


class _SyncService:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    async def trigger_sync(self, connector_id, *, triggered_by):
        self.calls.append((connector_id, triggered_by))
        return IBORSyncTriggerResponse(
            run_id=uuid4(),
            connector_id=connector_id,
            status=IBORSyncRunStatus.running,
            started_at=datetime.now(UTC),
        )


def _app(
    ibor_service: IBORConnectorService,
    sync_service: _SyncService,
    *,
    role: str = "platform_admin",
) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.state.refresh_ibor_sync_scheduler = None
    app.include_router(auth_router)

    async def _user() -> dict[str, object]:
        return {"sub": str(uuid4()), "roles": [role_claim(role)]}

    from platform.auth.dependencies import get_ibor_service, get_ibor_sync_service

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_ibor_service] = lambda: ibor_service
    app.dependency_overrides[get_ibor_sync_service] = lambda: sync_service
    return app


@pytest.mark.asyncio
async def test_ibor_admin_diagnostic_sync_now_and_history() -> None:
    repository = InMemoryIBORRepository()
    service = IBORConnectorService(repository=repository)
    sync_service = _SyncService()
    actor_id = uuid4()
    connector = await repository.create_connector(
        name="ldap-directory",
        source_type="ldap",
        sync_mode="pull",
        cadence_seconds=3600,
        credential_ref="secret/data/musematic/test/ibor/ldap-directory",
        role_mapping_policy=[],
        enabled=True,
        created_by=actor_id,
    )
    for offset in range(3):
        run = await repository.create_sync_run(
            connector_id=connector.id,
            mode=IBORSyncMode.pull,
            status=IBORSyncRunStatus.succeeded,
            counts={"users_upserted": offset},
            triggered_by=actor_id,
        )
        run.started_at = datetime.now(UTC) - timedelta(minutes=offset)
        run.finished_at = run.started_at + timedelta(seconds=5)

    app = _app(service, sync_service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        diagnostic = await client.post(
            f"/api/v1/auth/ibor/connectors/{connector.id}/test-connection"
        )
        sync = await client.post(f"/api/v1/auth/ibor/connectors/{connector.id}/sync-now")
        history = await client.get(
            f"/api/v1/auth/ibor/connectors/{connector.id}/sync-history",
            params={"limit": 2},
        )

    assert diagnostic.status_code == 200
    assert diagnostic.json()["success"] is True
    assert [step["step"] for step in diagnostic.json()["steps"]] == [
        "connector_lookup",
        "credential_reference",
        "ldap_diagnostic_ready",
    ]
    assert sync.status_code == 202
    assert sync.json()["connector_id"] == str(connector.id)
    assert len(sync_service.calls) == 1
    assert history.status_code == 200
    assert len(history.json()["items"]) == 2
    assert history.json()["next_cursor"] is not None


@pytest.mark.asyncio
async def test_ibor_admin_extensions_require_platform_admin() -> None:
    repository = InMemoryIBORRepository()
    service = IBORConnectorService(repository=repository)
    sync_service = _SyncService()
    app = _app(service, sync_service, role="viewer")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        created = await client.post("/api/v1/auth/ibor/connectors", json=_connector_payload())

    assert created.status_code == 403
