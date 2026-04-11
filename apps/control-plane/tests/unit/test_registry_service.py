from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from platform.common import database
from platform.common.exceptions import ObjectStorageError
from platform.registry.exceptions import (
    AgentNotFoundError,
    InvalidTransitionError,
    InvalidVisibilityPatternError,
    NamespaceConflictError,
    NamespaceNotFoundError,
    RegistryError,
    RevisionConflictError,
    WorkspaceAuthorizationError,
)
from platform.registry.models import AgentProfile, EmbeddingStatus, LifecycleStatus
from platform.registry.schemas import (
    AgentDiscoveryParams,
    AgentPatch,
    LifecycleTransitionRequest,
    MaturityUpdateRequest,
    NamespaceCreate,
)
from platform.registry.service import RegistryService, build_search_document
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from tests.registry_support import (
    AsyncOpenSearchStub,
    AsyncQdrantStub,
    ObjectStorageStub,
    RegistryRepoStub,
    SessionStub,
    WorkspacesServiceStub,
    build_namespace,
    build_profile,
    build_recording_producer,
    build_registry_settings,
    build_tar_package,
)


def _service(
    repo: RegistryRepoStub | None = None,
    *,
    object_storage: ObjectStorageStub | None = None,
    opensearch: AsyncOpenSearchStub | None = None,
    qdrant: AsyncQdrantStub | None = None,
    workspaces_service: WorkspacesServiceStub | None = None,
) -> tuple[
    RegistryService,
    RegistryRepoStub,
    ObjectStorageStub,
    AsyncOpenSearchStub,
    AsyncQdrantStub,
]:
    resolved_repo = repo or RegistryRepoStub()
    resolved_storage = object_storage or ObjectStorageStub()
    resolved_opensearch = opensearch or AsyncOpenSearchStub()
    resolved_qdrant = qdrant or AsyncQdrantStub()
    resolved_workspaces = workspaces_service or WorkspacesServiceStub()
    service = RegistryService(
        repository=resolved_repo,
        object_storage=resolved_storage,
        opensearch=resolved_opensearch,
        qdrant=resolved_qdrant,
        workspaces_service=resolved_workspaces,
        event_producer=build_recording_producer(),
        settings=build_registry_settings(),
    )
    return service, resolved_repo, resolved_storage, resolved_opensearch, resolved_qdrant


@pytest.mark.asyncio
async def test_namespace_flows_cover_create_list_delete_and_conflicts() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    workspaces = WorkspacesServiceStub(workspace_ids_by_user={actor_id: [workspace_id]})
    service, repo, _storage, _opensearch, _qdrant = _service(workspaces_service=workspaces)

    created = await service.create_namespace(
        workspace_id,
        NamespaceCreate(name="finance-ops", description=" Ops "),
        actor_id,
    )
    listed = await service.list_namespaces(workspace_id, actor_id)
    await service.delete_namespace(workspace_id, created.id, actor_id)

    assert created.name == "finance-ops"
    assert listed.total == 1
    with pytest.raises(NamespaceNotFoundError):
        await service.delete_namespace(workspace_id, created.id, actor_id)

    repo.namespaces_by_id[created.id] = build_namespace(
        namespace_id=created.id,
        workspace_id=workspace_id,
        created_by=actor_id,
        name="finance-ops",
    )
    repo.namespaces_by_name[(workspace_id, "finance-ops")] = repo.namespaces_by_id[created.id]
    with pytest.raises(NamespaceConflictError):
        await service.create_namespace(
            workspace_id,
            NamespaceCreate(name="finance-ops"),
            actor_id,
        )


