from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from platform.context_engineering.exceptions import ContextSourceUnavailableError
from platform.context_engineering.models import ContextSourceType
from platform.context_engineering.schemas import (
    ContextElement,
    ContextProvenanceEntry,
    SourceConfig,
)
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ContextFetchRequest:
    execution_id: UUID
    step_id: UUID
    workspace_id: UUID
    agent_fqn: str
    goal_id: UUID | None
    task_brief: str
    source_config: SourceConfig


class ContextSourceAdapter(Protocol):
    source_type: ContextSourceType

    async def fetch(self, request: ContextFetchRequest) -> list[ContextElement]: ...


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(UTC)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _extract(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _content_from_item(item: Any) -> str:
    for field in ("content", "message", "text", "summary", "description", "value"):
        value = _extract(item, field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(item).strip()
    return str(item).strip()


def _origin_from_item(item: Any, prefix: str) -> str:
    explicit = _extract(item, "origin")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    identifier = _extract(item, "id") or _extract(item, "gid") or _extract(item, "name")
    if identifier is None:
        return prefix
    return f"{prefix}:{identifier}"


def _metadata_from_item(item: Any) -> dict[str, Any]:
    metadata = _extract(item, "metadata", {})
    if isinstance(metadata, dict):
        return dict(metadata)
    return {}


def _classification_from_item(item: Any) -> str:
    classification = _extract(item, "data_classification") or _extract(item, "classification")
    if isinstance(classification, str) and classification.strip():
        return classification.strip().lower()
    return "public"


def _token_count_from_content(content: str, item: Any) -> int:
    existing = _extract(item, "token_count")
    if isinstance(existing, int) and existing >= 0:
        return existing
    return max(1, len(content.split()))


def _build_element(
    *,
    source_type: ContextSourceType,
    priority: int,
    content: str,
    origin: str,
    timestamp: datetime,
    authority_score: float,
    policy_justification: str,
    metadata: dict[str, Any] | None = None,
    data_classification: str = "public",
    token_count: int | None = None,
) -> ContextElement:
    return ContextElement(
        source_type=source_type,
        content=content,
        token_count=token_count if token_count is not None else max(1, len(content.split())),
        priority=priority,
        provenance=ContextProvenanceEntry(
            origin=origin,
            timestamp=timestamp,
            authority_score=authority_score,
            policy_justification=policy_justification,
        ),
        metadata=metadata or {},
        data_classification=data_classification,
    )


def _normalize_items(
    *,
    source_type: ContextSourceType,
    items: list[Any],
    request: ContextFetchRequest,
    origin_prefix: str,
    authority_score: float,
) -> list[ContextElement]:
    sorted_items = sorted(
        items,
        key=lambda item: (
            _coerce_datetime(
                _extract(item, "timestamp")
                or _extract(item, "created_at")
                or _extract(item, "updated_at")
                or _extract(item, "occurred_at")
            ),
            str(_extract(item, "id", "")),
        ),
    )
    elements: list[ContextElement] = []
    for item in sorted_items[: request.source_config.max_elements]:
        content = _content_from_item(item)
        if not content:
            continue
        elements.append(
            _build_element(
                source_type=source_type,
                priority=request.source_config.priority,
                content=content,
                origin=_origin_from_item(item, origin_prefix),
                timestamp=_coerce_datetime(
                    _extract(item, "timestamp")
                    or _extract(item, "created_at")
                    or _extract(item, "updated_at")
                    or _extract(item, "occurred_at")
                ),
                authority_score=authority_score,
                policy_justification="included: source enabled by resolved profile",
                metadata=_metadata_from_item(item),
                data_classification=_classification_from_item(item),
                token_count=_token_count_from_content(content, item),
            )
        )
    return elements


class SystemInstructionsAdapter:
    source_type = ContextSourceType.system_instructions

    def __init__(self, registry_service: Any | None) -> None:
        self.registry_service = registry_service

    async def fetch(self, request: ContextFetchRequest) -> list[ContextElement]:
        if self.registry_service is None:
            raise ContextSourceUnavailableError(
                self.source_type.value, "Registry service unavailable"
            )
        try:
            if hasattr(self.registry_service, "get_by_fqn"):
                agent = await self.registry_service.get_by_fqn(
                    request.workspace_id, request.agent_fqn
                )
            elif hasattr(self.registry_service, "get_agent_by_fqn"):
                agent = await self.registry_service.get_agent_by_fqn(
                    request.workspace_id,
                    request.agent_fqn,
                )
            elif hasattr(self.registry_service, "resolve_fqn"):
                agent = await self.registry_service.resolve_fqn(
                    request.agent_fqn,
                    workspace_id=request.workspace_id,
                    actor_id=None,
                    requesting_agent_id=None,
                )
            else:
                raise AttributeError("Registry service does not expose an FQN resolver")
        except Exception as exc:
            raise ContextSourceUnavailableError(self.source_type.value, str(exc)) from exc

        if agent is None:
            return []
        purpose = _extract(agent, "purpose", "")
        approach = _extract(agent, "approach", "")
        role_types = list(_extract(agent, "role_types", []) or [])
        content = "\n".join(
            line
            for line in (
                f"Purpose: {purpose}".strip(),
                f"Approach: {approach}".strip() if approach else "",
            )
            if line
        ).strip()
        if not content:
            return []
        metadata = {"role_types": role_types}
        return [
            _build_element(
                source_type=self.source_type,
                priority=request.source_config.priority,
                content=content,
                origin=f"registry:{request.agent_fqn}",
                timestamp=_coerce_datetime(
                    _extract(agent, "updated_at") or _extract(agent, "created_at")
                ),
                authority_score=1.0,
                policy_justification="included: canonical system instructions",
                metadata=metadata,
            )
        ]


class WorkflowStateAdapter:
    source_type = ContextSourceType.workflow_state

    def __init__(self, execution_service: Any | None) -> None:
        self.execution_service = execution_service

    async def fetch(self, request: ContextFetchRequest) -> list[ContextElement]:
        if self.execution_service is None:
            raise ContextSourceUnavailableError(
                self.source_type.value, "Execution service unavailable"
            )
        try:
            if hasattr(self.execution_service, "get_workflow_state"):
                state = await self.execution_service.get_workflow_state(
                    request.execution_id,
                    request.step_id,
                )
            else:
                raise AttributeError("Execution service missing get_workflow_state")
        except Exception as exc:
            raise ContextSourceUnavailableError(self.source_type.value, str(exc)) from exc
        items = state if isinstance(state, list) else [state]
        return _normalize_items(
            source_type=self.source_type,
            items=items,
            request=request,
            origin_prefix=f"workflow:{request.execution_id}",
            authority_score=0.85,
        )


class ConversationHistoryAdapter:
    source_type = ContextSourceType.conversation_history

    def __init__(self, interactions_service: Any | None) -> None:
        self.interactions_service = interactions_service

    async def fetch(self, request: ContextFetchRequest) -> list[ContextElement]:
        if self.interactions_service is None:
            raise ContextSourceUnavailableError(
                self.source_type.value,
                "Interactions service unavailable",
            )
        try:
            if hasattr(self.interactions_service, "get_conversation_history"):
                history = await self.interactions_service.get_conversation_history(
                    request.execution_id,
                    request.step_id,
                    limit=request.source_config.max_elements,
                )
            elif hasattr(self.interactions_service, "list_conversation_history"):
                history = await self.interactions_service.list_conversation_history(
                    request.execution_id,
                    request.step_id,
                    limit=request.source_config.max_elements,
                )
            else:
                raise AttributeError("Interactions service missing history reader")
        except Exception as exc:
            raise ContextSourceUnavailableError(self.source_type.value, str(exc)) from exc
        items = history if isinstance(history, list) else [history]
        return _normalize_items(
            source_type=self.source_type,
            items=items,
            request=request,
            origin_prefix=f"conversation:{request.execution_id}",
            authority_score=0.8,
        )


class LongTermMemoryAdapter:
    source_type = ContextSourceType.long_term_memory

    def __init__(self, memory_service: Any | None) -> None:
        self.memory_service = memory_service

    async def fetch(self, request: ContextFetchRequest) -> list[ContextElement]:
        if self.memory_service is None:
            raise ContextSourceUnavailableError(
                self.source_type.value, "Memory adapter unavailable"
            )
        try:
            if hasattr(self.memory_service, "search_agent_memory"):
                items = await self.memory_service.search_agent_memory(
                    workspace_id=request.workspace_id,
                    agent_fqn=request.agent_fqn,
                    query=request.task_brief,
                    limit=request.source_config.max_elements,
                )
            else:
                raise AttributeError("Memory service missing search_agent_memory")
        except Exception as exc:
            raise ContextSourceUnavailableError(self.source_type.value, str(exc)) from exc
        normalized = _normalize_items(
            source_type=self.source_type,
            items=list(items or []),
            request=request,
            origin_prefix=f"memory:{request.agent_fqn}",
            authority_score=0.7,
        )
        for element in normalized:
            score = _extract(element.metadata, "score", None)
            if isinstance(score, (int, float)):
                element.metadata["relevance_score"] = float(score)
        return normalized


class ToolOutputsAdapter:
    source_type = ContextSourceType.tool_outputs

    def __init__(self, execution_service: Any | None) -> None:
        self.execution_service = execution_service

    async def fetch(self, request: ContextFetchRequest) -> list[ContextElement]:
        if self.execution_service is None:
            raise ContextSourceUnavailableError(
                self.source_type.value, "Execution service unavailable"
            )
        try:
            if hasattr(self.execution_service, "get_tool_outputs"):
                outputs = await self.execution_service.get_tool_outputs(
                    request.execution_id,
                    request.step_id,
                )
            else:
                raise AttributeError("Execution service missing get_tool_outputs")
        except Exception as exc:
            raise ContextSourceUnavailableError(self.source_type.value, str(exc)) from exc
        items = outputs if isinstance(outputs, list) else [outputs]
        return _normalize_items(
            source_type=self.source_type,
            items=items,
            request=request,
            origin_prefix=f"tool-output:{request.step_id}",
            authority_score=0.9,
        )


class ConnectorPayloadsAdapter:
    source_type = ContextSourceType.connector_payloads

    def __init__(self, connectors_service: Any | None) -> None:
        self.connectors_service = connectors_service

    async def fetch(self, request: ContextFetchRequest) -> list[ContextElement]:
        if self.connectors_service is None:
            raise ContextSourceUnavailableError(
                self.source_type.value,
                "Connectors service unavailable",
            )
        try:
            if hasattr(self.connectors_service, "get_connector_payloads"):
                payloads = await self.connectors_service.get_connector_payloads(
                    request.execution_id,
                    request.step_id,
                )
            else:
                raise AttributeError("Connectors service missing get_connector_payloads")
        except Exception as exc:
            raise ContextSourceUnavailableError(self.source_type.value, str(exc)) from exc
        items = payloads if isinstance(payloads, list) else [payloads]
        return _normalize_items(
            source_type=self.source_type,
            items=items,
            request=request,
            origin_prefix=f"connector:{request.step_id}",
            authority_score=0.6,
        )


class WorkspaceMetadataAdapter:
    source_type = ContextSourceType.workspace_metadata

    def __init__(self, workspaces_service: Any | None) -> None:
        self.workspaces_service = workspaces_service

    async def fetch(self, request: ContextFetchRequest) -> list[ContextElement]:
        if self.workspaces_service is None:
            raise ContextSourceUnavailableError(
                self.source_type.value, "Workspaces service unavailable"
            )
        try:
            workspace = None
            repo = getattr(self.workspaces_service, "repo", None)
            if repo is not None and hasattr(repo, "get_workspace_by_id_any"):
                workspace = await repo.get_workspace_by_id_any(request.workspace_id)
            elif hasattr(self.workspaces_service, "get_workspace_metadata"):
                workspace = await self.workspaces_service.get_workspace_metadata(
                    request.workspace_id
                )
            else:
                raise AttributeError("Workspaces service missing metadata reader")
        except Exception as exc:
            raise ContextSourceUnavailableError(self.source_type.value, str(exc)) from exc
        if workspace is None:
            return []
        name = _extract(workspace, "name", "")
        description = _extract(workspace, "description", None)
        content = "\n".join(
            line for line in (f"Workspace: {name}", description or "") if line
        ).strip()
        if not content:
            return []
        return [
            _build_element(
                source_type=self.source_type,
                priority=request.source_config.priority,
                content=content,
                origin=f"workspace:{request.workspace_id}",
                timestamp=_coerce_datetime(
                    _extract(workspace, "updated_at") or _extract(workspace, "created_at")
                ),
                authority_score=0.5,
                policy_justification="included: workspace metadata",
            )
        ]


class ReasoningTracesAdapter:
    source_type = ContextSourceType.reasoning_traces

    def __init__(self, execution_service: Any | None) -> None:
        self.execution_service = execution_service

    async def fetch(self, request: ContextFetchRequest) -> list[ContextElement]:
        if self.execution_service is None:
            raise ContextSourceUnavailableError(
                self.source_type.value, "Execution service unavailable"
            )
        try:
            if hasattr(self.execution_service, "get_reasoning_traces"):
                traces = await self.execution_service.get_reasoning_traces(
                    request.execution_id,
                    request.step_id,
                )
            else:
                raise AttributeError("Execution service missing get_reasoning_traces")
        except Exception as exc:
            raise ContextSourceUnavailableError(self.source_type.value, str(exc)) from exc
        items = traces if isinstance(traces, list) else [traces]
        return _normalize_items(
            source_type=self.source_type,
            items=items,
            request=request,
            origin_prefix=f"reasoning:{request.step_id}",
            authority_score=0.75,
        )


class WorkspaceGoalHistoryAdapter:
    source_type = ContextSourceType.workspace_goal_history

    def __init__(self, workspaces_service: Any | None) -> None:
        self.workspaces_service = workspaces_service

    async def fetch(self, request: ContextFetchRequest) -> list[ContextElement]:
        if request.goal_id is None:
            return []
        if self.workspaces_service is None:
            raise ContextSourceUnavailableError(
                self.source_type.value, "Workspaces service unavailable"
            )
        try:
            repo = getattr(self.workspaces_service, "repo", None)
            if repo is not None and hasattr(repo, "get_goal_by_gid"):
                goal = await repo.get_goal_by_gid(request.goal_id)
            elif hasattr(self.workspaces_service, "get_goal_by_gid"):
                goal = await self.workspaces_service.get_goal_by_gid(request.goal_id)
            else:
                raise AttributeError("Workspaces service missing get_goal_by_gid")
        except Exception as exc:
            raise ContextSourceUnavailableError(self.source_type.value, str(exc)) from exc
        if goal is None:
            return []
        content = "\n".join(
            line
            for line in (
                f"Goal title: {_extract(goal, 'title', '')}",
                _extract(goal, "description", None) or "",
                f"Goal status: {_extract(goal, 'status', '')}",
            )
            if line
        ).strip()
        if not content:
            return []
        return [
            _build_element(
                source_type=self.source_type,
                priority=request.source_config.priority,
                content=content,
                origin=f"goal:{request.goal_id}",
                timestamp=_coerce_datetime(
                    _extract(goal, "updated_at") or _extract(goal, "created_at")
                ),
                authority_score=0.75,
                policy_justification="included: active workspace goal context",
                metadata={"gid": str(request.goal_id)},
            )
        ]


def build_default_adapters(
    *,
    registry_service: Any | None = None,
    execution_service: Any | None = None,
    interactions_service: Any | None = None,
    memory_service: Any | None = None,
    connectors_service: Any | None = None,
    workspaces_service: Any | None = None,
) -> dict[ContextSourceType, ContextSourceAdapter]:
    return {
        ContextSourceType.system_instructions: SystemInstructionsAdapter(registry_service),
        ContextSourceType.workflow_state: WorkflowStateAdapter(execution_service),
        ContextSourceType.conversation_history: ConversationHistoryAdapter(interactions_service),
        ContextSourceType.long_term_memory: LongTermMemoryAdapter(memory_service),
        ContextSourceType.tool_outputs: ToolOutputsAdapter(execution_service),
        ContextSourceType.connector_payloads: ConnectorPayloadsAdapter(connectors_service),
        ContextSourceType.workspace_metadata: WorkspaceMetadataAdapter(workspaces_service),
        ContextSourceType.reasoning_traces: ReasoningTracesAdapter(execution_service),
        ContextSourceType.workspace_goal_history: WorkspaceGoalHistoryAdapter(workspaces_service),
    }
