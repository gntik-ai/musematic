from __future__ import annotations

from datetime import UTC, datetime
from platform.context_engineering.adapters import (
    ConnectorPayloadsAdapter,
    ContextFetchRequest,
    ConversationHistoryAdapter,
    LongTermMemoryAdapter,
    ReasoningTracesAdapter,
    SystemInstructionsAdapter,
    ToolOutputsAdapter,
    WorkflowStateAdapter,
    WorkspaceGoalHistoryAdapter,
    WorkspaceMetadataAdapter,
    _classification_from_item,
    _coerce_datetime,
    _content_from_item,
    _metadata_from_item,
    _normalize_items,
    _origin_from_item,
    _token_count_from_content,
    build_default_adapters,
)
from platform.context_engineering.exceptions import ContextSourceUnavailableError
from platform.context_engineering.models import ContextSourceType
from platform.context_engineering.schemas import SourceConfig
from types import SimpleNamespace
from uuid import uuid4

import pytest


def _request(
    source_type: ContextSourceType,
    *,
    goal_id=None,
    max_elements: int = 2,
) -> ContextFetchRequest:
    return ContextFetchRequest(
        execution_id=uuid4(),
        step_id=uuid4(),
        workspace_id=uuid4(),
        agent_fqn="finance:agent",
        goal_id=goal_id,
        task_brief="retry payment",
        source_config=SourceConfig(
            source_type=source_type,
            priority=50,
            enabled=True,
            max_elements=max_elements,
        ),
    )


def test_adapter_helpers_normalize_structured_items() -> None:
    now = datetime.now(UTC)

    assert _coerce_datetime("bad-date").tzinfo is UTC
    assert _coerce_datetime(now.replace(tzinfo=None)).tzinfo is UTC
    assert _content_from_item({"message": "  hello  "}) == "hello"
    assert _content_from_item({"value": 3}) == "{'value': 3}"
    assert _origin_from_item({"id": "42"}, "conversation") == "conversation:42"
    assert _origin_from_item({"origin": "custom:7"}, "conversation") == "custom:7"
    assert _origin_from_item({}, "conversation") == "conversation"
    assert _metadata_from_item({"metadata": {"score": 0.9}}) == {"score": 0.9}
    assert _metadata_from_item({"metadata": "bad"}) == {}
    assert _classification_from_item({"classification": " Internal "}) == "internal"
    assert _token_count_from_content("alpha beta", {"token_count": 7}) == 7
    assert _token_count_from_content("alpha beta", {}) == 2

    items = [
        "",
        {
            "id": "b",
            "content": "second",
            "created_at": now.isoformat(),
            "metadata": {"score": 0.3},
            "classification": "confidential",
        },
        SimpleNamespace(
            id="a",
            content="first",
            created_at=now,
            metadata={"score": 0.7},
            data_classification="public",
            token_count=3,
        ),
    ]
    normalized = _normalize_items(
        source_type=ContextSourceType.tool_outputs,
        items=items,
        request=_request(ContextSourceType.tool_outputs),
        origin_prefix="tool",
        authority_score=0.9,
    )

    assert [item.provenance.origin for item in normalized] == ["tool:a", "tool:b"]
    assert normalized[0].token_count == 3
    assert normalized[1].data_classification == "confidential"


