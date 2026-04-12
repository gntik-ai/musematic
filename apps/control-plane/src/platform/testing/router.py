from __future__ import annotations

from platform.common import database
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user
from platform.common.events.producer import EventProducer
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.testing.coordination_service import CoordinationTestService
from platform.testing.dependencies import (
    build_test_suite_generation_service,
    get_coordination_service,
    get_drift_service,
    get_test_suite_generation_service,
)
from platform.testing.drift_service import DriftDetectionService
from platform.testing.models import AdversarialCategory, SuiteType
from platform.testing.schemas import (
    AdversarialCaseListResponse,
    CoordinationTestRequest,
    CoordinationTestResultResponse,
    DriftAlertListResponse,
    DriftAlertResponse,
    GeneratedTestSuiteListResponse,
    GeneratedTestSuiteResponse,
    GenerateSuiteRequest,
    ImportSuiteRequest,
    ImportSuiteResponse,
)
from platform.testing.suite_generation_service import TestSuiteGenerationService
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Query, Request, status

router = APIRouter(tags=["testing"])


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
    raise AuthorizationError("PERMISSION_DENIED", "Insufficient role for testing endpoint")


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


async def _generate_suite_background(
    app: FastAPI,
    suite_id: UUID,
    cases_per_category: int,
) -> None:
    async with database.AsyncSessionLocal() as session:
        settings = cast(PlatformSettings, app.state.settings)
        service = build_test_suite_generation_service(
            session=session,
            settings=settings,
            producer=cast(EventProducer | None, app.state.clients.get("kafka")),
            object_storage=cast(AsyncObjectStorageClient, app.state.clients["minio"]),
            registry_service=None,
        )
        try:
            await service.generate_suite(suite_id, cases_per_category=cases_per_category)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@router.post(
    "/suites/generate",
    response_model=GeneratedTestSuiteResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_suite(
    payload: GenerateSuiteRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    suite_service: TestSuiteGenerationService = Depends(get_test_suite_generation_service),
) -> GeneratedTestSuiteResponse:
    workspace_id = _workspace_id(request, current_user, payload.workspace_id)
    suite = await suite_service.start_generation(
        payload.model_copy(update={"workspace_id": workspace_id})
    )
    background_tasks.add_task(
        _generate_suite_background,
        request.app,
        suite.id,
        payload.cases_per_category,
    )
    return suite


@router.get("/suites", response_model=GeneratedTestSuiteListResponse)
async def list_suites(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    agent_fqn: str | None = Query(default=None),
    suite_type: SuiteType | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    suite_service: TestSuiteGenerationService = Depends(get_test_suite_generation_service),
) -> GeneratedTestSuiteListResponse:
    return await suite_service.list_suites(
        workspace_id=_workspace_id(request, current_user),
        agent_fqn=agent_fqn,
        suite_type=suite_type,
        page=page,
        page_size=page_size,
    )


@router.get("/suites/{suite_id}", response_model=GeneratedTestSuiteResponse)
async def get_suite(
    suite_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    suite_service: TestSuiteGenerationService = Depends(get_test_suite_generation_service),
) -> GeneratedTestSuiteResponse:
    return await suite_service.get_suite(suite_id, _workspace_id(request, current_user))


@router.get("/suites/{suite_id}/cases", response_model=AdversarialCaseListResponse)
async def list_suite_cases(
    suite_id: UUID,
    category: AdversarialCategory | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    suite_service: TestSuiteGenerationService = Depends(get_test_suite_generation_service),
) -> AdversarialCaseListResponse:
    return await suite_service.list_cases(
        suite_id=suite_id,
        category=category,
        page=page,
        page_size=page_size,
    )


@router.post("/suites/{suite_id}/import", response_model=ImportSuiteResponse)
async def import_suite(
    suite_id: UUID,
    payload: ImportSuiteRequest,
    suite_service: TestSuiteGenerationService = Depends(get_test_suite_generation_service),
) -> ImportSuiteResponse:
    return await suite_service.import_to_eval_set(suite_id, payload.eval_set_id)


@router.post(
    "/coordination-tests",
    response_model=CoordinationTestResultResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_coordination_test(
    payload: CoordinationTestRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    coordination_service: CoordinationTestService = Depends(get_coordination_service),
) -> CoordinationTestResultResponse:
    workspace_id = _workspace_id(request, current_user, payload.workspace_id)
    result = await coordination_service.run_coordination_test(
        payload.fleet_id,
        payload.execution_id or uuid4(),
        workspace_id,
    )
    return CoordinationTestResultResponse.model_validate(result)


@router.get("/coordination-tests/{result_id}", response_model=CoordinationTestResultResponse)
async def get_coordination_test(
    result_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    coordination_service: CoordinationTestService = Depends(get_coordination_service),
) -> CoordinationTestResultResponse:
    del request, current_user
    result = await coordination_service.repository.get_coordination_result(result_id)
    if result is None:
        raise ValidationError("COORDINATION_RESULT_NOT_FOUND", "Coordination test result not found")
    return CoordinationTestResultResponse.model_validate(result)


@router.get("/drift-alerts", response_model=DriftAlertListResponse)
async def list_drift_alerts(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    agent_fqn: str | None = Query(default=None),
    eval_set_id: UUID | None = Query(default=None),
    acknowledged: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    drift_service: DriftDetectionService = Depends(get_drift_service),
) -> DriftAlertListResponse:
    _require_roles(current_user, {"workspace_admin", "platform_admin", "superadmin"})
    return await drift_service.list_alerts(
        workspace_id=_workspace_id(request, current_user),
        agent_fqn=agent_fqn,
        eval_set_id=eval_set_id,
        acknowledged=acknowledged,
        page=page,
        page_size=page_size,
    )


@router.patch("/drift-alerts/{alert_id}/acknowledge", response_model=DriftAlertResponse)
async def acknowledge_drift_alert(
    alert_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    drift_service: DriftDetectionService = Depends(get_drift_service),
) -> DriftAlertResponse:
    _require_roles(current_user, {"workspace_admin", "platform_admin", "superadmin"})
    return await drift_service.acknowledge_alert(alert_id, _actor_id(current_user))
