from __future__ import annotations

import time
from platform.main import create_app
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.integration.registry_flow_support import (
    agent_token,
    build_registry_backends,
    build_registry_clients,
    build_registry_settings,
    create_namespace,
    create_workspace,
    human_token,
    publish_agent,
    refresh_registry_index,
    seed_registry_user,
    upload_package,
)
from tests.registry_support import build_manifest_payload, build_tar_package

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _upload_published_agent(
    client: httpx.AsyncClient,
    token: str,
    workspace_id: UUID,
    *,
    namespace_name: str,
    manifest_payload: dict[str, object],
) -> UUID:
    uploaded = await upload_package(
        client,
        token,
        workspace_id,
        namespace_name=namespace_name,
        package_bytes=build_tar_package(manifest_payload=manifest_payload),
    )
    assert uploaded.status_code == 201, uploaded.text
    agent_id = UUID(uploaded.json()["agent_profile"]["id"])
    await publish_agent(client, token, workspace_id, agent_id)
    return agent_id


async def test_registry_discovery_supports_fqn_pattern_keyword_and_visibility(
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
        email="registry-discovery@example.com",
        display_name="Discovery User",
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
            workspace_id = await create_workspace(client, token, name="Registry Discovery")
            for namespace_name in ("ns-a", "ns-b", "requester"):
                namespace = await create_namespace(
                    client,
                    token,
                    workspace_id,
                    name=namespace_name,
                )
                assert namespace.status_code == 201, namespace.text

            requester_upload = await upload_package(
                client,
                token,
                workspace_id,
                namespace_name="requester",
                package_bytes=build_tar_package(
                    manifest_payload=build_manifest_payload(
                        local_name="router",
                        display_name="Requester Router",
                        purpose="Routes delegated work to registry agents.",
                        approach="Delegates and aggregates agent responses.",
                    )
                ),
            )
            assert requester_upload.status_code == 201, requester_upload.text
            requester_id = UUID(requester_upload.json()["agent_profile"]["id"])
            await _upload_published_agent(
                client,
                token,
                workspace_id,
                namespace_name="ns-a",
                manifest_payload=build_manifest_payload(
                    local_name="agent-1",
                    display_name="Accounts Helper",
                    purpose="Handles finance approvals and account routing tasks.",
                    approach="Matches finance operations against routing rules.",
                    tags=["finance", "routing"],
                ),
            )
            await _upload_published_agent(
                client,
                token,
                workspace_id,
                namespace_name="ns-b",
                manifest_payload=build_manifest_payload(
                    local_name="agent-2",
                    display_name="Translation Helper",
                    purpose="Translates support content for multilingual teams.",
                    approach="Applies translation templates to support tickets.",
                    tags=["translation", "support"],
                ),
            )

            await refresh_registry_index(backends.opensearch, settings)

            started = time.monotonic()
            resolved = await client.get(
                "/api/v1/agents/resolve/ns-a:agent-1",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Workspace-ID": str(workspace_id),
                },
            )
            elapsed = time.monotonic() - started
            patterned = await client.get(
                "/api/v1/agents",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Workspace-ID": str(workspace_id),
                },
                params={"fqn_pattern": "ns-a:*"},
            )
            keyword = await client.get(
                "/api/v1/agents",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Workspace-ID": str(workspace_id),
                },
                params={"keyword": "translation"},
            )
            invisible_for_agent = await client.get(
                "/api/v1/agents",
                headers={
                    "Authorization": f"Bearer {agent_token(settings, requester_id)}",
                    "X-Workspace-ID": str(workspace_id),
                },
            )

    assert resolved.status_code == 200
    assert elapsed < 1.0
    assert resolved.json()["fqn"] == "ns-a:agent-1"
    assert patterned.status_code == 200
    assert patterned.json()["total"] == 1
    assert [item["fqn"] for item in patterned.json()["items"]] == ["ns-a:agent-1"]
    assert keyword.status_code == 200
    assert keyword.json()["total"] == 1
    assert keyword.json()["items"][0]["fqn"] == "ns-b:agent-2"
    assert invisible_for_agent.status_code == 200
    assert invisible_for_agent.json()["total"] == 0