@pytest.mark.asyncio
async def test_upload_agent_creates_profile_revision_indexes_and_publishes(monkeypatch) -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, created_by=actor_id, name="finance")
    workspaces = WorkspacesServiceStub(workspace_ids_by_user={actor_id: [workspace_id]})
    service, repo, storage, _opensearch, _qdrant = _service(workspaces_service=workspaces)
    repo.namespaces_by_id[namespace.id] = namespace
    repo.namespaces_by_name[(workspace_id, namespace.name)] = namespace
    dispatched: list[object] = []
    indexed: list[UUID] = []

    async def _fake_index(agent_profile_id):
        indexed.append(agent_profile_id)

    def _capture(coroutine):
        dispatched.append(coroutine)
        coroutine.close()

    monkeypatch.setattr(service, "_index_or_flag", _fake_index)
    monkeypatch.setattr(service, "_dispatch_background_task", _capture)

    response = await service.upload_agent(
        workspace_id,
        namespace.name,
        build_tar_package(),
        "agent.tar.gz",
        actor_id,
    )

    assert response.created is True
    assert response.agent_profile.fqn == "finance:kyc-verifier"
    assert len(repo.revisions_by_profile[response.agent_profile.id]) == 1
    assert storage.uploaded
    assert indexed == [response.agent_profile.id]
    assert len(dispatched) == 1
    assert [event["event_type"] for event in service.event_producer.events] == [
        "registry.agent.created"
    ]


@pytest.mark.asyncio
async def test_upload_agent_updates_existing_profile_and_cleans_up_on_conflict(
    monkeypatch,
) -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, created_by=actor_id, name="finance")
    repo = RegistryRepoStub()
    workspaces = WorkspacesServiceStub(workspace_ids_by_user={actor_id: [workspace_id]})
    service, resolved_repo, storage, _opensearch, _qdrant = _service(
        repo,
        workspaces_service=workspaces,
    )
    resolved_repo.namespaces_by_id[namespace.id] = namespace
    resolved_repo.namespaces_by_name[(workspace_id, namespace.name)] = namespace
    existing = build_profile(workspace_id=workspace_id, namespace=namespace)
    resolved_repo.profiles_by_id[existing.id] = existing
    resolved_repo.profiles_by_fqn[(workspace_id, existing.fqn)] = existing
    monkeypatch.setattr(service, "_index_or_flag", lambda *_args, **_kwargs: _async_none())
    monkeypatch.setattr(service, "_dispatch_background_task", lambda coroutine: coroutine.close())

    updated = await service.upload_agent(
        workspace_id,
        namespace.name,
        build_tar_package(
            manifest_payload={
                "local_name": "kyc-verifier",
                "version": "1.0.1",
                "purpose": "Valid purpose for second upload.",
                "role_types": ["executor"],
                "tags": ["kyc"],
            }
        ),
        "agent.tar.gz",
        actor_id,
    )

    assert updated.created is False
    assert len(resolved_repo.revisions_by_profile[existing.id]) == 1

    async def _raise_conflict(**kwargs):
        raise IntegrityError("insert", {}, Exception("uq_registry_revision_profile_version"))

    monkeypatch.setattr(resolved_repo, "insert_revision", _raise_conflict)

    with pytest.raises(RevisionConflictError):
        await service.upload_agent(
            workspace_id,
            namespace.name,
            build_tar_package(),
            "agent.tar.gz",
            actor_id,
        )

    assert storage.deleted


@pytest.mark.asyncio
async def test_get_resolve_and_list_agents_apply_visibility() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    requester_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, created_by=actor_id, name="finance")
    visible = build_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        local_name="planner",
        status=LifecycleStatus.published,
    )
    hidden = build_profile(
        workspace_id=workspace_id,
        namespace=build_namespace(workspace_id=workspace_id, name="ops"),
        local_name="runner",
        status=LifecycleStatus.published,
    )
    requester = build_profile(
        profile_id=requester_id,
        workspace_id=workspace_id,
        namespace=namespace,
        local_name="requester",
        visibility_agents=["finance:*"],
        status=LifecycleStatus.published,
    )
    repo = RegistryRepoStub()
    for profile in (visible, hidden, requester):
        repo.profiles_by_id[profile.id] = profile
        repo.profiles_by_fqn[(workspace_id, profile.fqn)] = profile
    repo.revisions_by_profile[visible.id] = []
    repo.revisions_by_profile[hidden.id] = []
    repo.revisions_by_profile[requester.id] = []
    workspaces = WorkspacesServiceStub(
        workspace_ids_by_user={actor_id: [workspace_id]},
        visibility_by_workspace={
            workspace_id: SimpleNamespace(
                visibility_agents=["shared:*"],
                visibility_tools=[],
            )
        },
    )
    service, _repo, _storage, _opensearch, _qdrant = _service(repo, workspaces_service=workspaces)

    fetched = await service.get_agent(
        workspace_id,
        visible.id,
        actor_id=actor_id,
        requesting_agent_id=requester_id,
    )
    resolved = await service.resolve_fqn(
        visible.fqn,
        workspace_id=workspace_id,
        actor_id=actor_id,
        requesting_agent_id=requester_id,
    )
    listed = await service.list_agents(
        AgentDiscoveryParams(
            workspace_id=workspace_id,
            fqn_pattern="finance:*",
            limit=10,
            offset=0,
        ),
        actor_id=actor_id,
        requesting_agent_id=requester_id,
    )

    assert fetched.id == visible.id
    assert resolved.id == visible.id
    assert [item.id for item in listed.items] == [visible.id, requester.id]
    with pytest.raises(AgentNotFoundError):
        await service.get_agent(
            workspace_id,
            hidden.id,
            actor_id=actor_id,
            requesting_agent_id=requester_id,
        )


