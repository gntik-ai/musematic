from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.discovery.dependencies import DiscoveryServiceDep
from platform.discovery.schemas import (
    ClusterListResponse,
    CritiqueListResponse,
    DiscoveryExperimentResponse,
    DiscoverySessionCreateRequest,
    DiscoverySessionListResponse,
    DiscoverySessionResponse,
    ExperimentDesignRequest,
    GDECycleResponse,
    HaltSessionRequest,
    HypothesisListResponse,
    HypothesisResponse,
    LeaderboardResponse,
    ProvenanceGraphResponse,
    TournamentRoundListResponse,
)
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

router = APIRouter(prefix="/api/v1/discovery", tags=["discovery"])


def _actor_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


def _workspace_id(current_user: dict[str, Any], workspace_id: UUID | None) -> UUID:
    if workspace_id is not None:
        return workspace_id
    value = current_user.get("workspace_id") or current_user.get("workspace")
    if value is None:
        raise ValueError("workspace_id query parameter is required")
    return UUID(str(value))


@router.post(
    "/sessions",
    response_model=DiscoverySessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    payload: DiscoverySessionCreateRequest,
    service: DiscoveryServiceDep,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DiscoverySessionResponse:
    return await service.start_session(payload, _actor_id(current_user))


@router.get("/sessions/{session_id}", response_model=DiscoverySessionResponse)
async def get_session(
    session_id: UUID,
    service: DiscoveryServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DiscoverySessionResponse:
    return await service.get_session(session_id, _workspace_id(current_user, workspace_id))


@router.get("/sessions", response_model=DiscoverySessionListResponse)
async def list_sessions(
    service: DiscoveryServiceDep,
    workspace_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DiscoverySessionListResponse:
    return await service.list_sessions(
        _workspace_id(current_user, workspace_id),
        status=status_filter,
        limit=limit,
        cursor=cursor,
    )


@router.post("/sessions/{session_id}/halt", response_model=DiscoverySessionResponse)
async def halt_session(
    session_id: UUID,
    payload: HaltSessionRequest,
    service: DiscoveryServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DiscoverySessionResponse:
    return await service.halt_session(
        session_id,
        _workspace_id(current_user, workspace_id),
        _actor_id(current_user),
        payload.reason,
    )


@router.post(
    "/sessions/{session_id}/cycle",
    response_model=GDECycleResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_cycle(
    session_id: UUID,
    service: DiscoveryServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> GDECycleResponse:
    return await service.run_gde_cycle(
        session_id,
        _workspace_id(current_user, workspace_id),
        _actor_id(current_user),
    )


@router.get("/cycles/{cycle_id}", response_model=GDECycleResponse)
async def get_cycle(
    cycle_id: UUID,
    service: DiscoveryServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> GDECycleResponse:
    return await service.get_cycle(cycle_id, _workspace_id(current_user, workspace_id))


@router.get("/sessions/{session_id}/hypotheses", response_model=HypothesisListResponse)
async def list_hypotheses(
    session_id: UUID,
    service: DiscoveryServiceDep,
    workspace_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    order_by: str = Query(default="elo_desc", pattern="^(elo_desc|created_at)$"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> HypothesisListResponse:
    return await service.list_hypotheses(
        session_id,
        _workspace_id(current_user, workspace_id),
        status=status_filter,
        order_by=order_by,
        limit=limit,
        cursor=cursor,
    )


@router.get("/hypotheses/{hypothesis_id}", response_model=HypothesisResponse)
async def get_hypothesis(
    hypothesis_id: UUID,
    service: DiscoveryServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> HypothesisResponse:
    return await service.get_hypothesis(hypothesis_id, _workspace_id(current_user, workspace_id))


@router.get("/hypotheses/{hypothesis_id}/critiques", response_model=CritiqueListResponse)
async def get_critiques(
    hypothesis_id: UUID,
    service: DiscoveryServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> CritiqueListResponse:
    return await service.get_critiques(hypothesis_id, _workspace_id(current_user, workspace_id))


@router.get("/sessions/{session_id}/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    session_id: UUID,
    service: DiscoveryServiceDep,
    workspace_id: UUID | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> LeaderboardResponse:
    return await service.get_leaderboard(
        session_id,
        _workspace_id(current_user, workspace_id),
        limit,
    )


@router.get("/sessions/{session_id}/tournament-rounds", response_model=TournamentRoundListResponse)
async def list_tournament_rounds(
    session_id: UUID,
    service: DiscoveryServiceDep,
    workspace_id: UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> TournamentRoundListResponse:
    return await service.list_tournament_rounds(
        session_id,
        _workspace_id(current_user, workspace_id),
        limit=limit,
        cursor=cursor,
    )


@router.post(
    "/hypotheses/{hypothesis_id}/experiment",
    response_model=DiscoveryExperimentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def design_experiment(
    hypothesis_id: UUID,
    payload: ExperimentDesignRequest,
    service: DiscoveryServiceDep,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DiscoveryExperimentResponse:
    return await service.design_experiment(
        hypothesis_id, payload.workspace_id, _actor_id(current_user)
    )


@router.get("/experiments/{experiment_id}", response_model=DiscoveryExperimentResponse)
async def get_experiment(
    experiment_id: UUID,
    service: DiscoveryServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DiscoveryExperimentResponse:
    return await service.get_experiment(experiment_id, _workspace_id(current_user, workspace_id))


@router.post(
    "/experiments/{experiment_id}/execute",
    response_model=DiscoveryExperimentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def execute_experiment(
    experiment_id: UUID,
    service: DiscoveryServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DiscoveryExperimentResponse:
    return await service.execute_experiment(
        experiment_id, _workspace_id(current_user, workspace_id)
    )


@router.get("/hypotheses/{hypothesis_id}/provenance", response_model=ProvenanceGraphResponse)
async def get_provenance(
    hypothesis_id: UUID,
    service: DiscoveryServiceDep,
    workspace_id: UUID | None = Query(default=None),
    depth: int = Query(default=3, ge=1, le=10),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ProvenanceGraphResponse:
    return await service.get_hypothesis_provenance(
        hypothesis_id,
        _workspace_id(current_user, workspace_id),
        depth,
    )


@router.get("/sessions/{session_id}/clusters", response_model=ClusterListResponse)
async def get_clusters(
    session_id: UUID,
    service: DiscoveryServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ClusterListResponse:
    return await service.get_proximity_clusters(
        session_id, _workspace_id(current_user, workspace_id)
    )


@router.post(
    "/sessions/{session_id}/compute-proximity",
    response_model=ClusterListResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def compute_proximity(
    session_id: UUID,
    service: DiscoveryServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ClusterListResponse:
    return await service.trigger_proximity_computation(
        session_id,
        _workspace_id(current_user, workspace_id),
    )
