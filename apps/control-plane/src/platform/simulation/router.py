from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.common.exceptions import ValidationError
from platform.simulation.dependencies import SimulationServiceDep
from platform.simulation.schemas import (
    BehavioralPredictionCreateRequest,
    BehavioralPredictionResponse,
    DigitalTwinCreateRequest,
    DigitalTwinListResponse,
    DigitalTwinModifyRequest,
    DigitalTwinResponse,
    DigitalTwinVersionListResponse,
    ScenarioCreate,
    ScenarioListResponse,
    ScenarioRead,
    ScenarioRunRequest,
    ScenarioRunSummary,
    ScenarioUpdate,
    SimulationComparisonCreateRequest,
    SimulationComparisonReportResponse,
    SimulationIsolationPolicyCreateRequest,
    SimulationIsolationPolicyListResponse,
    SimulationIsolationPolicyResponse,
    SimulationRunCreateRequest,
    SimulationRunListResponse,
    SimulationRunResponse,
)
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

router = APIRouter(prefix="/api/v1/simulations", tags=["simulations"])


def _actor_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


def _workspace_id(current_user: dict[str, Any], workspace_id: UUID | None) -> UUID:
    if workspace_id is not None:
        return workspace_id
    value = current_user.get("workspace_id") or current_user.get("workspace")
    if value is None:
        raise ValidationError("WORKSPACE_REQUIRED", "workspace_id query parameter is required")
    return UUID(str(value))