@pytest.mark.asyncio
async def test_patch_transition_maturity_and_audit_flows() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, created_by=actor_id)
    profile = build_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        status=LifecycleStatus.draft,
    )
    repo = RegistryRepoStub()
    repo.profiles_by_id[profile.id] = profile
    repo.profiles_by_fqn[(workspace_id, profile.fqn)] = profile
    workspaces = WorkspacesServiceStub(workspace_ids_by_user={actor_id: [workspace_id]})
    service, _repo, _storage, _opensearch, _qdrant = _service(repo, workspaces_service=workspaces)
    repo.revisions_by_profile[profile.id] = []

    patched = await service.patch_agent(
        workspace_id,
        profile.id,
        AgentPatch(
            display_name="Updated",
            visibility_agents=["finance:*"],
            visibility_tools=["tools:*"],
            role_types=["custom"],
            custom_role_description="Owns orchestration",
        ),
        actor_id,
    )
    transitioned = await service.transition_lifecycle(
        workspace_id,
        profile.id,
        LifecycleTransitionRequest(target_status=LifecycleStatus.validated, reason="reviewed"),
        actor_id,
    )
    matured = await service.update_maturity(
        workspace_id,
        profile.id,
        MaturityUpdateRequest(maturity_level=2, reason="certified"),
        actor_id,
    )
    audit = await service.list_lifecycle_audit(workspace_id, profile.id, actor_id)

    assert patched.display_name == "Updated"
    assert transitioned.status == LifecycleStatus.validated
    assert matured.maturity_level == 2
    assert audit.total == 1
    with pytest.raises(InvalidVisibilityPatternError):
        await service.patch_agent(
            workspace_id,
            profile.id,
            AgentPatch(visibility_agents=["("]),
            actor_id,
        )
    with pytest.raises(InvalidTransitionError):
        await service.transition_lifecycle(
            workspace_id,
            profile.id,
            LifecycleTransitionRequest(target_status=LifecycleStatus.archived),
            actor_id,
        )


@pytest.mark.asyncio
async def test_list_revisions_get_agent_by_fqn_and_workspace_authz_guards() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, created_by=actor_id)
    profile = build_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        status=LifecycleStatus.published,
    )
    repo = RegistryRepoStub()
    repo.profiles_by_id[profile.id] = profile
    repo.profiles_by_fqn[(workspace_id, profile.fqn)] = profile
    repo.revisions_by_profile[profile.id] = [build_tar_revision(profile)]
    service, _repo, _storage, _opensearch, _qdrant = _service(
        repo,
        workspaces_service=WorkspacesServiceStub(workspace_ids_by_user={actor_id: [workspace_id]}),
    )

    revisions = await service.list_revisions(workspace_id, profile.id, actor_id)
    fetched = await service.get_agent_by_fqn(profile.fqn, workspace_id)

    assert len(revisions) == 1
    assert fetched is not None

    with pytest.raises(WorkspaceAuthorizationError):
        await service.list_namespaces(workspace_id, uuid4())

    archived = build_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        local_name="archived",
        status=LifecycleStatus.archived,
    )
    repo.profiles_by_id[archived.id] = archived
    repo.profiles_by_fqn[(workspace_id, archived.fqn)] = archived
    assert await service.get_agent_by_fqn(archived.fqn, workspace_id) is None


