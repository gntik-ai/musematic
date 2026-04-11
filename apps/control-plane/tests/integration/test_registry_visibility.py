from __future__ import annotations

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


async def _upload_and_publish(
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


async def test_registry_visibility_patterns_and_workspace_grants_apply_immediately(
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
        email="registry-visibility@example.com",
        display_name="Visibility User",
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
            workspace_id = await create_workspace(client, token, name="Registry Visibility")
            for namespace_name in ("requester", "local", "shared", "hidden"):
                namespace = await create_namespace(
                    client,
                    token,
                    workspace_id,
                    name=namespace_name,
                )
                assert namespace.status_code == 201, namespace.text

            requester_id = await _upload_and_publish(
                client,
                token,
                workspace_id,
                namespace_name="requester",
                manifest_payload=build_manifest_payload(
                    local_name="router",
                    display_name="Requester Router",
                    purpose="Routes agent discovery requests for the workspace.",
                    approach="Delegates to visible agents and aggregates responses.",
                ),
            )
            await _upload_and_publish(
                client,
                token,
                workspace_id,
                namespace_name="local",
                manifest_payload=build_manifest_payload(
                    local_name="reader",
                    display_name="Local Reader",
                    purpose="Reads local workspace materials for operators.",
                    approach="Fetches and summarizes workspace-local documents.",
                ),
            )
            await _upload_and_publish(
                client,
                token,
                workspace_id,
                namespace_name="shared",
                manifest_payload=build_manifest_payload(
                    local_name="writer",
                    display_name="Shared Writer",
                    purpose="Writes shared responses for partner teams.",
                    approach="Uses shared templates to produce partner-facing output.",
                ),
            )
            await _upload_and_publish(
                client,
                token,
                workspace_id,
                namespace_name="hidden",
                manifest_payload=build_manifest_payload(
                    local_name="judge",
                    display_name="Hidden Judge",
                    purpose="Performs internal evaluation of private agent outputs.",
                    approach="Scores outputs against internal-only rubrics.",
                ),
            )

            await refresh_registry_index(backends.opensearch, settings)
            agent_headers = {
                "Authorization": f"Bearer {agent_token(settings, requester_id)}",
                "X-Workspace-ID": str(workspace_id),
            }

            hidden_initially = await client.get("/api/v1/agents", headers=agent_headers)
            local_only = await client.patch(
                f"/api/v1/agents/{requester_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Workspace-ID": str(workspace_id),
                },
                json={"visibility_agents": ["local:*"]},
            )
            visible_after_patch = await client.get("/api/v1/agents", headers=agent_headers)
            grant_update = await client.put(
                f"/api/v1/workspaces/{workspace_id}/visibility",
                headers={"Authorization": f"Bearer {token}"},
                json={"visibility_agents": ["shared:*"], "visibility_tools": []},
            )
            visible_after_grant = await client.get("/api/v1/agents", headers=agent_headers)
            wildcard = await client.patch(
                f"/api/v1/agents/{requester_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Workspace-ID": str(workspace_id),
                },
                json={"visibility_agents": ["*"]},
            )
            visible_after_wildcard = await client.get("/api/v1/agents", headers=agent_headers)
            invalid_pattern = await client.patch(
                f"/api/v1/agents/{requester_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Workspace-ID": str(workspace_id),
                },
                json={"visibility_agents": ["["]},
            )

    assert hidden_initially.status_code == 200
    assert hidden_initially.json()["total"] == 0
    assert local_only.status_code == 200
    assert local_only.json()["visibility_agents"] == ["local:*"]
    assert visible_after_patch.status_code == 200
    assert [item["fqn"] for item in visible_after_patch.json()["items"]] == ["local:reader"]
    assert grant_update.status_code == 200
    assert grant_update.json()["visibility_agents"] == ["shared:*"]
    assert {item["fqn"] for item in visible_after_grant.json()["items"]} == {
        "local:reader",
        "shared:writer",
    }
    assert wildcard.status_code == 200
    assert {item["fqn"] for item in visible_after_wildcard.json()["items"]} == {
        "requester:router",
        "local:reader",
        "shared:writer",
        "hidden:judge",
    }
    assert invalid_pattern.status_code == 422
    assert invalid_pattern.json()["error"]["code"] == "REGISTRY_INVALID_VISIBILITY_PATTERN"
