from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.policies.models import AttachmentTargetType, EnforcementComponent
from platform.policies.repository import PolicyRepository
from platform.policies.schemas import (
    EnforcementBundle,
    ValidationManifest,
    build_bundle_fingerprint,
)
from uuid import uuid4

import pytest

from tests.policies_support import (
    build_attachment,
    build_blocked_record,
    build_bundle_cache_record,
    build_execute_result,
    build_policy,
    build_version,
)
from tests.registry_support import SessionStub


@pytest.mark.asyncio
async def test_repository_create_and_query_methods_delegate_to_session() -> None:
    session = SessionStub(
        execute_results=[
            build_execute_result(one=build_policy()),
            build_execute_result(many=[build_policy()]),
            build_execute_result(many=[build_version()]),
            build_execute_result(one=build_version(version_number=2)),
            build_execute_result(one=build_version()),
        ],
        scalar_results=[1],
    )
    repository = PolicyRepository(session)
    created = await repository.create(build_policy())
    version = await repository.create_version(build_version(policy_id=created.id))
    found = await repository.get_by_id(created.id)
    listed, total = await repository.list_with_filters(
        scope_type=None,
        status=None,
        workspace_id=None,
        offset=0,
        limit=20,
    )
    versions = await repository.get_versions(created.id)
    version_two = await repository.get_version_by_number(created.id, 2)
    fetched_version = await repository.get_policy_version(version.id)

    assert created in session.added
    assert version in session.added
    assert found is not None
    assert total == 1
    assert len(listed) == 1
    assert len(versions) == 1
    assert version_two is not None
    assert fetched_version is not None


@pytest.mark.asyncio
async def test_repository_attachment_record_and_cache_operations() -> None:
    policy = build_policy()
    version = build_version(policy_id=policy.id)
    attachment = build_attachment(
        policy=policy,
        version=version,
        target_type=AttachmentTargetType.workspace,
        target_id=str(uuid4()),
    )
    session = SessionStub(
        execute_results=[
            build_execute_result(one=attachment),
            build_execute_result(one=attachment),
            build_execute_result(many=[attachment]),
            build_execute_result(many=[attachment]),
            build_execute_result(many=[build_blocked_record()]),
            build_execute_result(one=build_blocked_record()),
        ],
        scalar_results=[1],
    )
    repository = PolicyRepository(session)
    created_attachment = await repository.create_attachment(attachment)
    found_attachment = await repository.get_attachment(attachment.id, policy.id)
    active_attachment = await repository.find_active_attachment(
        policy_id=policy.id,
        target_type=attachment.target_type,
        target_id=attachment.target_id,
    )
    listed_attachments = await repository.list_attachments(policy.id)
    await repository.deactivate_attachment(attachment)
    async def _list_attachments(_policy_id):
        return [attachment]

    repository.list_attachments = _list_attachments  # type: ignore[method-assign]
    await repository.deactivate_attachments_for_policy(policy.id)
    applicable = await repository.get_all_applicable_attachments(
        workspace_id=uuid4(),
        agent_revision_id=None,
        deployment_id=None,
        execution_id=None,
    )
    record = build_blocked_record(
        enforcement_component=EnforcementComponent.tool_gateway,
        workspace_id=uuid4(),
    )
    created_record = await repository.create_blocked_action_record(record)
    listed_records, total = await repository.list_blocked_action_records(
        enforcement_component=EnforcementComponent.tool_gateway,
        workspace_id=record.workspace_id,
    )
    fetched_record = await repository.get_blocked_action_record(record.id)

    assert created_attachment is attachment
    assert found_attachment is attachment
    assert active_attachment is attachment
    assert listed_attachments == [attachment]
    assert attachment.is_active is False
    assert isinstance(attachment.deactivated_at, datetime)
    assert isinstance(applicable, list)
    assert created_record is record
    assert total == 1
    assert len(listed_records) == 1
    assert fetched_record is not None


@pytest.mark.asyncio
async def test_repository_upsert_bundle_cache_updates_existing_entries() -> None:
    session = SessionStub()
    repository = PolicyRepository(session)
    fingerprint = build_bundle_fingerprint([uuid4()])
    bundle = EnforcementBundle(
        fingerprint=fingerprint,
        manifest=ValidationManifest(
            source_policy_ids=[],
            source_version_ids=[],
            fingerprint=fingerprint,
        ),
    )
    cache = build_bundle_cache_record(
        fingerprint=fingerprint,
        bundle=bundle,
    )
    session.execute_results = [build_execute_result(one=None)]
    created = await repository.upsert_bundle_cache(cache)

    existing = build_bundle_cache_record(
        fingerprint=fingerprint,
        bundle=bundle,
        expires_in_seconds=30,
    )
    session.execute_results = [build_execute_result(one=existing)]
    updated_cache = build_bundle_cache_record(
        fingerprint=fingerprint,
        bundle=bundle,
        expires_in_seconds=120,
    )
    updated = await repository.upsert_bundle_cache(updated_cache)

    assert created is cache
    assert updated.expires_at > datetime.now(UTC) + timedelta(seconds=60)
