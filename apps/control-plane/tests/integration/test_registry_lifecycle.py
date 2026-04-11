from __future__ import annotations

from platform.main import create_app
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.integration.registry_flow_support import (
    build_registry_backends,
    build_registry_clients,
    build_registry_settings,
    create_namespace,
    create_workspace,
    human_token,
    refresh_registry_index,
    seed_registry_user,
    transition_agent,
    upload_package,
)
from tests.registry_support import build_tar_package

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_registry_lifecycle_enforces_transitions_audits_and_events(
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
        email="registry-lifecycle@example.com",
        display_name="Lifecycle User",
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
            workspace_id = await create_workspace(client, token, name="Registry Lifecycle")
            namespace = await create_namespace(client, token, workspace_id, name="lifecycle")
            assert namespace.status_code == 201, namespace.text

            uploaded = await upload_package(
                client,
                token,
                workspace_id,
                namespace_name="lifecycle",
                package_bytes=build_tar_package(),
            )
            assert uploaded.status_code == 201, uploaded.text
            agent_id = UUID(uploaded.json()["agent_profile"]["id"])
            fqn = uploaded.json()["agent_profile"]["fqn"]

            invalid = await transition_agent(
                client,
                token,
                workspace_id,
                agent_id,
                target_status="deprecated",
            )
            validated = await transition_agent(
                client,
                token,
                workspace_id,
                agent_id,
                target_status="validated",
            )
            published = await transition_agent(
                client,
                token,
                workspace_id,
                agent_id,
                target_status="published",
            )
            disabled = await transition_agent(
                client,
                token,
                workspace_id,
                agent_id,
                target_status="disabled",
            )
            republished = await transition_agent(
                client,
                token,
                workspace_id,
                agent_id,
                target_status="published",
            )
            deprecated = await transition_agent(
                client,
                token,
                workspace_id,
                agent_id,
                target_status="deprecated",
                reason="superseded by v2",
            )
            archived = await transition_agent(
                client,
                token,
                workspace_id,
                agent_id,
                target_status="archived",
            )
            audit = await client.get(
                f"/api/v1/agents/{agent_id}/lifecycle-audit",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Workspace-ID": str(workspace_id),
                },
            )

            await refresh_registry_index(backends.opensearch, settings)
            resolved_after_archive = await client.get(
                f"/api/v1/agents/resolve/{fqn}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Workspace-ID": str(workspace_id),
                },
            )

    registry_events = [
        event["event_type"]
        for event in backends.producer.events
        if str(event["event_type"]).startswith("registry.")
    ]

    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "REGISTRY_INVALID_TRANSITION"
    assert validated.status_code == 200
    assert validated.json()["status"] == "validated"
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert republished.status_code == 200
    assert republished.json()["status"] == "published"
    assert deprecated.status_code == 200
    assert deprecated.json()["status"] == "deprecated"
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert audit.status_code == 200
    assert [item["new_status"] for item in audit.json()["items"]] == [
        "validated",
        "published",
        "disabled",
        "published",
        "deprecated",
        "archived",
    ]
    assert registry_events.count("registry.agent.created") == 1
    assert registry_events.count("registry.agent.published") == 2
    assert registry_events.count("registry.agent.deprecated") == 1
    assert resolved_after_archive.status_code == 404