@pytest.mark.asyncio
async def test_index_or_flag_and_extract_embedding_paths(monkeypatch) -> None:
    workspace_id = uuid4()
    profile = build_profile(workspace_id=workspace_id, status=LifecycleStatus.published)
    repo = RegistryRepoStub()
    repo.profiles_by_id[profile.id] = profile
    repo.profiles_by_fqn[(workspace_id, profile.fqn)] = profile
    repo.session.get_results[(AgentProfile, profile.id)] = profile
    repo.revisions_by_profile[profile.id] = [build_tar_revision(profile)]
    opensearch = AsyncOpenSearchStub()
    service, _repo, _storage, _opensearch, _qdrant = _service(repo, opensearch=opensearch)

    await service._index_or_flag(profile.id)
    assert profile.needs_reindex is False
    assert opensearch.indexed

    failing_opensearch = AsyncOpenSearchStub(fail_index=RuntimeError("boom"))
    failing_service, failing_repo, _storage, _opensearch, _qdrant = _service(
        repo,
        opensearch=failing_opensearch,
    )
    await failing_service._index_or_flag(profile.id)
    assert failing_repo.profiles_by_id[profile.id].needs_reindex is True

    assert service._extract_embedding({"embedding": [1, 2.5]}) == [1.0, 2.5]
    assert service._extract_embedding({"data": [{"embedding": [3, 4]}]}) == [3.0, 4.0]
    with pytest.raises(RegistryError):
        service._extract_embedding({"data": []})


@pytest.mark.asyncio
async def test_generate_embedding_async_success_and_failure(monkeypatch) -> None:
    workspace_id = uuid4()
    profile = build_profile(workspace_id=workspace_id, status=LifecycleStatus.published)
    session = SessionStub(get_results={(AgentProfile, profile.id): profile})
    qdrant = AsyncQdrantStub()
    service, _repo, _storage, _opensearch, _qdrant = _service(qdrant=qdrant)

    @asynccontextmanager
    async def _session_factory():
        yield session

    class SuccessClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            del url, json
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {"embedding": [0.1, 0.2]},
            )

    monkeypatch.setattr(database, "AsyncSessionLocal", _session_factory)
    monkeypatch.setattr(
        "platform.registry.service.httpx.AsyncClient",
        lambda timeout: SuccessClient(),
    )

    await service._generate_embedding_async(profile.id)

    assert qdrant.upserts
    assert session.commit_calls == 1
    assert profile.embedding_status == EmbeddingStatus.complete

    session_fail = SessionStub(get_results={(AgentProfile, profile.id): profile})

    @asynccontextmanager
    async def _failing_session_factory():
        yield session_fail

    class FailingClient(SuccessClient):
        async def post(self, url, json):
            del url, json
            raise RuntimeError("embedding service down")

    monkeypatch.setattr(database, "AsyncSessionLocal", _failing_session_factory)
    monkeypatch.setattr(
        "platform.registry.service.httpx.AsyncClient",
        lambda timeout: FailingClient(),
    )

    await service._generate_embedding_async(profile.id)

    assert profile.embedding_status == EmbeddingStatus.failed
    assert session_fail.commit_calls == 1


@pytest.mark.asyncio
async def test_build_search_document_and_internal_helpers() -> None:
    profile = build_profile(status=LifecycleStatus.published)
    revision = build_tar_revision(profile)
    service, _repo, _storage, _opensearch, _qdrant = _service()

    document = build_search_document(profile, revision)

    assert document["fqn"] == profile.fqn
    assert document["current_version"] == revision.version
    assert service._dedupe(["a", "b", "a"]) == ["a", "b"]
    correlation = service._correlation(profile.workspace_id)
    assert correlation.workspace_id == profile.workspace_id