@router.post("", response_model=SimulationRunResponse, status_code=status.HTTP_201_CREATED)
async def create_simulation_run(
    payload: SimulationRunCreateRequest,
    service: SimulationServiceDep,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> SimulationRunResponse:
    return await service.create_simulation_run(payload, _actor_id(current_user))


@router.get("", response_model=SimulationRunListResponse)
async def list_simulation_runs(
    service: SimulationServiceDep,
    workspace_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> SimulationRunListResponse:
    return await service.list_simulation_runs(
        _workspace_id(current_user, workspace_id),
        status=status_filter,
        limit=limit,
        cursor=cursor,
    )


@router.post(
    "/twins",
    response_model=DigitalTwinResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_digital_twin(
    payload: DigitalTwinCreateRequest,
    service: SimulationServiceDep,
) -> DigitalTwinResponse:
    return await service.create_digital_twin(payload)


@router.get("/twins", response_model=DigitalTwinListResponse)
async def list_digital_twins(
    service: SimulationServiceDep,
    workspace_id: UUID | None = Query(default=None),
    agent_fqn: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DigitalTwinListResponse:
    return await service.list_digital_twins(
        _workspace_id(current_user, workspace_id),
        agent_fqn=agent_fqn,
        is_active=is_active,
        limit=limit,
        cursor=cursor,
    )


@router.get("/twins/{twin_id}", response_model=DigitalTwinResponse)
async def get_digital_twin(
    twin_id: UUID,
    service: SimulationServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DigitalTwinResponse:
    return await service.get_digital_twin(twin_id, _workspace_id(current_user, workspace_id))


@router.patch(
    "/twins/{twin_id}",
    response_model=DigitalTwinResponse,
    status_code=status.HTTP_201_CREATED,
)
async def modify_digital_twin(
    twin_id: UUID,
    payload: DigitalTwinModifyRequest,
    service: SimulationServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DigitalTwinResponse:
    return await service.modify_digital_twin(
        twin_id,
        _workspace_id(current_user, workspace_id),
        payload,
    )


@router.get("/twins/{twin_id}/versions", response_model=DigitalTwinVersionListResponse)
async def list_twin_versions(
    twin_id: UUID,
    service: SimulationServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DigitalTwinVersionListResponse:
    return await service.list_twin_versions(twin_id, _workspace_id(current_user, workspace_id))


@router.post(
    "/isolation-policies",
    response_model=SimulationIsolationPolicyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_isolation_policy(
    payload: SimulationIsolationPolicyCreateRequest,
    service: SimulationServiceDep,
) -> SimulationIsolationPolicyResponse:
    return await service.create_isolation_policy(payload)


@router.get("/isolation-policies", response_model=SimulationIsolationPolicyListResponse)
async def list_isolation_policies(
    service: SimulationServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> SimulationIsolationPolicyListResponse:
    return await service.list_isolation_policies(_workspace_id(current_user, workspace_id))


@router.get(
    "/isolation-policies/{policy_id}",
    response_model=SimulationIsolationPolicyResponse,
)
async def get_isolation_policy(
    policy_id: UUID,
    service: SimulationServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> SimulationIsolationPolicyResponse:
    return await service.get_isolation_policy(policy_id, _workspace_id(current_user, workspace_id))


@router.post(
    "/twins/{twin_id}/predict",
    response_model=BehavioralPredictionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_behavioral_prediction(
    twin_id: UUID,
    payload: BehavioralPredictionCreateRequest,
    service: SimulationServiceDep,
) -> BehavioralPredictionResponse:
    return await service.create_behavioral_prediction(twin_id, payload)


@router.get("/predictions/{prediction_id}", response_model=BehavioralPredictionResponse)
async def get_behavioral_prediction(
    prediction_id: UUID,
    service: SimulationServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> BehavioralPredictionResponse:
    return await service.get_behavioral_prediction(
        prediction_id,
        _workspace_id(current_user, workspace_id),
    )


@router.get("/comparisons/{report_id}", response_model=SimulationComparisonReportResponse)
async def get_comparison_report(
    report_id: UUID,
    service: SimulationServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> SimulationComparisonReportResponse:
    return await service.get_comparison_report(report_id, _workspace_id(current_user, workspace_id))


@router.get("/scenarios", response_model=ScenarioListResponse)
async def list_simulation_scenarios(
    service: SimulationServiceDep,
    workspace_id: UUID | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ScenarioListResponse:
    return await service.list_scenarios(
        _workspace_id(current_user, workspace_id),
        include_archived=include_archived,
        limit=limit,
        cursor=cursor,
    )


@router.post(
    "/scenarios",
    response_model=ScenarioRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_simulation_scenario(
    payload: ScenarioCreate,
    service: SimulationServiceDep,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ScenarioRead:
    return await service.create_scenario(payload, _actor_id(current_user))


@router.get("/scenarios/{scenario_id}", response_model=ScenarioRead)
async def get_simulation_scenario(
    scenario_id: UUID,
    service: SimulationServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ScenarioRead:
    return await service.get_scenario(scenario_id, _workspace_id(current_user, workspace_id))


@router.put("/scenarios/{scenario_id}", response_model=ScenarioRead)
async def update_simulation_scenario(
    scenario_id: UUID,
    payload: ScenarioUpdate,
    service: SimulationServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ScenarioRead:
    return await service.update_scenario(
        scenario_id,
        _workspace_id(current_user, workspace_id),
        payload,
    )


@router.delete("/scenarios/{scenario_id}", response_model=ScenarioRead)
async def archive_simulation_scenario(
    scenario_id: UUID,
    service: SimulationServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ScenarioRead:
    return await service.archive_scenario(scenario_id, _workspace_id(current_user, workspace_id))


@router.post(
    "/scenarios/{scenario_id}/run",
    response_model=ScenarioRunSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_simulation_scenario(
    scenario_id: UUID,
    payload: ScenarioRunRequest,
    service: SimulationServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ScenarioRunSummary:
    return await service.launch_scenario(
        scenario_id,
        _workspace_id(current_user, workspace_id),
        _actor_id(current_user),
        payload,
    )


@router.get("/{run_id}", response_model=SimulationRunResponse)
async def get_simulation_run(
    run_id: UUID,
    service: SimulationServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> SimulationRunResponse:
    return await service.get_simulation_run(run_id, _workspace_id(current_user, workspace_id))


@router.post("/{run_id}/cancel", response_model=SimulationRunResponse)
async def cancel_simulation_run(
    run_id: UUID,
    service: SimulationServiceDep,
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> SimulationRunResponse:
    return await service.cancel_simulation_run(
        run_id,
        _workspace_id(current_user, workspace_id),
        _actor_id(current_user),
    )


@router.post(
    "/{run_id}/compare",
    response_model=SimulationComparisonReportResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_comparison_report(
    run_id: UUID,
    payload: SimulationComparisonCreateRequest,
    service: SimulationServiceDep,
) -> SimulationComparisonReportResponse:
    return await service.create_comparison_report(run_id, payload)
