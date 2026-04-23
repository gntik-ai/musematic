from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.interactions.dependencies import get_interactions_service
from platform.interactions.models import AttentionStatus, InteractionState
from platform.interactions.schemas import (
    AgentDecisionConfigListResponse,
    AgentDecisionConfigResponse,
    AgentDecisionConfigUpsert,
    AttentionRequestCreate,
    AttentionRequestListResponse,
    AttentionRequestResponse,
    AttentionResolve,
    BranchCreate,
    BranchMerge,
    BranchResponse,
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    DecisionRationaleListResponse,
    DecisionRationaleMessageListResponse,
    GoalMessageCreate,
    GoalMessageListResponse,
    GoalMessageResponse,
    GoalStateTransitionRequest,
    GoalStateTransitionResponse,
    InteractionCreate,
    InteractionListResponse,
    InteractionResponse,
    InteractionTransition,
    MergeRecordResponse,
    MessageCreate,
    MessageInject,
    MessageListResponse,
    MessageResponse,
    ParticipantAdd,
    ParticipantResponse,
)
from platform.interactions.service import InteractionsService
from typing import Any
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

router = APIRouter(prefix="/api/v1", tags=["interactions"])


def _workspace_id(request: Request, current_user: dict[str, Any]) -> UUID:
    explicit = current_user.get("workspace_id") or request.headers.get("X-Workspace-ID")
    if explicit is not None:
        return UUID(str(explicit))
    roles = current_user.get("roles")
    if isinstance(roles, list):
        for role in roles:
            if isinstance(role, dict) and role.get("workspace_id"):
                return UUID(str(role["workspace_id"]))
    raise ValidationError("WORKSPACE_REQUIRED", "workspace_id is required")


def _requesting_agent_id(current_user: dict[str, Any]) -> UUID | None:
    agent_id = current_user.get("agent_profile_id") or current_user.get("agent_id")
    return UUID(str(agent_id)) if agent_id is not None else None


def _identity(current_user: dict[str, Any], request: Request) -> str:
    header_agent = request.headers.get("X-Agent-FQN")
    if header_agent:
        return header_agent
    agent_fqn = current_user.get("agent_fqn")
    if isinstance(agent_fqn, str):
        return agent_fqn
    subject = current_user.get("sub")
    if subject is None:
        raise ValidationError("IDENTITY_REQUIRED", "Authenticated subject is required")
    return str(subject)


def _role_names(current_user: dict[str, Any]) -> set[str]:
    roles = current_user.get("roles", [])
    return {
        str(item.get("role"))
        for item in roles
        if isinstance(item, dict) and item.get("role") is not None
    }


def _require_roles(current_user: dict[str, Any], accepted: set[str]) -> None:
    if _role_names(current_user) & accepted:
        return
    raise AuthorizationError(
        "PERMISSION_DENIED",
        "Insufficient role for interaction endpoint",
    )


