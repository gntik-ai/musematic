from __future__ import annotations

from platform.registry.models import (
    AgentProfile,
    AssessmentMethod,
    EmbeddingStatus,
    LifecycleStatus,
)
from platform.registry.repository import RegistryRepository
from uuid import uuid4

import pytest

from tests.registry_support import (
    AsyncOpenSearchStub,
    ExecuteResultStub,
    SessionStub,
    build_namespace,
    build_profile,
)


@pytest.mark.asyncio
async def test_repository_namespace_crud_and_count_queries() -> None:
    workspace_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id)
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(one=namespace),
            ExecuteResultStub(one=namespace),
            ExecuteResultStub(many=[namespace]),
        ],
        scalar_results=[1],
    )
    repo = RegistryRepository(session)

    created = await repo.create_namespace(
        workspace_id=workspace_id,
        name="finance-ops",
        description="Ops namespace",
        created_by=uuid4(),
    )
    fetched_by_name = await repo.get_namespace_by_name(workspace_id, namespace.name)
    fetched_by_id = await repo.get_namespace_by_id(workspace_id, namespace.id)
    listed = await repo.list_namespaces(workspace_id)
    has_agents = await repo.namespace_has_agents(namespace.id)
    await repo.delete_namespace(namespace)

    assert created.name == "finance-ops"
    assert fetched_by_name == namespace
    assert fetched_by_id == namespace
    assert listed == [namespace]
    assert has_agents is True
    assert session.deleted == [namespace]
    assert session.flush_calls >= 2


@pytest.mark.asyncio
async def test_repository_upsert_and_profile_accessors() -> None:
    workspace_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, name="finance")
    existing = build_profile(workspace_id=workspace_id, namespace=namespace)
    other = build_profile(workspace_id=workspace_id, namespace=namespace, local_name="reviewer")
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(one=None),
            ExecuteResultStub(one=existing),
            ExecuteResultStub(one=existing),
            ExecuteResultStub(one=existing),
            ExecuteResultStub(one=existing),
            ExecuteResultStub(many=[existing, other]),
            ExecuteResultStub(many=[existing, other]),
        ],
        scalar_results=[2],
    )
    repo = RegistryRepository(session)

    created, created_flag = await repo.upsert_agent_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        local_name="kyc-verifier",
        display_name="Verifier",
        purpose="Valid purpose long enough to pass repository tests.",
        approach="Extract and evaluate evidence.",
        role_types=["executor"],
        custom_role_description=None,
        tags=["kyc"],
        maturity_level=1,
        actor_id=uuid4(),
    )
    updated, updated_flag = await repo.upsert_agent_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        local_name=existing.local_name,
        display_name="Updated",
        purpose="Updated purpose long enough to pass repository tests.",
        approach="Updated approach",
        role_types=["planner"],
        custom_role_description="Owns orchestration",
        tags=["ops"],
        maturity_level=2,
        actor_id=uuid4(),
    )
    fetched_by_id = await repo.get_agent_by_id(workspace_id, existing.id)
    fetched_by_fqn = await repo.get_agent_by_fqn(workspace_id, existing.fqn)
    fetched_alias = await repo.get_by_fqn(workspace_id, existing.fqn)
    listed, total = await repo.list_agents_by_workspace(
        workspace_id,
        status=LifecycleStatus.draft,
        maturity_min=0,
        limit=20,
        offset=0,
    )
    ordered = await repo.get_agents_by_ids(workspace_id, [other.id, existing.id, uuid4()])
    touched = await repo.update_agent_profile(existing, display_name="Touched")

    assert created_flag is True
    assert created.fqn == "finance:kyc-verifier"
    assert updated_flag is False
    assert fetched_by_id is existing
    assert existing.display_name == "Touched"
    assert updated.role_types == ["planner"]
    assert updated.custom_role_description == "Owns orchestration"
    assert updated.approach == "Updated approach"
    assert fetched_by_fqn == existing
    assert fetched_alias == existing
    assert listed == [existing, other]
    assert total == 2
    assert ordered == [other, existing]
    assert touched.display_name == "Touched"
    assert await repo.get_agents_by_ids(workspace_id, []) == []


