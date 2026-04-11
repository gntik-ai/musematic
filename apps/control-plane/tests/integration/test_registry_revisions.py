from __future__ import annotations

from platform.main import create_app
from platform.registry.models import AgentRevision
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.integration.registry_flow_support import (
    build_registry_backends,
    build_registry_clients,
    build_registry_settings,
    create_namespace,
    create_workspace,
    human_token,
    seed_registry_user,
    upload_package,
)
from tests.registry_support import build_manifest_payload, build_tar_package

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_registry_revisions_remain_immutable_across_patch_and_new_uploads(
    monkeypatch,
    auth_settings,
    session_factory: async_sessionmaker,
    redis_client,
    migrated_database_url: str,
    object_storage_settings,
    opensearch_settings,
    qdrant_settings,
) -> None:
    settings = build_registry_settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_client=redis_client,
        object_storage_settings=object_storage_settings,
        opensearch_settings=opensearch_settings,
        qdrant_settings=qdrant_settings,
    )
    backends = build_registry_backends(
        object_storage_settings=object_storage_settings,
        opensearch_settings=opensearch_settings,
        qdrant_settings=qdrant_settings,
    )
    user_id = uuid4()
    await seed_registry_user(
        session_factory,
        user_id=user_id,
        email="registry-revisions@example.com",
        display_name="Revision User",
        max_workspaces=2,
    )
    token = human_token(settings, user_id)

    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda resolved: build_registry_clients(redis_client=redis_client, backends=backends),
    )
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            workspace_id = await create_workspace(client, token, name="Registry Revisions")
            namespace = await create_namespace(client, token, workspace_id, name="finance")
            assert namespace.status_code == 201, namespace.text

            uploaded = await upload_package(
                client,
                token,
                workspace_id,
                namespace_name="finance",
                package_bytes=build_tar_package(),
            )
            assert uploaded.status_code == 201, uploaded.text
            agent_id = UUID(uploaded.json()["agent_profile"]["id"])

            patched = await client.patch(
                f"/api/v1/agents/{agent_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Workspace-ID": str(workspace_id),
                },
                json={"display_name": "KYC Verifier Updated"},
            )
            revisions_after_patch = await client.get(
                f"/api/v1/agents/{agent_id}/revisions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Workspace-ID": str(workspace_id),
                },
            )
            updated = await upload_package(
                client,
                token,
                workspace_id,
                namespace_name="finance",
                package_bytes=build_tar_package(
                    manifest_payload=build_manifest_payload(
                        version="1.1.0",
                        display_name="KYC Verifier Updated",
                    )
                ),
            )
            revisions_after_upload = await client.get(
                f"/api/v1/agents/{agent_id}/revisions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Workspace-ID": str(workspace_id),
                },
            )
            fetched_agent = await client.get(
                f"/api/v1/agents/{agent_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Workspace-ID": str(workspace_id),
                },
            )

    assert patched.status_code == 200
    assert patched.json()["display_name"] == "KYC Verifier Updated"
    assert revisions_after_patch.status_code == 200
    assert revisions_after_patch.json()["total"] == 1
    assert updated.status_code == 200
    assert updated.json()["created"] is False
    assert revisions_after_upload.status_code == 200
    assert [item["version"] for item in revisions_after_upload.json()["items"]] == [
        "1.0.0",
        "1.1.0",
    ]
    assert fetched_agent.status_code == 200
    assert fetched_agent.json()["current_revision"]["version"] == "1.1.0"

    async with session_factory() as session:
        revisions = list(
            (
                await session.execute(
                    select(AgentRevision)
                    .where(AgentRevision.agent_profile_id == agent_id)
                    .order_by(AgentRevision.created_at.asc(), AgentRevision.id.asc())
                )
            ).scalars()
        )

    assert len(revisions) == 2
    assert revisions[0].manifest_snapshot["version"] == "1.0.0"
    assert revisions[1].manifest_snapshot["version"] == "1.1.0"
    assert revisions[0].sha256_digest == uploaded.json()["revision"]["sha256_digest"]
    assert revisions[1].sha256_digest == updated.json()["revision"]["sha256_digest"]
