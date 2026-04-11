from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.common.exceptions import ValidationError as PlatformValidationError
from platform.memory.dependencies import get_memory_service
from platform.memory.models import ConflictStatus, MemoryScope, PatternStatus
from platform.memory.schemas import (
    ConflictResolution,
    CrossScopeTransferRequest,
    EvidenceConflictListResponse,
    EvidenceConflictResponse,
    GraphTraversalQuery,
    GraphTraversalResponse,
    KnowledgeEdgeCreate,
    KnowledgeEdgeResponse,
    KnowledgeNodeCreate,
    KnowledgeNodeResponse,
    MemoryEntryListResponse,
    MemoryEntryResponse,
    MemoryWriteRequest,
    PatternAssetListResponse,
    PatternAssetResponse,
    PatternNomination,
    PatternReview,
    RetrievalQuery,
    RetrievalResponse,
    TrajectoryRecordCreate,
    TrajectoryRecordResponse,
    WriteGateResult,
)
from platform.memory.service import MemoryService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


def _workspace_id(current_user: dict[str, Any], request: Request) -> UUID:
    explicit = current_user.get("workspace_id") or request.headers.get("X-Workspace-ID")
    if explicit is not None:
        return UUID(str(explicit))
    roles = current_user.get("roles")
    if isinstance(roles, list):
        for role in roles:
            if isinstance(role, dict) and role.get("workspace_id"):
                return UUID(str(role["workspace_id"]))
    raise PlatformValidationError(
        "MEMORY_WORKSPACE_REQUIRED",
        "workspace_id is required",
    )


def _requester_identity(current_user: dict[str, Any], request: Request) -> str:
    header_agent = request.headers.get("X-Agent-FQN")
    if header_agent:
        return header_agent
    if isinstance(current_user.get("agent_fqn"), str):
        return str(current_user["agent_fqn"])
    return str(current_user["sub"])


@router.post("/entries", response_model=WriteGateResult, status_code=status.HTTP_201_CREATED)
async def create_memory_entry(
    payload: MemoryWriteRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> WriteGateResult:
    return await memory_service.write_memory(
        payload,
        _requester_identity(current_user, request),
        _workspace_id(current_user, request),
    )


@router.get("/entries/{entry_id}", response_model=MemoryEntryResponse)
async def get_memory_entry(
    entry_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemoryEntryResponse:
    return await memory_service.get_memory_entry_for_requester(
        entry_id,
        _workspace_id(current_user, request),
        _requester_identity(current_user, request),
    )


@router.get("/entries", response_model=MemoryEntryListResponse)
async def list_memory_entries(
    request: Request,
    scope: MemoryScope | None = Query(default=None),
    agent_fqn: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemoryEntryListResponse:
    items, total = await memory_service.list_memory_entries(
        _workspace_id(current_user, request),
        _requester_identity(current_user, request),
        scope,
        page,
        page_size,
        agent_fqn_filter=agent_fqn,
    )
    return MemoryEntryListResponse(items=items, total=total, page=page, page_size=page_size)


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory_entry(
    entry_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> Response:
    await memory_service.delete_memory_entry(
        entry_id,
        _workspace_id(current_user, request),
        _requester_identity(current_user, request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/entries/{entry_id}/transfer", response_model=WriteGateResult, status_code=201)
async def transfer_memory_scope(
    entry_id: UUID,
    payload: CrossScopeTransferRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> WriteGateResult:
    transfer = payload.model_copy(update={"memory_entry_id": entry_id})
    return await memory_service.transfer_memory_scope(
        transfer,
        _requester_identity(current_user, request),
        _workspace_id(current_user, request),
    )


@router.post("/retrieve", response_model=RetrievalResponse)
async def retrieve_memory(
    payload: RetrievalQuery,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> RetrievalResponse:
    return await memory_service.retrieve(
        payload,
        _requester_identity(current_user, request),
        _workspace_id(current_user, request),
    )


@router.get("/conflicts", response_model=EvidenceConflictListResponse)
async def list_conflicts(
    request: Request,
    status: ConflictStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> EvidenceConflictListResponse:
    items, total = await memory_service.list_conflicts(
        _workspace_id(current_user, request),
        status,
        page,
        page_size,
    )
    return EvidenceConflictListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/conflicts/{conflict_id}/resolve", response_model=EvidenceConflictResponse)
async def resolve_conflict(
    conflict_id: UUID,
    payload: ConflictResolution,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> EvidenceConflictResponse:
    return await memory_service.resolve_conflict(
        conflict_id,
        payload,
        str(current_user["sub"]),
        _workspace_id(current_user, request),
    )


@router.post("/trajectories", response_model=TrajectoryRecordResponse, status_code=201)
async def record_trajectory(
    payload: TrajectoryRecordCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> TrajectoryRecordResponse:
    return await memory_service.record_trajectory(payload, _workspace_id(current_user, request))


@router.get("/trajectories/{trajectory_id}", response_model=TrajectoryRecordResponse)
async def get_trajectory(
    trajectory_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> TrajectoryRecordResponse:
    return await memory_service.get_trajectory(trajectory_id, _workspace_id(current_user, request))


@router.post("/patterns", response_model=PatternAssetResponse, status_code=201)
async def nominate_pattern(
    payload: PatternNomination,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> PatternAssetResponse:
    return await memory_service.nominate_pattern(
        payload,
        _requester_identity(current_user, request),
        _workspace_id(current_user, request),
    )


@router.post("/patterns/{pattern_id}/review", response_model=PatternAssetResponse)
async def review_pattern(
    pattern_id: UUID,
    payload: PatternReview,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> PatternAssetResponse:
    return await memory_service.review_pattern(
        pattern_id,
        payload,
        str(current_user["sub"]),
        _workspace_id(current_user, request),
    )


@router.get("/patterns", response_model=PatternAssetListResponse)
async def list_patterns(
    request: Request,
    status: PatternStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> PatternAssetListResponse:
    items, total = await memory_service.list_patterns(
        _workspace_id(current_user, request),
        status,
        page,
        page_size,
    )
    return PatternAssetListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/graph/nodes", response_model=KnowledgeNodeResponse, status_code=201)
async def create_knowledge_node(
    payload: KnowledgeNodeCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> KnowledgeNodeResponse:
    return await memory_service.create_knowledge_node(
        payload,
        _requester_identity(current_user, request),
        _workspace_id(current_user, request),
    )


@router.post("/graph/edges", response_model=KnowledgeEdgeResponse, status_code=201)
async def create_knowledge_edge(
    payload: KnowledgeEdgeCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> KnowledgeEdgeResponse:
    return await memory_service.create_knowledge_edge(
        payload,
        _workspace_id(current_user, request),
    )


@router.post("/graph/traverse", response_model=GraphTraversalResponse)
async def traverse_graph(
    payload: GraphTraversalQuery,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> GraphTraversalResponse:
    return await memory_service.traverse_graph(payload, _workspace_id(current_user, request))


@router.get("/graph/nodes/{node_id}/provenance", response_model=GraphTraversalResponse)
async def get_provenance_chain(
    node_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> GraphTraversalResponse:
    return await memory_service.get_provenance_chain(
        node_id,
        _workspace_id(current_user, request),
    )