@router.post(
    "/interactions/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    payload: ConversationCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> ConversationResponse:
    return await interactions_service.create_conversation(
        payload,
        _identity(current_user, request),
        _workspace_id(request, current_user),
    )


@router.get("/interactions/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> ConversationResponse:
    return await interactions_service.get_conversation(
        conversation_id,
        _workspace_id(request, current_user),
    )


@router.get("/interactions/conversations", response_model=ConversationListResponse)
async def list_conversations(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> ConversationListResponse:
    return await interactions_service.list_conversations(
        _workspace_id(request, current_user),
        page,
        page_size,
    )


@router.patch("/interactions/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> ConversationResponse:
    return await interactions_service.update_conversation(
        conversation_id,
        payload,
        _workspace_id(request, current_user),
    )


@router.delete(
    "/interactions/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    conversation_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> Response:
    await interactions_service.delete_conversation(
        conversation_id,
        _workspace_id(request, current_user),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/interactions/",
    response_model=InteractionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_interaction(
    payload: InteractionCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> InteractionResponse:
    return await interactions_service.create_interaction(
        payload,
        _identity(current_user, request),
        _workspace_id(request, current_user),
    )


@router.get(
    "/interactions/conversations/{conversation_id}/interactions",
    response_model=InteractionListResponse,
)
async def list_interactions(
    conversation_id: UUID,
    request: Request,
    state: InteractionState | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> InteractionListResponse:
    return await interactions_service.list_interactions(
        conversation_id,
        _workspace_id(request, current_user),
        page,
        page_size,
        state,
    )


@router.post("/interactions/{interaction_id}/transition", response_model=InteractionResponse)
async def transition_interaction(
    interaction_id: UUID,
    payload: InteractionTransition,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> InteractionResponse:
    return await interactions_service.transition_interaction(
        interaction_id,
        payload,
        _workspace_id(request, current_user),
    )


@router.post(
    "/interactions/{interaction_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    interaction_id: UUID,
    payload: MessageCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> MessageResponse:
    return await interactions_service.send_message(
        interaction_id,
        payload,
        _identity(current_user, request),
        _workspace_id(request, current_user),
    )


@router.post(
    "/interactions/{interaction_id}/inject",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def inject_message(
    interaction_id: UUID,
    payload: MessageInject,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> MessageResponse:
    return await interactions_service.inject_message(
        interaction_id,
        payload,
        _identity(current_user, request),
        _workspace_id(request, current_user),
    )


@router.get("/interactions/{interaction_id}/messages", response_model=MessageListResponse)
async def list_messages(
    interaction_id: UUID,
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> MessageListResponse:
    return await interactions_service.list_messages(
        interaction_id,
        _workspace_id(request, current_user),
        page,
        page_size,
    )


@router.post(
    "/interactions/{interaction_id}/participants",
    response_model=ParticipantResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_participant(
    interaction_id: UUID,
    payload: ParticipantAdd,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> ParticipantResponse:
    return await interactions_service.add_participant(
        interaction_id,
        payload,
        _workspace_id(request, current_user),
        requesting_agent_id=_requesting_agent_id(current_user),
    )


@router.delete(
    "/interactions/{interaction_id}/participants/{identity}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_participant(
    interaction_id: UUID,
    identity: str,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> Response:
    await interactions_service.remove_participant(
        interaction_id,
        identity,
        _workspace_id(request, current_user),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/interactions/{interaction_id}/participants",
    response_model=list[ParticipantResponse],
)
async def list_participants(
    interaction_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> list[ParticipantResponse]:
    return await interactions_service.list_participants(
        interaction_id,
        _workspace_id(request, current_user),
    )


@router.post(
    "/workspaces/{workspace_id}/goals/{goal_id}/messages",
    response_model=GoalMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_goal_message(
    workspace_id: UUID,
    goal_id: UUID,
    payload: GoalMessageCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> GoalMessageResponse:
    return await interactions_service.post_goal_message(
        goal_id,
        payload,
        _identity(current_user, request),
        workspace_id,
    )


@router.get(
    "/workspaces/{workspace_id}/goals/{goal_id}/messages",
    response_model=GoalMessageListResponse,
)
async def list_goal_messages(
    workspace_id: UUID,
    goal_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> GoalMessageListResponse:
    del current_user
    return await interactions_service.list_goal_messages(
        goal_id,
        workspace_id,
        page,
        page_size,
    )


@router.post(
    "/workspaces/{workspace_id}/goals/{goal_id}/transition",
    response_model=GoalStateTransitionResponse,
)
async def transition_goal_state(
    workspace_id: UUID,
    goal_id: UUID,
    payload: GoalStateTransitionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> GoalStateTransitionResponse:
    _require_roles(
        current_user,
        {"workspace_admin", "workspace_owner", "platform_admin", "superadmin"},
    )
    return await interactions_service.transition_goal_state(goal_id, payload, workspace_id)


@router.put(
    "/workspaces/{workspace_id}/agent-decision-configs/{agent_fqn}",
    response_model=AgentDecisionConfigResponse,
)
async def upsert_agent_decision_config(
    workspace_id: UUID,
    agent_fqn: str,
    payload: AgentDecisionConfigUpsert,
    response: Response,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> AgentDecisionConfigResponse:
    _require_roles(
        current_user,
        {"workspace_admin", "workspace_owner", "platform_admin", "superadmin"},
    )
    config_response, created = await interactions_service.upsert_agent_decision_config(
        workspace_id,
        unquote(agent_fqn),
        payload,
        UUID(str(current_user["sub"])),
    )
    if created:
        response.status_code = status.HTTP_201_CREATED
    return config_response


@router.get(
    "/workspaces/{workspace_id}/agent-decision-configs",
    response_model=AgentDecisionConfigListResponse,
)
async def list_agent_decision_configs(
    workspace_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> AgentDecisionConfigListResponse:
    _require_roles(
        current_user,
        {"workspace_admin", "workspace_owner", "platform_admin", "superadmin"},
    )
    return await interactions_service.list_agent_decision_configs(
        workspace_id,
        UUID(str(current_user["sub"])),
    )


@router.get(
    "/workspaces/{workspace_id}/goals/{goal_id}/messages/{message_id}/rationale",
    response_model=DecisionRationaleMessageListResponse,
)
async def list_rationale_for_message(
    workspace_id: UUID,
    goal_id: UUID,
    message_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> DecisionRationaleMessageListResponse:
    _require_roles(
        current_user,
        {"workspace_admin", "workspace_owner", "platform_admin", "superadmin"},
    )
    return await interactions_service.list_rationale_for_message(
        goal_id,
        message_id,
        workspace_id,
    )


@router.get(
    "/workspaces/{workspace_id}/goals/{goal_id}/rationale",
    response_model=DecisionRationaleListResponse,
)
async def list_rationale_for_goal(
    workspace_id: UUID,
    goal_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    agent_fqn: str | None = Query(default=None),
    decision: str | None = Query(default=None, pattern="^(respond|skip)$"),
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> DecisionRationaleListResponse:
    _require_roles(
        current_user,
        {"workspace_admin", "workspace_owner", "platform_admin", "superadmin"},
    )
    return await interactions_service.list_rationale_for_goal(
        goal_id,
        workspace_id,
        page,
        page_size,
        agent_fqn=unquote(agent_fqn) if agent_fqn is not None else None,
        decision=decision,
    )


@router.post(
    "/interactions/branches",
    response_model=BranchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_branch(
    payload: BranchCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> BranchResponse:
    return await interactions_service.create_branch(
        payload,
        _workspace_id(request, current_user),
    )


@router.post(
    "/interactions/branches/{branch_id}/merge",
    response_model=MergeRecordResponse,
)
async def merge_branch(
    branch_id: UUID,
    payload: BranchMerge,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> MergeRecordResponse:
    return await interactions_service.merge_branch(
        branch_id,
        payload,
        _identity(current_user, request),
        _workspace_id(request, current_user),
    )


@router.post(
    "/interactions/branches/{branch_id}/abandon",
    response_model=BranchResponse,
)
async def abandon_branch(
    branch_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> BranchResponse:
    return await interactions_service.abandon_branch(
        branch_id,
        _workspace_id(request, current_user),
    )


@router.get(
    "/interactions/conversations/{conversation_id}/branches",
    response_model=list[BranchResponse],
)
async def list_branches(
    conversation_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> list[BranchResponse]:
    return await interactions_service.list_branches(
        conversation_id,
        _workspace_id(request, current_user),
    )


@router.post(
    "/interactions/attention",
    response_model=AttentionRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_attention_request(
    payload: AttentionRequestCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> AttentionRequestResponse:
    return await interactions_service.create_attention_request(
        payload,
        _identity(current_user, request),
        _workspace_id(request, current_user),
    )


@router.get("/interactions/attention", response_model=AttentionRequestListResponse)
async def list_attention_requests(
    request: Request,
    status: AttentionStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> AttentionRequestListResponse:
    return await interactions_service.list_attention_requests(
        str(current_user["sub"]),
        _workspace_id(request, current_user),
        status,
        page,
        page_size,
    )


@router.post(
    "/interactions/attention/{request_id}/resolve",
    response_model=AttentionRequestResponse,
)
async def resolve_attention_request(
    request_id: UUID,
    payload: AttentionResolve,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> AttentionRequestResponse:
    return await interactions_service.resolve_attention_request(
        request_id,
        payload,
        _workspace_id(request, current_user),
        requester_identity=str(current_user["sub"]),
    )


@router.get("/interactions/{interaction_id}", response_model=InteractionResponse)
async def get_interaction(
    interaction_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> InteractionResponse:
    return await interactions_service.get_interaction(
        interaction_id,
        _workspace_id(request, current_user),
    )