@pytest.mark.asyncio
async def test_service_namespace_and_upload_failure_branches() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, created_by=actor_id, name="finance")
    repo = RegistryRepoStub()
    repo.namespaces_by_id[namespace.id] = namespace
    repo.namespaces_by_name[(workspace_id, namespace.name)] = namespace
    service, _repo, storage, _opensearch, _qdrant = _service(
        repo,
        workspaces_service=WorkspacesServiceStub(workspace_ids_by_user={actor_id: [workspace_id]}),
    )

    profile = build_profile(workspace_id=workspace_id, namespace=namespace)
    repo.profiles_by_id[profile.id] = profile
    repo.profiles_by_fqn[(workspace_id, profile.fqn)] = profile
    with pytest.raises(RegistryError) as namespace_exc:
        await service.delete_namespace(workspace_id, namespace.id, actor_id)
    assert namespace_exc.value.code == "REGISTRY_NAMESPACE_NOT_EMPTY"

    with pytest.raises(NamespaceNotFoundError):
        await service.upload_agent(
            workspace_id,
            "missing",
            build_tar_package(),
            "agent.tar.gz",
            actor_id,
        )

    storage.fail_upload = ObjectStorageError("minio down")
    with pytest.raises(RegistryError) as store_exc:
        await service.upload_agent(
            workspace_id,
            namespace.name,
            build_tar_package(),
            "agent.tar.gz",
            actor_id,
        )
    assert store_exc.value.code == "REGISTRY_STORE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_service_upload_handles_fqn_conflict_and_generic_failure(monkeypatch) -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, created_by=actor_id, name="finance")
    repo = RegistryRepoStub()
    repo.namespaces_by_id[namespace.id] = namespace
    repo.namespaces_by_name[(workspace_id, namespace.name)] = namespace
    service, _repo, storage, _opensearch, _qdrant = _service(
        repo,
        workspaces_service=WorkspacesServiceStub(workspace_ids_by_user={actor_id: [workspace_id]}),
    )
    monkeypatch.setattr(service, "_dispatch_background_task", lambda coroutine: coroutine.close())
    monkeypatch.setattr(service, "_index_or_flag", lambda *_args, **_kwargs: _async_none())

    async def _raise_fqn_conflict(**kwargs):
        raise IntegrityError("insert", {}, Exception("uq_registry_profile_fqn"))

    monkeypatch.setattr(repo, "insert_revision", _raise_fqn_conflict)
    with pytest.raises(RegistryError) as fqn_exc:
        await service.upload_agent(
            workspace_id,
            namespace.name,
            build_tar_package(),
            "agent.tar.gz",
            actor_id,
        )
    assert fqn_exc.value.code == "REGISTRY_FQN_CONFLICT"
    assert storage.deleted

    async def _raise_runtime(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(repo, "insert_revision", _raise_runtime)
    with pytest.raises(RuntimeError):
        await service.upload_agent(
            workspace_id,
            namespace.name,
            build_tar_package(),
            "agent.tar.gz",
            actor_id,
        )


@pytest.mark.asyncio
async def test_service_resolution_listing_and_transition_branches(monkeypatch) -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, created_by=actor_id, name="finance")
    validated = build_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        local_name="validated",
        status=LifecycleStatus.validated,
    )
    published = build_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        local_name="published",
        status=LifecycleStatus.published,
    )
    repo = RegistryRepoStub()
    for profile in (validated, published):
        repo.profiles_by_id[profile.id] = profile
        repo.profiles_by_fqn[(workspace_id, profile.fqn)] = profile
        repo.revisions_by_profile[profile.id] = [build_tar_revision(profile)]
    repo.keyword_ids = [published.id]
    repo.keyword_total = 1
    service, _repo, _storage, _opensearch, _qdrant = _service(
        repo,
        workspaces_service=WorkspacesServiceStub(workspace_ids_by_user={actor_id: [workspace_id]}),
    )
    monkeypatch.setattr(service, "_dispatch_background_task", lambda coroutine: coroutine.close())

    keyword_results = await service.list_agents(
        AgentDiscoveryParams(
            workspace_id=workspace_id,
            keyword="kyc",
            limit=10,
            offset=0,
        ),
        actor_id=None,
        requesting_agent_id=None,
    )
    published_result = await service.transition_lifecycle(
        workspace_id,
        validated.id,
        LifecycleTransitionRequest(target_status=LifecycleStatus.published),
        actor_id,
    )
    deprecated_result = await service.transition_lifecycle(
        workspace_id,
        published.id,
        LifecycleTransitionRequest(
            target_status=LifecycleStatus.deprecated,
            reason="superseded",
        ),
        actor_id,
    )

    assert keyword_results.total == 1
    assert published_result.status == LifecycleStatus.published
    assert deprecated_result.status == LifecycleStatus.deprecated
    assert [event["event_type"] for event in service.event_producer.events] == [
        "registry.agent.published",
        "registry.agent.deprecated",
    ]
    with pytest.raises(RegistryError):
        await service.list_agents(AgentDiscoveryParams(workspace_id=None))
    with pytest.raises(AgentNotFoundError):
        await service.get_agent(workspace_id, uuid4(), actor_id=None, requesting_agent_id=None)
    with pytest.raises(AgentNotFoundError):
        await service.resolve_fqn(
            "missing:agent",
            workspace_id=workspace_id,
            actor_id=None,
            requesting_agent_id=None,
        )