@pytest.mark.asyncio
async def test_system_instructions_adapter_supports_multiple_registry_shapes() -> None:
    request = _request(ContextSourceType.system_instructions)
    agent = SimpleNamespace(
        purpose="Resolve incidents",
        approach="Be deterministic",
        role_types=["executor"],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    class GetByAltName:
        async def get_agent_by_fqn(self, workspace_id, agent_fqn):
            del workspace_id, agent_fqn
            return agent

    class ResolveFqn:
        async def resolve_fqn(self, agent_fqn, **kwargs):
            del agent_fqn, kwargs
            return agent

    class DirectLookup:
        async def get_by_fqn(self, workspace_id, agent_fqn):
            del workspace_id, agent_fqn
            return None

    direct = await SystemInstructionsAdapter(GetByAltName()).fetch(request)
    resolved = await SystemInstructionsAdapter(ResolveFqn()).fetch(request)
    empty = await SystemInstructionsAdapter(DirectLookup()).fetch(request)

    assert direct[0].metadata["role_types"] == ["executor"]
    assert resolved[0].content.startswith("Purpose:")
    assert empty == []

    with pytest.raises(ContextSourceUnavailableError):
        await SystemInstructionsAdapter(None).fetch(request)


@pytest.mark.asyncio
async def test_source_adapters_cover_success_empty_and_error_paths() -> None:
    now = datetime.now(UTC)

    class WorkflowByMethod:
        async def get_workflow_state(self, execution_id, step_id):
            del execution_id, step_id
            return {"id": "wf-1", "content": "workflow", "created_at": now}

    class HistoryByAltMethod:
        async def list_conversation_history(self, execution_id, step_id, *, limit):
            del execution_id, step_id, limit
            return [{"id": "c-1", "text": "history", "created_at": now}]

    class MemorySearch:
        async def search_agent_memory(self, **kwargs):
            del kwargs
            return [
                {
                    "id": "m-1",
                    "content": "memory",
                    "metadata": {"score": 0.8},
                    "created_at": now,
                }
            ]

    class ToolOutputs:
        async def get_tool_outputs(self, execution_id, step_id):
            del execution_id, step_id
            return [{"id": "t-1", "content": "tool output", "created_at": now}]

        async def get_reasoning_traces(self, execution_id, step_id):
            del execution_id, step_id
            return [{"id": "r-1", "content": "reasoning", "created_at": now}]

    class Connectors:
        async def get_connector_payloads(self, execution_id, step_id):
            del execution_id, step_id
            return [{"id": "p-1", "content": "connector", "created_at": now}]

    class WorkspacesByMethod:
        async def get_workspace_metadata(self, workspace_id):
            del workspace_id
            return SimpleNamespace(name="Finance", description="Payments", updated_at=now)

        async def get_goal_by_gid(self, goal_id):
            del goal_id
            return SimpleNamespace(
                title="Reduce retries",
                description="Improve incident handling",
                status="open",
                updated_at=now,
            )

    class MissingMethods:
        pass

    workflow = await WorkflowStateAdapter(WorkflowByMethod()).fetch(
        _request(ContextSourceType.workflow_state)
    )
    history = await ConversationHistoryAdapter(HistoryByAltMethod()).fetch(
        _request(ContextSourceType.conversation_history)
    )
    memory = await LongTermMemoryAdapter(MemorySearch()).fetch(
        _request(ContextSourceType.long_term_memory)
    )
    tool_outputs = await ToolOutputsAdapter(ToolOutputs()).fetch(
        _request(ContextSourceType.tool_outputs)
    )
    connectors = await ConnectorPayloadsAdapter(Connectors()).fetch(
        _request(ContextSourceType.connector_payloads)
    )
    workspace = await WorkspaceMetadataAdapter(WorkspacesByMethod()).fetch(
        _request(ContextSourceType.workspace_metadata)
    )
    reasoning = await ReasoningTracesAdapter(ToolOutputs()).fetch(
        _request(ContextSourceType.reasoning_traces)
    )
    goal = await WorkspaceGoalHistoryAdapter(WorkspacesByMethod()).fetch(
        _request(ContextSourceType.workspace_goal_history, goal_id=uuid4())
    )
    no_goal = await WorkspaceGoalHistoryAdapter(WorkspacesByMethod()).fetch(
        _request(ContextSourceType.workspace_goal_history)
    )

    assert workflow[0].content == "workflow"
    assert history[0].content == "history"
    assert memory[0].metadata["relevance_score"] == 0.8
    assert tool_outputs[0].content == "tool output"
    assert connectors[0].content == "connector"
    assert workspace[0].content.startswith("Workspace:")
    assert reasoning[0].content == "reasoning"
    assert goal[0].provenance.origin.startswith("goal:")
    assert no_goal == []

    with pytest.raises(ContextSourceUnavailableError):
        await WorkflowStateAdapter(MissingMethods()).fetch(
            _request(ContextSourceType.workflow_state)
        )
    with pytest.raises(ContextSourceUnavailableError):
        await ConversationHistoryAdapter(MissingMethods()).fetch(
            _request(ContextSourceType.conversation_history)
        )
    with pytest.raises(ContextSourceUnavailableError):
        await LongTermMemoryAdapter(MissingMethods()).fetch(
            _request(ContextSourceType.long_term_memory)
        )
    with pytest.raises(ContextSourceUnavailableError):
        await ToolOutputsAdapter(MissingMethods()).fetch(_request(ContextSourceType.tool_outputs))
    with pytest.raises(ContextSourceUnavailableError):
        await ConnectorPayloadsAdapter(MissingMethods()).fetch(
            _request(ContextSourceType.connector_payloads)
        )
    with pytest.raises(ContextSourceUnavailableError):
        await WorkspaceMetadataAdapter(MissingMethods()).fetch(
            _request(ContextSourceType.workspace_metadata)
        )
    with pytest.raises(ContextSourceUnavailableError):
        await ReasoningTracesAdapter(MissingMethods()).fetch(
            _request(ContextSourceType.reasoning_traces)
        )
    with pytest.raises(ContextSourceUnavailableError):
        await WorkspaceGoalHistoryAdapter(MissingMethods()).fetch(
            _request(ContextSourceType.workspace_goal_history, goal_id=uuid4())
        )


def test_build_default_adapters_registers_all_context_sources() -> None:
    adapters = build_default_adapters()

    assert set(adapters) == set(ContextSourceType)


@pytest.mark.asyncio
async def test_adapters_cover_none_services_and_empty_payloads() -> None:
    request = _request(ContextSourceType.workspace_goal_history, goal_id=uuid4())

    class EmptyRegistry:
        async def get_by_fqn(self, workspace_id, agent_fqn):
            del workspace_id, agent_fqn
            return None

    class EmptyWorkspaceRepo:
        async def get_workspace_by_id_any(self, workspace_id):
            del workspace_id
            return None

        async def get_goal_by_gid(self, goal_id):
            del goal_id
            return None

    assert await SystemInstructionsAdapter(EmptyRegistry()).fetch(
        _request(ContextSourceType.system_instructions)
    ) == []
    assert await WorkspaceMetadataAdapter(SimpleNamespace(repo=EmptyWorkspaceRepo())).fetch(
        _request(ContextSourceType.workspace_metadata)
    ) == []
    assert await WorkspaceGoalHistoryAdapter(SimpleNamespace(repo=EmptyWorkspaceRepo())).fetch(
        request
    ) == []

    with pytest.raises(ContextSourceUnavailableError):
        await WorkflowStateAdapter(None).fetch(_request(ContextSourceType.workflow_state))
    with pytest.raises(ContextSourceUnavailableError):
        await ConversationHistoryAdapter(None).fetch(
            _request(ContextSourceType.conversation_history)
        )
    with pytest.raises(ContextSourceUnavailableError):
        await LongTermMemoryAdapter(None).fetch(_request(ContextSourceType.long_term_memory))
    with pytest.raises(ContextSourceUnavailableError):
        await ToolOutputsAdapter(None).fetch(_request(ContextSourceType.tool_outputs))
    with pytest.raises(ContextSourceUnavailableError):
        await ConnectorPayloadsAdapter(None).fetch(_request(ContextSourceType.connector_payloads))
    with pytest.raises(ContextSourceUnavailableError):
        await WorkspaceMetadataAdapter(None).fetch(_request(ContextSourceType.workspace_metadata))
    with pytest.raises(ContextSourceUnavailableError):
        await ReasoningTracesAdapter(None).fetch(_request(ContextSourceType.reasoning_traces))
    with pytest.raises(ContextSourceUnavailableError):
        await WorkspaceGoalHistoryAdapter(None).fetch(request)
