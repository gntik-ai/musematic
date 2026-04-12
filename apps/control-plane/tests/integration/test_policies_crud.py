from __future__ import annotations

from platform.policies.models import PolicyScopeType
from platform.policies.service import PolicyService
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from tests.auth_support import RecordingProducer
from tests.policies_support import (
    InMemoryPolicyRepository,
    RegistryPolicyStub,
    WorkspacesPolicyStub,
    build_policy_create,
    build_policy_service_app,
    build_policy_settings,
    build_rules,
)


@pytest.mark.asyncio
async def test_policy_crud_flow_via_api_creates_versions_and_archives() -> None:
    workspace_id = uuid4()
    repository = InMemoryPolicyRepository()
    service = PolicyService(
        repository=repository,
        settings=build_policy_settings(),
        producer=RecordingProducer(),
        redis_client=None,
        registry_service=RegistryPolicyStub(),
        workspaces_service=WorkspacesPolicyStub(workspace_ids={workspace_id}),
    )
    app = build_policy_service_app(service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            "/api/v1/policies",
            json=build_policy_create(
                workspace_id=workspace_id,
                scope_type=PolicyScopeType.workspace,
                rules=build_rules(),
            ).model_dump(mode="json"),
        )
        policy_id = created.json()["id"]
        updated = await client.patch(
            f"/api/v1/policies/{policy_id}",
            json={"rules": {"allowed_namespaces": ["finance"]}, "change_summary": "v2"},
        )
        history = await client.get(f"/api/v1/policies/{policy_id}/versions")
        version_one = await client.get(f"/api/v1/policies/{policy_id}/versions/1")
        archived = await client.post(f"/api/v1/policies/{policy_id}/archive")
        listing = await client.get(
            "/api/v1/policies",
            params={"workspace_id": str(workspace_id)},
        )

    assert created.status_code == 201
    assert created.json()["current_version"]["version_number"] == 1
    assert updated.status_code == 200
    assert updated.json()["current_version"]["version_number"] == 2
    assert history.json()["total"] == 2
    assert version_one.json()["version_number"] == 1
    assert archived.json()["status"] == "archived"
    assert listing.json()["total"] == 0