@pytest.mark.asyncio
async def test_service_misc_branches_and_internal_helpers(monkeypatch) -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, created_by=actor_id)
    profile = build_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        status=LifecycleStatus.published,
    )
    repo = RegistryRepoStub()
    repo.profiles_by_id[profile.id] = profile
    repo.profiles_by_fqn[(workspace_id, profile.fqn)] = profile
    repo.revisions_by_profile[profile.id] = []
    service, _repo, _storage, _opensearch, _qdrant = _service(
        repo,
        workspaces_service=WorkspacesServiceStub(workspace_ids_by_user={actor_id: [workspace_id]}),
    )

    no_update = AgentPatch.model_construct()
    no_update.__pydantic_fields_set__ = set()
    unchanged = await service.patch_agent(workspace_id, profile.id, no_update, actor_id)
    approach_update = await service.patch_agent(
        workspace_id,
        profile.id,
        AgentPatch(approach="Updated", tags=["tag"], visibility_tools=["tools:*"]),
        actor_id,
    )
    same_maturity = await service.update_maturity(
        workspace_id,
        profile.id,
        MaturityUpdateRequest(maturity_level=profile.maturity_level),
        actor_id,
    )
    no_visibility = await _service(
        repo,
        workspaces_service=None,
    )[0]._get_workspace_visibility(workspace_id)
    service_missing_getter = _service(repo, workspaces_service=SimpleNamespace())[0]
    missing_getter = await service_missing_getter._get_workspace_visibility(workspace_id)
    response_none = await _service(
        repo,
        workspaces_service=WorkspacesServiceStub(
            workspace_ids_by_user={actor_id: [workspace_id]},
            visibility_by_workspace={workspace_id: None},
        ),
    )[0]._get_workspace_visibility(workspace_id)

    task_done = asyncio.Event()

    async def _done() -> None:
        task_done.set()

    service._dispatch_background_task(_done())
    await asyncio.wait_for(task_done.wait(), timeout=1.0)
    await asyncio.sleep(0)

    assert unchanged.id == profile.id
    assert approach_update.approach == "Updated"
    assert same_maturity.maturity_level == profile.maturity_level
    assert no_visibility.agent_patterns == []
    assert missing_getter.tool_patterns == []
    assert response_none.agent_patterns == []
    assert service._background_tasks == set()
    await service._assert_agent_visible(profile, workspace_id, None)
    service_without_workspace_access = _service(repo, workspaces_service=None)[0]
    with pytest.raises(WorkspaceAuthorizationError):
        await service_without_workspace_access._assert_workspace_access(workspace_id, actor_id)
    with pytest.raises(AgentNotFoundError):
        await service._get_agent_or_raise(workspace_id, uuid4())

    empty_session_service, empty_repo, _storage, _opensearch, _qdrant = _service(repo)
    empty_repo.session.get_results.clear()
    await empty_session_service._index_or_flag(uuid4())

    session = SessionStub()

    @asynccontextmanager
    async def _session_factory():
        yield session

    monkeypatch.setattr(database, "AsyncSessionLocal", _session_factory)
    await service._generate_embedding_async(uuid4())

    service.repository.session = SimpleNamespace()
    await service._commit()
    await service._rollback()


def build_tar_revision(profile):
    from tests.registry_support import build_revision

    return build_revision(agent_profile=profile)


async def _async_none() -> None:
    return None