@pytest.mark.asyncio
async def test_repository_revision_audit_maturity_and_reindex_helpers() -> None:
    workspace_id = uuid4()
    profile = build_profile(workspace_id=workspace_id)
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(one=object()),
            ExecuteResultStub(one=object()),
            ExecuteResultStub(many=[object()]),
            ExecuteResultStub(many=[object()]),
            ExecuteResultStub(many=[profile]),
        ],
        get_results={
            (AgentProfile, profile.id): profile,
            (AgentProfile, uuid4()): None,
        },
    )
    repo = RegistryRepository(session)

    revision = await repo.insert_revision(
        revision_id=uuid4(),
        workspace_id=workspace_id,
        agent_profile_id=profile.id,
        version="1.0.0",
        sha256_digest="a" * 64,
        storage_key="bucket/key",
        manifest_snapshot={"version": "1.0.0"},
        uploaded_by=uuid4(),
    )
    await repo.get_revision_by_id(revision.id)
    await repo.get_latest_revision(profile.id)
    await repo.list_revisions(profile.id)
    maturity = await repo.insert_maturity_record(
        workspace_id=workspace_id,
        agent_profile_id=profile.id,
        previous_level=0,
        new_level=1,
        assessment_method=AssessmentMethod.system_assessed,
        reason="Promoted",
        actor_id=uuid4(),
    )
    audit = await repo.insert_lifecycle_audit(
        workspace_id=workspace_id,
        agent_profile_id=profile.id,
        previous_status=LifecycleStatus.draft,
        new_status=LifecycleStatus.validated,
        actor_id=uuid4(),
        reason="Reviewed",
    )
    await repo.list_lifecycle_audit(profile.id)
    needing_reindex = await repo.get_agents_needing_reindex()
    await repo.set_needs_reindex(profile.id, True)
    await repo.set_embedding_status(profile.id, EmbeddingStatus.complete)

    assert revision.version == "1.0.0"
    assert maturity.new_level == 1
    assert audit.new_status == LifecycleStatus.validated
    assert needing_reindex == [profile]
    assert profile.needs_reindex is True
    assert profile.embedding_status == EmbeddingStatus.complete


@pytest.mark.asyncio
async def test_repository_keyword_search_uses_opensearch_results() -> None:
    workspace_id = uuid4()
    profile_id = uuid4()
    raw_client = type(
        "RawClient",
        (),
        {
            "calls": [],
            "search": lambda self, **kwargs: _search_response(self, kwargs, profile_id),
        },
    )()
    repo = RegistryRepository(SessionStub(), AsyncOpenSearchStub(raw_client=raw_client))

    ids, total = await repo.search_by_keyword(
        workspace_id=workspace_id,
        keyword="kyc",
        status=LifecycleStatus.published,
        maturity_min=1,
        limit=10,
        offset=0,
        index_name="marketplace-agents",
    )

    assert ids == [profile_id]
    assert total == 1
    assert raw_client.calls[0]["index"] == "marketplace-agents"


@pytest.mark.asyncio
async def test_repository_helpers_handle_missing_profiles_and_invalid_search_hits() -> None:
    repo = RegistryRepository(SessionStub(), None)

    assert await repo.search_by_keyword(
        workspace_id=uuid4(),
        keyword="kyc",
        status=None,
        maturity_min=0,
        limit=5,
        offset=0,
        index_name="marketplace-agents",
    ) == ([], 0)

    session = SessionStub()
    repo = RegistryRepository(session)
    await repo.set_needs_reindex(uuid4(), True)
    await repo.set_embedding_status(uuid4(), EmbeddingStatus.failed)
    assert session.flush_calls == 0

    raw_client = type(
        "RawClient",
        (),
        {
            "search": lambda self, **kwargs: _invalid_search_response(kwargs),
        },
    )()
    repo = RegistryRepository(SessionStub(), AsyncOpenSearchStub(raw_client=raw_client))
    ids, total = await repo.search_by_keyword(
        workspace_id=uuid4(),
        keyword="kyc",
        status=None,
        maturity_min=0,
        limit=5,
        offset=0,
        index_name="marketplace-agents",
    )
    assert ids == []
    assert total == 3


async def _search_response(raw_client, kwargs, profile_id):
    raw_client.calls.append(kwargs)
    return {
        "hits": {
            "total": {"value": 1},
            "hits": [
                {
                    "_id": str(profile_id),
                    "_source": {"agent_profile_id": str(profile_id)},
                }
            ],
        }
    }


async def _invalid_search_response(kwargs):
    del kwargs
    return {
        "hits": {
            "total": {"value": 3},
            "hits": [
                {"_source": {"agent_profile_id": 123}},
                {"_source": {"agent_profile_id": "not-a-uuid"}},
                {"_id": "still-not-a-uuid", "_source": {}},
            ],
        }
    }
