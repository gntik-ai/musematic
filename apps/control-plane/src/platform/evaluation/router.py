from __future__ import annotations

from platform.common import database
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.clients.reasoning_engine import ReasoningEngineClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.clients.runtime_controller import RuntimeControllerClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user
from platform.common.events.producer import EventProducer
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.evaluation.ab_experiment_service import AbExperimentService
from platform.evaluation.ate_service import ATEService
from platform.evaluation.dependencies import (
    build_ab_experiment_service,
    build_ate_service,
    build_eval_runner_service,
    build_robustness_service,
    get_ab_experiment_service,
    get_ate_service,
    get_eval_runner_service,
    get_eval_suite_service,
    get_human_grading_service,
    get_robustness_service,
)
from platform.evaluation.human_grading_service import HumanGradingService
from platform.evaluation.models import ATERunStatus, EvalSetStatus, RunStatus, VerdictStatus
from platform.evaluation.robustness_service import RobustnessTestService
from platform.evaluation.schemas import (
    AbExperimentCreate,
    AbExperimentResponse,
    ATEConfigCreate,
    ATEConfigListResponse,
    ATEConfigResponse,
    ATEConfigUpdate,
    ATERunListResponse,
    ATERunRequest,
    ATERunResponse,
    BenchmarkCaseCreate,
    BenchmarkCaseListResponse,
    BenchmarkCaseResponse,
    EvalSetCreate,
    EvalSetListResponse,
    EvalSetResponse,
    EvalSetUpdate,
    EvaluationRunCreate,
    EvaluationRunListResponse,
    EvaluationRunResponse,
    HumanAiGradeResponse,
    HumanGradeSubmit,
    HumanGradeUpdate,
    JudgeVerdictListResponse,
    JudgeVerdictResponse,
    ReviewProgressResponse,
    RobustnessRunCreate,
    RobustnessTestRunResponse,
)
from platform.evaluation.service import EvalRunnerService, EvalSuiteService
from platform.execution.dependencies import build_execution_service
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Query, Request, Response, status

router = APIRouter(tags=["evaluations"])


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
    raise AuthorizationError("PERMISSION_DENIED", "Insufficient role for evaluation endpoint")


def _actor_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


def _workspace_id(
    request: Request,
    current_user: dict[str, Any],
    payload_workspace_id: UUID | None = None,
) -> UUID:
    header_value = request.headers.get("X-Workspace-ID")
    if header_value:
        workspace_id = UUID(header_value)
    else:
        claim_value = current_user.get("workspace_id")
        if claim_value is None and payload_workspace_id is None:
            raise ValidationError("WORKSPACE_REQUIRED", "Workspace context is required")
        if claim_value is not None:
            workspace_id = UUID(str(claim_value))
        elif payload_workspace_id is not None:
            workspace_id = payload_workspace_id
        else:
            raise ValidationError("WORKSPACE_REQUIRED", "Workspace context is required")
    if payload_workspace_id is not None and workspace_id != payload_workspace_id:
        raise ValidationError("WORKSPACE_MISMATCH", "Payload workspace_id does not match request")
    return workspace_id


def _build_execution_query(app: FastAPI, session: Any) -> Any:
    return build_execution_service(
        session=session,
        settings=cast(PlatformSettings, app.state.settings),
        producer=cast(EventProducer | None, app.state.clients.get("kafka")),
        redis_client=cast(AsyncRedisClient, app.state.clients["redis"]),
        object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
        runtime_controller=cast(
            RuntimeControllerClient | None,
            app.state.clients.get("runtime_controller"),
        ),
        reasoning_engine=cast(
            ReasoningEngineClient | None,
            app.state.clients.get("reasoning_engine"),
        ),
        context_engineering_service=getattr(app.state, "context_engineering_service", None),
    )


def _build_eval_runner(app: FastAPI, session: Any) -> Any:
    return build_eval_runner_service(
        session=session,
        settings=cast(PlatformSettings, app.state.settings),
        producer=cast(EventProducer | None, app.state.clients.get("kafka")),
        qdrant=cast(AsyncQdrantClient, app.state.clients["qdrant"]),
        runtime_controller=cast(
            RuntimeControllerClient | None,
            app.state.clients.get("runtime_controller"),
        ),
        reasoning_engine=cast(
            ReasoningEngineClient | None,
            app.state.clients.get("reasoning_engine"),
        ),
        execution_service=_build_execution_query(app, session),
    )


