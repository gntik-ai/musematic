from __future__ import annotations

import os
from platform.main import create_app
from platform.registry.models import AgentProfile, AgentRevision
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.integration.registry_flow_support import (
    build_registry_backends,
    build_registry_clients,
    build_registry_settings,
    create_namespace,
    create_workspace,
    fetch_registry_document,
    human_token,
    refresh_registry_index,
    seed_registry_user,
    upload_package,
)
from tests.registry_support import build_manifest_payload, build_tar_package

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _count_rows(session_factory: async_sessionmaker, model: type[object]) -> int:
    async with session_factory() as session:
        total = await session.scalar(select(func.count()).select_from(model))
    return int(total or 0)


async def test_registry_upload_flow_persists_objects_and_search_documents(
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
        package_size_limit_mb=1,
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
        email="registry-uploader@example.com",
        display_name="Registry Uploader",
        max_workspaces=2,
    )
    token = human_token(settings, user_id)

    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda resolved: build_registry_clients(redis_client=redis_client, backends=backends),
    )

    app = create_app(settings=settings)
    manifest_missing_purpose = build_manifest_payload()
    manifest_missing_purpose.pop("purpose")

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            workspace_id = await create_workspace(client, token, name="Registry Uploads")

            namespace = await create_namespace(
                client,
                token,
                workspace_id,
                name="finance",
                description="Finance agents",
            )
            uploaded = await upload_package(
                client,
                token,
                workspace_id,
                namespace_name="finance",
                package_bytes=build_tar_package(),
            )
            updated = await upload_package(
                client,
                token,
                workspace_id,
                namespace_name="finance",
                package_bytes=build_tar_package(
                    manifest_payload=build_manifest_payload(
                        version="1.1.0",
                        display_name="KYC Verifier 1.1",
                    )
                ),
            )
            traversal = await upload_package(
                client,
                token,
                workspace_id,
                namespace_name="finance",
                package_bytes=build_tar_package(extra_files={"../../escape.txt": b"oops"}),
            )
            symlink = await upload_package(
                client,
                token,
                workspace_id,
                namespace_name="finance",
                package_bytes=build_tar_package(symlink_target="../../etc/passwd"),
            )
            oversized = await upload_package(
                client,
                token,
                workspace_id,
                namespace_name="finance",
                package_bytes=build_tar_package(
                    extra_files={"blob.bin": os.urandom(2 * 1024 * 1024)}
                ),
            )
            missing_purpose = await upload_package(
                client,
                token,
                workspace_id,
                namespace_name="finance",
                package_bytes=build_tar_package(
                    manifest_payload=manifest_missing_purpose
                ),
            )
            revisions = await client.get(
                f"/api/v1/agents/{uploaded.json()['agent_profile']['id']}/revisions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Workspace-ID": str(workspace_id),
                },
            )

        await refresh_registry_index(backends.opensearch, settings)
        search_document = await fetch_registry_document(
            backends.opensearch,
            settings,
            agent_profile_id=UUID(uploaded.json()["agent_profile"]["id"]),
        )
        stored_objects = await backends.object_storage.list_objects(
            settings.registry.package_bucket,
            prefix=f"{workspace_id}/finance/",
        )

    assert namespace.status_code == 201
    assert uploaded.status_code == 201
    assert uploaded.json()["created"] is True
    assert updated.status_code == 200
    assert updated.json()["created"] is False
    assert revisions.status_code == 200
    assert [item["version"] for item in revisions.json()["items"]] == ["1.0.0", "1.1.0"]
    assert traversal.status_code == 422
    assert traversal.json()["error"]["details"]["error_type"] == "path_traversal"
    assert symlink.status_code == 422
    assert symlink.json()["error"]["details"]["error_type"] == "symlink_rejected"
    assert oversized.status_code == 422
    assert oversized.json()["error"]["details"]["error_type"] == "size_limit"
    assert missing_purpose.status_code == 422
    assert missing_purpose.json()["error"]["details"]["error_type"] == "manifest_invalid"

    assert await _count_rows(session_factory, AgentProfile) == 1
    assert await _count_rows(session_factory, AgentRevision) == 2
    assert sorted(stored_objects) == sorted(
        [
            uploaded.json()["revision"]["storage_key"],
            updated.json()["revision"]["storage_key"],
        ]
    )
    assert search_document["fqn"] == "finance:kyc-verifier"
    assert search_document["current_version"] == "1.1.0"
