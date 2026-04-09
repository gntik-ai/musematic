from __future__ import annotations

from uuid import uuid4

import pytest


pytestmark = pytest.mark.asyncio


async def test_agent_package_versions_are_listed_and_retrievable(object_storage_client) -> None:
    key = f"finance-ops/kyc-verifier/{uuid4().hex}.tar.gz"
    first_payload = b"version1"
    second_payload = b"version2"

    await object_storage_client.upload_object("agent-packages", key, first_payload)
    await object_storage_client.upload_object("agent-packages", key, second_payload)

    versions = await object_storage_client.get_object_versions("agent-packages", key)

    assert len(versions) >= 2
    downloaded = {
        await object_storage_client.download_object("agent-packages", key, version_id=version.version_id)
        for version in versions[:2]
    }
    assert {first_payload, second_payload}.issubset(downloaded)


async def test_deleting_latest_version_keeps_previous_version_accessible(object_storage_client) -> None:
    key = f"finance-ops/kyc-verifier/{uuid4().hex}.tar.gz"
    await object_storage_client.upload_object("agent-packages", key, b"version1")
    await object_storage_client.upload_object("agent-packages", key, b"version2")

    versions = await object_storage_client.get_object_versions("agent-packages", key)
    latest = next(version for version in versions if version.is_latest)
    previous = next(version for version in versions if not version.is_latest)

    await object_storage_client.delete_object("agent-packages", key, version_id=latest.version_id)

    restored = await object_storage_client.download_object(
        "agent-packages",
        key,
        version_id=previous.version_id,
    )
    assert restored == b"version1"
