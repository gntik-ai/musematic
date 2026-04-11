from __future__ import annotations

from platform.registry.exceptions import InvalidVisibilityPatternError
from platform.registry.service import (
    RegistryService,
    compile_fqn_pattern,
    filter_profiles_by_patterns,
    fqn_matches,
)
from uuid import uuid4

import pytest

from tests.registry_support import (
    AsyncOpenSearchStub,
    AsyncQdrantStub,
    ObjectStorageStub,
    RegistryRepoStub,
    WorkspacesServiceStub,
    build_namespace,
    build_profile,
    build_registry_settings,
)


def _service(
    repo: RegistryRepoStub,
    workspaces_service: WorkspacesServiceStub,
) -> RegistryService:
    return RegistryService(
        repository=repo,
        object_storage=ObjectStorageStub(),
        opensearch=AsyncOpenSearchStub(),
        qdrant=AsyncQdrantStub(),
        workspaces_service=workspaces_service,
        event_producer=None,
        settings=build_registry_settings(),
    )


def test_fqn_pattern_helpers_cover_wildcards_and_regex() -> None:
    assert compile_fqn_pattern("finance:*").fullmatch("finance:planner") is not None
    assert fqn_matches("^finance:[a-z-]+$", "finance:planner") is True
    assert fqn_matches("finance:*", "ops:planner") is False
    assert fqn_matches("*", "anything:anywhere") is True


def test_filter_profiles_by_patterns_handles_empty_and_wildcard() -> None:
    namespace = build_namespace(name="finance")
    first = build_profile(namespace=namespace, local_name="planner")
    second = build_profile(namespace=build_namespace(name="ops"), local_name="runner")

    assert filter_profiles_by_patterns([first, second], []) == []
    assert filter_profiles_by_patterns([first, second], ["*"]) == [first, second]
    assert filter_profiles_by_patterns([first, second], ["finance:*"]) == [first]


def test_invalid_visibility_pattern_raises() -> None:
    with pytest.raises(InvalidVisibilityPatternError):
        compile_fqn_pattern("(")


@pytest.mark.asyncio
async def test_resolve_effective_visibility_unions_agent_and_workspace_patterns() -> None:
    workspace_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, name="finance")
    profile = build_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        visibility_agents=["finance:*"],
        visibility_tools=["tools:csv-reader"],
    )
    repo = RegistryRepoStub()
    repo.profiles_by_id[profile.id] = profile
    repo.profiles_by_fqn[(workspace_id, profile.fqn)] = profile
    workspaces_service = WorkspacesServiceStub(
        visibility_by_workspace={
            workspace_id: type(
                "VisibilityGrant",
                (),
                {
                    "visibility_agents": ["ops:*", "finance:*"],
                    "visibility_tools": ["tools:db"],
                },
            )()
        }
    )

    effective = await _service(repo, workspaces_service).resolve_effective_visibility(
        profile.id,
        workspace_id,
    )

    assert effective.agent_patterns == ["finance:*", "ops:*"]
    assert effective.tool_patterns == ["tools:csv-reader", "tools:db"]