async def _run_eval_background(app: FastAPI, run_id: UUID) -> None:
    async with database.AsyncSessionLocal() as session:
        service = _build_eval_runner(app, session)
        try:
            await service.run_existing(run_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _run_experiment_background(app: FastAPI, experiment_id: UUID) -> None:
    async with database.AsyncSessionLocal() as session:
        service = build_ab_experiment_service(
            session=session,
            producer=cast(EventProducer | None, app.state.clients.get("kafka")),
        )
        try:
            await service.run_experiment(experiment_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _run_ate_background(app: FastAPI, ate_run_id: UUID) -> None:
    async with database.AsyncSessionLocal() as session:
        service = build_ate_service(
            session=session,
            settings=cast(PlatformSettings, app.state.settings),
            producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            object_storage=cast(AsyncObjectStorageClient, app.state.clients["object_storage"]),
            simulation_controller=cast(
                Any,
                app.state.clients.get("simulation_controller"),
            ),
            eval_runner_service=_build_eval_runner(app, session),
        )
        try:
            await service.execute_run(ate_run_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _run_robustness_background(app: FastAPI, run_id: UUID) -> None:
    async with database.AsyncSessionLocal() as session:
        service = build_robustness_service(
            session=session,
            eval_runner_service=_build_eval_runner(app, session),
            producer=cast(EventProducer | None, app.state.clients.get("kafka")),
        )
        try:
            await service.execute_run(run_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@router.post("/eval-sets", response_model=EvalSetResponse, status_code=status.HTTP_201_CREATED)
async def create_eval_set(
    payload: EvalSetCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    eval_suite_service: EvalSuiteService = Depends(get_eval_suite_service),
) -> EvalSetResponse:
    workspace_id = _workspace_id(request, current_user, payload.workspace_id)
    normalized = payload.model_copy(update={"workspace_id": workspace_id})
    return await eval_suite_service.create_eval_set(normalized, _actor_id(current_user))


@router.get("/eval-sets", response_model=EvalSetListResponse)
async def list_eval_sets(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    status_filter: EvalSetStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    eval_suite_service: EvalSuiteService = Depends(get_eval_suite_service),
) -> EvalSetListResponse:
    return await eval_suite_service.list_eval_sets(
        workspace_id=_workspace_id(request, current_user),
        status=status_filter,
        page=page,
        page_size=page_size,
    )


@router.get("/eval-sets/{eval_set_id}", response_model=EvalSetResponse)
async def get_eval_set(
    eval_set_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    eval_suite_service: EvalSuiteService = Depends(get_eval_suite_service),
) -> EvalSetResponse:
    return await eval_suite_service.get_eval_set(
        eval_set_id,
        _workspace_id(request, current_user),
    )


@router.patch("/eval-sets/{eval_set_id}", response_model=EvalSetResponse)
async def update_eval_set(
    eval_set_id: UUID,
    payload: EvalSetUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    eval_suite_service: EvalSuiteService = Depends(get_eval_suite_service),
) -> EvalSetResponse:
    _require_roles(current_user, {"workspace_admin", "platform_admin", "superadmin"})
    return await eval_suite_service.update_eval_set(eval_set_id, payload)


@router.delete("/eval-sets/{eval_set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_eval_set(
    eval_set_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    eval_suite_service: EvalSuiteService = Depends(get_eval_suite_service),
) -> Response:
    _require_roles(current_user, {"workspace_admin", "platform_admin", "superadmin"})
    await eval_suite_service.archive_eval_set(eval_set_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/eval-sets/{eval_set_id}/cases",
    response_model=BenchmarkCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_benchmark_case(
    eval_set_id: UUID,
    payload: BenchmarkCaseCreate,
    eval_suite_service: EvalSuiteService = Depends(get_eval_suite_service),
) -> BenchmarkCaseResponse:
    return await eval_suite_service.create_benchmark_case(eval_set_id, payload)


@router.get("/eval-sets/{eval_set_id}/cases", response_model=BenchmarkCaseListResponse)
async def list_benchmark_cases(
    eval_set_id: UUID,
    category: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    eval_suite_service: EvalSuiteService = Depends(get_eval_suite_service),
) -> BenchmarkCaseListResponse:
    return await eval_suite_service.list_benchmark_cases(
        eval_set_id=eval_set_id,
        category=category,
        page=page,
        page_size=page_size,
    )


@router.get("/eval-sets/{eval_set_id}/cases/{case_id}", response_model=BenchmarkCaseResponse)
async def get_benchmark_case(
    eval_set_id: UUID,
    case_id: UUID,
    eval_suite_service: EvalSuiteService = Depends(get_eval_suite_service),
) -> BenchmarkCaseResponse:
    return await eval_suite_service.get_benchmark_case(eval_set_id, case_id)


@router.delete("/eval-sets/{eval_set_id}/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_benchmark_case(
    eval_set_id: UUID,
    case_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    eval_suite_service: EvalSuiteService = Depends(get_eval_suite_service),
) -> Response:
    _require_roles(current_user, {"workspace_admin", "platform_admin", "superadmin"})
    await eval_suite_service.delete_benchmark_case(eval_set_id, case_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/eval-sets/{eval_set_id}/run",
    response_model=EvaluationRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_eval_set(
    eval_set_id: UUID,
    payload: EvaluationRunCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    eval_runner_service: EvalRunnerService = Depends(get_eval_runner_service),
) -> EvaluationRunResponse:
    run = await eval_runner_service.start_run(
        eval_set_id,
        payload,
        _workspace_id(request, current_user),
    )
    background_tasks.add_task(_run_eval_background, request.app, run.id)
    return run


@router.get("/runs", response_model=EvaluationRunListResponse)
async def list_runs(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    eval_set_id: UUID | None = Query(default=None),
    agent_fqn: str | None = Query(default=None),
    status_filter: RunStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    eval_runner_service: EvalRunnerService = Depends(get_eval_runner_service),
) -> EvaluationRunListResponse:
    return await eval_runner_service.list_runs(
        workspace_id=_workspace_id(request, current_user),
        eval_set_id=eval_set_id,
        agent_fqn=agent_fqn,
        status=status_filter,
        page=page,
        page_size=page_size,
    )


@router.get("/runs/{run_id}", response_model=EvaluationRunResponse)
async def get_run(
    run_id: UUID,
    eval_runner_service: EvalRunnerService = Depends(get_eval_runner_service),
) -> EvaluationRunResponse:
    return await eval_runner_service.get_run(run_id)


@router.get("/runs/{run_id}/verdicts", response_model=JudgeVerdictListResponse)
async def list_run_verdicts(
    run_id: UUID,
    passed: bool | None = Query(default=None),
    status_filter: VerdictStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    eval_runner_service: EvalRunnerService = Depends(get_eval_runner_service),
) -> JudgeVerdictListResponse:
    return await eval_runner_service.list_run_verdicts(
        run_id=run_id,
        passed=passed,
        status=status_filter,
        page=page,
        page_size=page_size,
    )


@router.get("/verdicts/{verdict_id}", response_model=JudgeVerdictResponse)
async def get_verdict(
    verdict_id: UUID,
    eval_runner_service: EvalRunnerService = Depends(get_eval_runner_service),
) -> JudgeVerdictResponse:
    return await eval_runner_service.get_verdict(verdict_id)


@router.post(
    "/experiments",
    response_model=AbExperimentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_experiment(
    payload: AbExperimentCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    ab_experiment_service: AbExperimentService = Depends(get_ab_experiment_service),
) -> AbExperimentResponse:
    workspace_id = _workspace_id(request, current_user, payload.workspace_id)
    experiment = await ab_experiment_service.start_experiment(
        payload.model_copy(update={"workspace_id": workspace_id})
    )
    background_tasks.add_task(_run_experiment_background, request.app, experiment.id)
    return experiment


@router.get("/experiments/{experiment_id}", response_model=AbExperimentResponse)
async def get_experiment(
    experiment_id: UUID,
    ab_experiment_service: AbExperimentService = Depends(get_ab_experiment_service),
) -> AbExperimentResponse:
    return await ab_experiment_service.get_experiment(experiment_id)


@router.post("/ate", response_model=ATEConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_ate_config(
    payload: ATEConfigCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    ate_service: ATEService = Depends(get_ate_service),
) -> ATEConfigResponse:
    _require_roles(current_user, {"workspace_admin", "platform_admin", "superadmin"})
    workspace_id = _workspace_id(request, current_user, payload.workspace_id)
    return await ate_service.create_config(
        payload.model_copy(update={"workspace_id": workspace_id}),
        _actor_id(current_user),
    )


@router.get("/ate", response_model=ATEConfigListResponse)
async def list_ate_configs(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ate_service: ATEService = Depends(get_ate_service),
) -> ATEConfigListResponse:
    return await ate_service.list_configs(
        workspace_id=_workspace_id(request, current_user),
        page=page,
        page_size=page_size,
    )


@router.get("/ate/{ate_config_id}", response_model=ATEConfigResponse)
async def get_ate_config(
    ate_config_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    ate_service: ATEService = Depends(get_ate_service),
) -> ATEConfigResponse:
    return await ate_service.get_config(
        ate_config_id,
        _workspace_id(request, current_user),
    )


@router.patch("/ate/{ate_config_id}", response_model=ATEConfigResponse)
async def update_ate_config(
    ate_config_id: UUID,
    payload: ATEConfigUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    ate_service: ATEService = Depends(get_ate_service),
) -> ATEConfigResponse:
    _require_roles(current_user, {"workspace_admin", "platform_admin", "superadmin"})
    return await ate_service.update_config(ate_config_id, payload)


@router.post(
    "/ate/{ate_config_id}/run/{agent_fqn:path}",
    response_model=ATERunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_ate(
    ate_config_id: UUID,
    agent_fqn: str,
    payload: ATERunRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    ate_service: ATEService = Depends(get_ate_service),
) -> ATERunResponse:
    workspace_id = _workspace_id(request, current_user)
    run = await ate_service.start_run(
        ate_config_id=ate_config_id,
        workspace_id=workspace_id,
        agent_fqn=agent_fqn,
        payload=payload,
    )
    if run.status is not ATERunStatus.pre_check_failed:
        background_tasks.add_task(_run_ate_background, request.app, run.id)
    return run


@router.get("/ate/{ate_config_id}/results", response_model=ATERunListResponse)
async def list_ate_results(
    ate_config_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ate_service: ATEService = Depends(get_ate_service),
) -> ATERunListResponse:
    return await ate_service.list_results(
        ate_config_id=ate_config_id,
        page=page,
        page_size=page_size,
    )


@router.get("/ate/runs/{ate_run_id}", response_model=ATERunResponse)
async def get_ate_run(
    ate_run_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    ate_service: ATEService = Depends(get_ate_service),
) -> ATERunResponse:
    return await ate_service.get_run(
        ate_run_id,
        _workspace_id(request, current_user),
    )


@router.post(
    "/robustness-runs",
    response_model=RobustnessTestRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_robustness_run(
    payload: RobustnessRunCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    robustness_service: RobustnessTestService = Depends(get_robustness_service),
) -> RobustnessTestRunResponse:
    workspace_id = _workspace_id(request, current_user, payload.workspace_id)
    run = await robustness_service.start_run(
        payload.model_copy(update={"workspace_id": workspace_id})
    )
    background_tasks.add_task(_run_robustness_background, request.app, run.id)
    return run


@router.get("/robustness-runs/{robustness_run_id}", response_model=RobustnessTestRunResponse)
async def get_robustness_run(
    robustness_run_id: UUID,
    robustness_service: RobustnessTestService = Depends(get_robustness_service),
) -> RobustnessTestRunResponse:
    return await robustness_service.get_run(robustness_run_id)


@router.get("/runs/{run_id}/review-progress", response_model=ReviewProgressResponse)
async def get_review_progress(
    run_id: UUID,
    human_grading_service: HumanGradingService = Depends(get_human_grading_service),
) -> ReviewProgressResponse:
    return await human_grading_service.get_review_progress(run_id)


@router.get("/verdicts/{verdict_id}/grade", response_model=HumanAiGradeResponse)
async def get_verdict_grade(
    verdict_id: UUID,
    human_grading_service: HumanGradingService = Depends(get_human_grading_service),
) -> HumanAiGradeResponse:
    return await human_grading_service.get_grade_for_verdict(verdict_id)


@router.post(
    "/verdicts/{verdict_id}/grade",
    response_model=HumanAiGradeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_verdict_grade(
    verdict_id: UUID,
    payload: HumanGradeSubmit,
    current_user: dict[str, Any] = Depends(get_current_user),
    human_grading_service: HumanGradingService = Depends(get_human_grading_service),
) -> HumanAiGradeResponse:
    _require_roles(current_user, {"evaluator", "workspace_admin", "platform_admin", "superadmin"})
    return await human_grading_service.submit_grade(
        verdict_id,
        _actor_id(current_user),
        payload,
    )


@router.patch("/grades/{grade_id}", response_model=HumanAiGradeResponse)
async def update_grade(
    grade_id: UUID,
    payload: HumanGradeUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    human_grading_service: HumanGradingService = Depends(get_human_grading_service),
) -> HumanAiGradeResponse:
    _require_roles(current_user, {"evaluator", "workspace_admin", "platform_admin", "superadmin"})
    return await human_grading_service.update_grade(grade_id, payload)
