from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from platform.audit.dependencies import build_audit_chain_service
from platform.auth.schemas import RoleType
from platform.common.audit_hook import audit_chain_hook
from platform.common.dependencies import get_current_user, get_db
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.common.tagging.filter_extension import parse_tag_label_filters
from platform.incident_response.dependencies import get_incident_response_service
from platform.incident_response.service import IncidentResponseService
from platform.policies.models import AttachmentTargetType, EnforcementComponent, PolicyScopeType
from platform.registry.models import AgentRoleType
from platform.trust.ate_service import ATEService
from platform.trust.circuit_breaker import CircuitBreakerService
from platform.trust.contract_schemas import (
    AgentContractCreate,
    AgentContractListResponse,
    AgentContractResponse,
    AgentContractUpdate,
    AttachRevisionRequest,
    CertifierCreate,
    CertifierListResponse,
    CertifierResponse,
    ComplianceRateQuery,
    ComplianceRateResponse,
    ContractAttachmentRequest,
    ContractBreachEventListResponse,
    ContractTemplateListResponse,
    DismissSuspensionRequest,
    FailureMode,
    ForkRequest,
    IssueWithCertifierRequest,
    PreviewRequest,
    PreviewResponse,
    ReassessmentCreate,
    ReassessmentListResponse,
    ReassessmentResponse,
    SchemaEnumsResponse,
    TrustRecertificationRequestListResponse,
    TrustRecertificationRequestResponse,
)
from platform.trust.contract_service import ContractService
from platform.trust.dependencies import (
    get_ate_service,
    get_certification_service,
    get_circuit_breaker_service,
    get_contract_service,
    get_guardrail_pipeline_service,
    get_oje_service,
    get_prescreener_service,
    get_privacy_assessment_service,
    get_recertification_service,
    get_trust_tier_service,
)
from platform.trust.guardrail_pipeline import GuardrailPipelineService
from platform.trust.models import GuardrailLayer
from platform.trust.oje_pipeline import OJEPipelineService
from platform.trust.prescreener import SafetyPreScreenerService
from platform.trust.privacy_assessment import PrivacyAssessmentService
from platform.trust.recertification import RecertificationService
from platform.trust.routers.moderation_events_router import router as moderation_events_router
from platform.trust.routers.moderation_policies_router import router as moderation_policies_router
from platform.trust.schemas import (
    ATEConfigCreate,
    ATEConfigListResponse,
    ATEConfigResponse,
    ATERunRequest,
    ATERunResponse,
    BlockedActionResponse,
    BlockedActionsListResponse,
    CertificationCreate,
    CertificationListResponse,
    CertificationResponse,
    CertificationRevoke,
    CircuitBreakerConfigCreate,
    CircuitBreakerConfigListResponse,
    CircuitBreakerConfigResponse,
    CircuitBreakerStatusResponse,
    EvidenceRefCreate,
    EvidenceRefResponse,
    GuardrailEvaluationRequest,
    GuardrailEvaluationResponse,
    GuardrailPipelineConfigCreate,
    GuardrailPipelineConfigResponse,
    OJEPipelineConfigCreate,
    OJEPipelineConfigListResponse,
    OJEPipelineConfigResponse,
    PreScreenerRuleSetCreate,
    PreScreenerRuleSetListResponse,
    PreScreenerRuleSetResponse,
    PreScreenRequest,
    PreScreenResponse,
    PrivacyAssessmentRequest,
    PrivacyAssessmentResponse,
    RecertificationTriggerListResponse,
    RecertificationTriggerResponse,
    TrustSignalListResponse,
    TrustTierResponse,
)
from platform.trust.service import CertificationService
from platform.trust.trust_tier import TrustTierService
from typing import Any, get_args
from uuid import UUID

import yaml
from fastapi import APIRouter, Body, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["trust"])
router.include_router(moderation_policies_router)
router.include_router(moderation_events_router)


def _role_names(current_user: dict[str, Any]) -> set[str]:
    roles = current_user.get("roles", [])
    return {str(item.get("role")) for item in roles if isinstance(item, dict)}


def _require_roles(current_user: dict[str, Any], accepted: set[str]) -> None:
    if _role_names(current_user) & accepted:
        return
    raise AuthorizationError("PERMISSION_DENIED", "Insufficient role for trust endpoint")


def _require_service_account(current_user: dict[str, Any]) -> None:
    if current_user.get("type") == "service":
        return
    if _role_names(current_user) & {"service_account", "platform_service", "superadmin"}:
        return
    raise AuthorizationError("PERMISSION_DENIED", "Service account required")


def _workspace_id(current_user: dict[str, Any]) -> UUID:
    raw = current_user.get("workspace_id")
    if raw in {None, ""}:
        raise ValidationError("WORKSPACE_REQUIRED", "Authenticated workspace_id is required")
    try:
        return UUID(str(raw))
    except ValueError as exc:
        raise ValidationError("WORKSPACE_INVALID", "Authenticated workspace_id is invalid") from exc


@router.post("/disclosure/version", tags=["trust-content-moderation"])
async def update_disclosure_version(
    request: Request,
    payload: dict[str, Any] = Body(...),
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_roles(current_user, {"workspace_admin", "platform_admin", "superadmin"})
    text = str(payload.get("text") or "").strip()
    if not text:
        raise ValidationError("DISCLOSURE_TEXT_REQUIRED", "Disclosure text is required")
    await _append_disclosure_audit(
        request,
        session,
        current_user,
        text,
        bool(payload.get("material")),
    )
    return {
        "disclosure_text_ref": "/api/v1/me/consents/disclosure",
        "material": bool(payload.get("material")),
        "updated": True,
    }


async def _append_disclosure_audit(
    request: Request,
    session: AsyncSession,
    current_user: dict[str, Any],
    text: str,
    material: bool,
) -> None:
    settings = getattr(request.app.state, "settings", None)
    if (
        settings is None
        or not hasattr(settings, "audit")
        or not callable(getattr(session, "execute", None))
    ):
        return
    clients = getattr(request.app.state, "clients", {})
    audit_chain = build_audit_chain_service(
        session=session,
        settings=settings,
        producer=clients.get("kafka") if hasattr(clients, "get") else None,
    )
    await audit_chain_hook(
        audit_chain,
        None,
        "trust.disclosure.version",
        {
            "actor_id": current_user.get("sub"),
            "material": material,
            "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "occurred_at": datetime.now(UTC),
        },
    )


@router.post(
    "/certifications", response_model=CertificationResponse, status_code=status.HTTP_201_CREATED
)
async def create_certification(
    payload: CertificationCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    certification_service: CertificationService = Depends(get_certification_service),
) -> CertificationResponse:
    _require_roles(current_user, {"platform_admin", "trust_certifier", "superadmin"})
    return await certification_service.create(payload, str(current_user["sub"]))


@router.post(
    "/contracts",
    response_model=AgentContractResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_contract(
    payload: AgentContractCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    contract_service: ContractService = Depends(get_contract_service),
) -> AgentContractResponse:
    _require_roles(current_user, {"agent_owner", "platform_admin", "superadmin"})
    return await contract_service.create_contract(
        payload,
        _workspace_id(current_user),
        current_user.get("sub"),
    )


@router.get("/contracts", response_model=AgentContractListResponse)
async def list_contracts(
    agent_id: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    current_user: dict[str, Any] = Depends(get_current_user),
    contract_service: ContractService = Depends(get_contract_service),
) -> AgentContractListResponse:
    _require_roles(
        current_user,
        {
            "workspace_member",
            "workspace_admin",
            "agent_owner",
            "platform_admin",
            "compliance_officer",
            "superadmin",
        },
    )
    return await contract_service.list_contracts(
        _workspace_id(current_user),
        agent_id=agent_id,
        include_archived=include_archived,
    )


@router.get("/contracts/schema")
async def get_contract_schema() -> dict[str, Any]:
    return AgentContractCreate.model_json_schema()


@router.get("/contracts/schema-enums", response_model=SchemaEnumsResponse)
async def get_contract_schema_enums(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> SchemaEnumsResponse:
    _require_roles(
        current_user,
        {"workspace_member", "agent_owner", "platform_admin", "superadmin"},
    )
    return SchemaEnumsResponse(
        resource_types=[
            *[item.value for item in PolicyScopeType],
            *[item.value for item in AttachmentTargetType],
            *[item.value for item in EnforcementComponent],
        ],
        role_types=[item.value for item in RoleType] + [item.value for item in AgentRoleType],
        workspace_constraints=["workspace_visibility", "quota", "residency", "approval_required"],
        failure_modes=list(get_args(FailureMode)),
    )


@router.get("/contracts/templates", response_model=ContractTemplateListResponse)
async def list_contract_templates(
    current_user: dict[str, Any] = Depends(get_current_user),
    contract_service: ContractService = Depends(get_contract_service),
) -> ContractTemplateListResponse:
    _require_roles(
        current_user,
        {"workspace_member", "agent_owner", "platform_admin", "superadmin"},
    )
    return await contract_service.list_templates()


@router.get("/contracts/{contract_id}", response_model=AgentContractResponse)
async def get_contract(
    contract_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    contract_service: ContractService = Depends(get_contract_service),
) -> AgentContractResponse:
    return await contract_service.get_contract(
        contract_id,
        workspace_id=_workspace_id(current_user),
    )


@router.post("/contracts/{contract_id}/preview", response_model=PreviewResponse)
async def preview_contract(
    contract_id: UUID,
    payload: PreviewRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    contract_service: ContractService = Depends(get_contract_service),
) -> PreviewResponse:
    _require_roles(current_user, {"agent_owner", "platform_admin", "superadmin"})
    return await contract_service.preview_contract(
        contract_id,
        payload.sample_input,
        use_mock=payload.use_mock,
        cost_acknowledged=payload.cost_acknowledged,
        workspace_id=_workspace_id(current_user),
    )


@router.post(
    "/contracts/{template_id}/fork",
    response_model=AgentContractResponse,
    status_code=status.HTTP_201_CREATED,
)
async def fork_contract_template(
    template_id: UUID,
    payload: ForkRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    contract_service: ContractService = Depends(get_contract_service),
) -> AgentContractResponse:
    _require_roles(current_user, {"agent_owner", "platform_admin", "superadmin"})
    return await contract_service.fork_template(
        template_id,
        payload.new_name,
        _workspace_id(current_user),
        UUID(str(current_user["sub"])),
    )


@router.post("/contracts/{contract_id}/attach-revision/{revision_id}", status_code=204)
async def attach_contract_to_revision(
    contract_id: UUID,
    revision_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    contract_service: ContractService = Depends(get_contract_service),
) -> Response:
    _require_roles(current_user, {"agent_owner", "platform_admin", "superadmin"})
    await contract_service.attach_to_revision(
        contract_id,
        revision_id,
        UUID(str(current_user["sub"])),
        workspace_id=_workspace_id(current_user),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/contracts/{contract_id}/attach-revision", status_code=204)
async def attach_contract_to_revision_body(
    contract_id: UUID,
    payload: AttachRevisionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    contract_service: ContractService = Depends(get_contract_service),
) -> Response:
    _require_roles(current_user, {"agent_owner", "platform_admin", "superadmin"})
    await contract_service.attach_to_revision(
        contract_id,
        payload.revision_id,
        UUID(str(current_user["sub"])),
        workspace_id=_workspace_id(current_user),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/contracts/{contract_id}", response_model=AgentContractResponse)
async def update_contract(
    contract_id: UUID,
    payload: AgentContractUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    contract_service: ContractService = Depends(get_contract_service),
) -> AgentContractResponse:
    _require_roles(current_user, {"agent_owner", "platform_admin", "superadmin"})
    return await contract_service.update_contract(
        contract_id,
        payload,
        current_user.get("sub"),
        workspace_id=_workspace_id(current_user),
    )


@router.delete("/contracts/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_contract(
    contract_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    contract_service: ContractService = Depends(get_contract_service),
) -> Response:
    _require_roles(current_user, {"agent_owner", "platform_admin", "superadmin"})
    await contract_service.archive_contract(
        contract_id,
        current_user.get("sub"),
        workspace_id=_workspace_id(current_user),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/contracts/{contract_id}/attach-interaction", status_code=status.HTTP_204_NO_CONTENT)
async def attach_contract_to_interaction(
    contract_id: UUID,
    payload: ContractAttachmentRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    contract_service: ContractService = Depends(get_contract_service),
) -> Response:
    _require_roles(current_user, {"agent_owner", "platform_admin", "superadmin"})
    if payload.interaction_id is None:
        raise ValidationError("INTERACTION_REQUIRED", "interaction_id is required")
    await contract_service.attach_to_interaction(
        payload.interaction_id,
        contract_id,
        workspace_id=_workspace_id(current_user),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/contracts/{contract_id}/attach-execution", status_code=status.HTTP_204_NO_CONTENT)
async def attach_contract_to_execution(
    contract_id: UUID,
    payload: ContractAttachmentRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    contract_service: ContractService = Depends(get_contract_service),
) -> Response:
    _require_roles(current_user, {"agent_owner", "platform_admin", "superadmin"})
    if payload.execution_id is None:
        raise ValidationError("EXECUTION_REQUIRED", "execution_id is required")
    await contract_service.attach_to_execution(
        payload.execution_id,
        contract_id,
        workspace_id=_workspace_id(current_user),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/contracts/{contract_id}/breaches", response_model=ContractBreachEventListResponse)
async def list_contract_breaches(
    contract_id: UUID,
    target_type: str | None = Query(default=None),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: dict[str, Any] = Depends(get_current_user),
    contract_service: ContractService = Depends(get_contract_service),
) -> ContractBreachEventListResponse:
    _require_roles(
        current_user,
        {"agent_owner", "platform_admin", "compliance_officer", "superadmin"},
    )
    return await contract_service.list_breach_events(
        contract_id,
        workspace_id=_workspace_id(current_user),
        target_type=target_type,
        start=start,
        end=end,
        offset=(page - 1) * page_size,
        limit=page_size,
    )


@router.get("/compliance/rates", response_model=ComplianceRateResponse)
async def get_compliance_rates(
    scope: str = Query(),
    scope_id: str = Query(),
    start: datetime = Query(),
    end: datetime = Query(),
    bucket: str = Query(default="daily"),
    current_user: dict[str, Any] = Depends(get_current_user),
    contract_service: ContractService = Depends(get_contract_service),
) -> ComplianceRateResponse:
    _require_roles(current_user, {"compliance_officer", "platform_admin", "superadmin"})
    query = ComplianceRateQuery(
        scope=scope,
        scope_id=scope_id,
        start=start,
        end=end,
        bucket=bucket,
    )
    return await contract_service.get_compliance_rates(query, _workspace_id(current_user))


@router.post("/certifiers", response_model=CertifierResponse, status_code=status.HTTP_201_CREATED)
async def create_certifier(
    payload: CertifierCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    certification_service: CertificationService = Depends(get_certification_service),
) -> CertifierResponse:
    _require_roles(current_user, {"platform_admin", "compliance_officer", "superadmin"})
    return await certification_service.create_certifier(payload, str(current_user["sub"]))


@router.get("/certifiers", response_model=CertifierListResponse)
async def list_certifiers(
    include_inactive: bool = Query(default=False),
    current_user: dict[str, Any] = Depends(get_current_user),
    certification_service: CertificationService = Depends(get_certification_service),
) -> CertifierListResponse:
    del current_user
    return await certification_service.list_certifiers(include_inactive=include_inactive)


@router.get("/certifiers/{certifier_id}", response_model=CertifierResponse)
async def get_certifier(
    certifier_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    certification_service: CertificationService = Depends(get_certification_service),
) -> CertifierResponse:
    del current_user
    return await certification_service.get_certifier(certifier_id)


@router.delete("/certifiers/{certifier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_certifier(
    certifier_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    certification_service: CertificationService = Depends(get_certification_service),
) -> Response:
    _require_roles(current_user, {"platform_admin", "superadmin"})
    await certification_service.deactivate_certifier(certifier_id, str(current_user["sub"]))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/certifications/{certification_id}", response_model=CertificationResponse)
async def get_certification(
    certification_id: UUID,
    certification_service: CertificationService = Depends(get_certification_service),
    incident_response_service: IncidentResponseService = Depends(get_incident_response_service),
) -> CertificationResponse:
    response = await certification_service.get(certification_id)
    finder = getattr(incident_response_service, "find_post_mortems_for_certification", None)
    if callable(finder):
        post_mortems = await finder(certification_id)
        response.post_mortems = [item.model_dump(mode="json") for item in post_mortems]
    return response


@router.get("/agents/{agent_id}/certifications", response_model=CertificationListResponse)
async def list_agent_certifications(
    agent_id: str,
    request: Request,
    certification_service: CertificationService = Depends(get_certification_service),
) -> CertificationListResponse:
    items = await certification_service.list_for_agent(
        agent_id,
        tag_label_filters=parse_tag_label_filters(request),
    )
    return CertificationListResponse(items=items, total=len(items))


@router.post("/certifications/{certification_id}/activate", response_model=CertificationResponse)
async def activate_certification(
    certification_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    certification_service: CertificationService = Depends(get_certification_service),
) -> CertificationResponse:
    _require_roles(current_user, {"trust_certifier", "platform_admin", "superadmin"})
    return await certification_service.activate(certification_id, str(current_user["sub"]))


@router.post("/certifications/{certification_id}/revoke", response_model=CertificationResponse)
async def revoke_certification(
    certification_id: UUID,
    payload: CertificationRevoke,
    current_user: dict[str, Any] = Depends(get_current_user),
    certification_service: CertificationService = Depends(get_certification_service),
) -> CertificationResponse:
    _require_roles(current_user, {"trust_certifier", "platform_admin", "superadmin"})
    return await certification_service.revoke(
        certification_id, payload.reason, str(current_user["sub"])
    )


@router.post(
    "/certifications/{certification_id}/evidence",
    response_model=EvidenceRefResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_certification_evidence(
    certification_id: UUID,
    payload: EvidenceRefCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    certification_service: CertificationService = Depends(get_certification_service),
) -> EvidenceRefResponse:
    _require_roles(current_user, {"trust_certifier", "platform_admin", "superadmin"})
    return await certification_service.add_evidence(certification_id, payload)


@router.post(
    "/certifications/{certification_id}/issue-with-certifier",
    response_model=CertificationResponse,
)
async def issue_with_certifier(
    certification_id: UUID,
    payload: IssueWithCertifierRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    certification_service: CertificationService = Depends(get_certification_service),
) -> CertificationResponse:
    _require_roles(current_user, {"platform_admin", "compliance_officer", "superadmin"})
    return await certification_service.issue_with_certifier(
        certification_id,
        payload.certifier_id,
        payload.scope,
        str(current_user["sub"]),
    )


@router.get(
    "/certifications/{certification_id}/reassessments",
    response_model=ReassessmentListResponse,
)
async def list_reassessments(
    certification_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    certification_service: CertificationService = Depends(get_certification_service),
) -> ReassessmentListResponse:
    del current_user
    return await certification_service.list_reassessments(certification_id)


@router.post(
    "/certifications/{certification_id}/reassessments",
    response_model=ReassessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reassessment(
    certification_id: UUID,
    payload: ReassessmentCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    certification_service: CertificationService = Depends(get_certification_service),
) -> ReassessmentResponse:
    _require_roles(current_user, {"platform_admin", "compliance_officer", "superadmin"})
    return await certification_service.record_reassessment(
        certification_id,
        payload,
        str(current_user["sub"]),
    )


@router.post(
    "/certifications/{certification_id}/dismiss-suspension",
    response_model=CertificationResponse,
)
async def dismiss_suspension(
    certification_id: UUID,
    payload: DismissSuspensionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    certification_service: CertificationService = Depends(get_certification_service),
) -> CertificationResponse:
    _require_roles(current_user, {"platform_admin", "superadmin"})
    return await certification_service.dismiss_suspension(
        certification_id,
        payload.justification,
        str(current_user["sub"]),
    )


@router.get(
    "/recertification-requests",
    response_model=TrustRecertificationRequestListResponse,
)
async def list_recertification_requests_v2(
    certification_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    certification_service: CertificationService = Depends(get_certification_service),
) -> TrustRecertificationRequestListResponse:
    _require_roles(current_user, {"platform_admin", "compliance_officer", "superadmin"})
    return await certification_service.list_recertification_requests(
        certification_id=certification_id,
        status=status,
    )


@router.get(
    "/recertification-requests/{request_id}",
    response_model=TrustRecertificationRequestResponse,
)
async def get_recertification_request_v2(
    request_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    certification_service: CertificationService = Depends(get_certification_service),
) -> TrustRecertificationRequestResponse:
    _require_roles(current_user, {"platform_admin", "compliance_officer", "superadmin"})
    return await certification_service.get_recertification_request(request_id)


@router.get("/agents/{agent_id}/tier", response_model=TrustTierResponse)
async def get_agent_tier(
    agent_id: str,
    trust_tier_service: TrustTierService = Depends(get_trust_tier_service),
) -> TrustTierResponse:
    return await trust_tier_service.get_tier(agent_id)


@router.get("/agents/{agent_id}/signals", response_model=TrustSignalListResponse)
async def list_agent_signals(
    agent_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    trust_tier_service: TrustTierService = Depends(get_trust_tier_service),
) -> TrustSignalListResponse:
    _require_roles(current_user, {"trust_certifier", "platform_admin", "superadmin"})
    repo = trust_tier_service.repository
    items, total = await repo.list_trust_signals_for_agent(
        agent_id,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    from platform.trust.schemas import TrustSignalResponse

    return TrustSignalListResponse(
        items=[TrustSignalResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/guardrails/evaluate", response_model=GuardrailEvaluationResponse)
async def evaluate_guardrail(
    payload: GuardrailEvaluationRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    guardrail_service: GuardrailPipelineService = Depends(get_guardrail_pipeline_service),
) -> GuardrailEvaluationResponse:
    _require_service_account(current_user)
    return await guardrail_service.evaluate_full_pipeline(payload)


@router.get("/guardrails/blocked-actions", response_model=BlockedActionsListResponse)
async def list_blocked_actions(
    agent_id: str | None = Query(default=None),
    layer: GuardrailLayer | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    guardrail_service: GuardrailPipelineService = Depends(get_guardrail_pipeline_service),
) -> BlockedActionsListResponse:
    _require_roles(current_user, {"trust_certifier", "platform_admin", "superadmin"})
    return await guardrail_service.list_blocked_actions(
        agent_id=agent_id,
        layer=layer,
        workspace_id=workspace_id,
        since=since,
        until=until,
        page=page,
        page_size=page_size,
    )


@router.get("/guardrails/blocked-actions/{record_id}", response_model=BlockedActionResponse)
async def get_blocked_action(
    record_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    guardrail_service: GuardrailPipelineService = Depends(get_guardrail_pipeline_service),
) -> BlockedActionResponse:
    _require_roles(current_user, {"trust_certifier", "platform_admin", "superadmin"})
    item = await guardrail_service.get_blocked_action(record_id)
    if item is None:
        raise ValidationError("TRUST_BLOCKED_ACTION_NOT_FOUND", "Blocked action record not found")
    return item


@router.get("/guardrails/config", response_model=GuardrailPipelineConfigResponse)
async def get_guardrail_config(
    workspace_id: str = Query(...),
    fleet_id: str | None = Query(default=None),
    guardrail_service: GuardrailPipelineService = Depends(get_guardrail_pipeline_service),
) -> GuardrailPipelineConfigResponse:
    item = await guardrail_service.get_config(workspace_id, fleet_id)
    if item is None:
        raise ValidationError("TRUST_GUARDRAIL_CONFIG_NOT_FOUND", "Guardrail config not found")
    return item


@router.put("/guardrails/config", response_model=GuardrailPipelineConfigResponse)
async def update_guardrail_config(
    payload: GuardrailPipelineConfigCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    guardrail_service: GuardrailPipelineService = Depends(get_guardrail_pipeline_service),
) -> GuardrailPipelineConfigResponse:
    _require_roles(current_user, {"workspace_admin", "platform_admin", "superadmin"})
    return await guardrail_service.update_config(
        payload.workspace_id,
        payload.fleet_id,
        payload.config,
        is_active=payload.is_active,
    )


@router.post("/prescreener/screen", response_model=PreScreenResponse)
async def prescreen(
    payload: PreScreenRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    prescreener_service: SafetyPreScreenerService = Depends(get_prescreener_service),
) -> PreScreenResponse:
    _require_service_account(current_user)
    return await prescreener_service.screen(payload.content, payload.context_type)


@router.get("/prescreener/rule-sets", response_model=PreScreenerRuleSetListResponse)
async def list_prescreener_rule_sets(
    current_user: dict[str, Any] = Depends(get_current_user),
    prescreener_service: SafetyPreScreenerService = Depends(get_prescreener_service),
) -> PreScreenerRuleSetListResponse:
    _require_roles(current_user, {"platform_admin", "superadmin"})
    return await prescreener_service.list_rule_sets()


@router.post(
    "/prescreener/rule-sets",
    response_model=PreScreenerRuleSetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_prescreener_rule_set(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    prescreener_service: SafetyPreScreenerService = Depends(get_prescreener_service),
) -> PreScreenerRuleSetResponse:
    _require_roles(current_user, {"platform_admin", "superadmin"})
    content_type = request.headers.get("content-type", "application/json").split(";")[0].strip()
    raw = await request.body()
    if content_type == "application/yaml":
        try:
            data = yaml.safe_load(raw.decode("utf-8"))
        except yaml.YAMLError as exc:
            raise ValidationError("YAML_PARSE_ERROR", str(exc)) from exc
    else:
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValidationError("JSON_PARSE_ERROR", str(exc)) from exc
    payload = PreScreenerRuleSetCreate.model_validate(data)
    return await prescreener_service.create_rule_set(payload)


@router.post(
    "/prescreener/rule-sets/{rule_set_id}/activate", response_model=PreScreenerRuleSetResponse
)
async def activate_prescreener_rule_set(
    rule_set_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    prescreener_service: SafetyPreScreenerService = Depends(get_prescreener_service),
) -> PreScreenerRuleSetResponse:
    _require_roles(current_user, {"platform_admin", "superadmin"})
    return await prescreener_service.activate_rule_set(rule_set_id)


@router.get("/oje-configs", response_model=OJEPipelineConfigListResponse)
async def list_oje_configs(
    workspace_id: str = Query(...),
    current_user: dict[str, Any] = Depends(get_current_user),
    oje_service: OJEPipelineService = Depends(get_oje_service),
) -> OJEPipelineConfigListResponse:
    _require_roles(current_user, {"workspace_admin", "platform_admin", "superadmin"})
    return await oje_service.list_pipeline_configs(workspace_id)


@router.post(
    "/oje-configs", response_model=OJEPipelineConfigResponse, status_code=status.HTTP_201_CREATED
)
async def create_oje_config(
    payload: OJEPipelineConfigCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    oje_service: OJEPipelineService = Depends(get_oje_service),
) -> OJEPipelineConfigResponse:
    _require_roles(current_user, {"workspace_admin", "platform_admin", "superadmin"})
    return await oje_service.configure_pipeline(payload)


@router.get("/oje-configs/{config_id}", response_model=OJEPipelineConfigResponse)
async def get_oje_config(
    config_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    oje_service: OJEPipelineService = Depends(get_oje_service),
) -> OJEPipelineConfigResponse:
    _require_roles(current_user, {"workspace_admin", "platform_admin", "superadmin"})
    return await oje_service.get_pipeline_config_by_id(config_id)


@router.delete("/oje-configs/{config_id}", response_model=OJEPipelineConfigResponse)
async def deactivate_oje_config(
    config_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    oje_service: OJEPipelineService = Depends(get_oje_service),
) -> OJEPipelineConfigResponse:
    _require_roles(current_user, {"workspace_admin", "platform_admin", "superadmin"})
    return await oje_service.deactivate_pipeline(config_id)


@router.get("/recertification-triggers", response_model=RecertificationTriggerListResponse)
async def list_recertification_triggers(
    agent_id: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    recertification_service: RecertificationService = Depends(get_recertification_service),
) -> RecertificationTriggerListResponse:
    _require_roles(current_user, {"trust_certifier", "platform_admin", "superadmin"})
    return await recertification_service.list_triggers(agent_id)


@router.get("/recertification-triggers/{trigger_id}", response_model=RecertificationTriggerResponse)
async def get_recertification_trigger(
    trigger_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    recertification_service: RecertificationService = Depends(get_recertification_service),
) -> RecertificationTriggerResponse:
    _require_roles(current_user, {"trust_certifier", "platform_admin", "superadmin"})
    return await recertification_service.get_trigger(trigger_id)


@router.get("/ate/configs", response_model=ATEConfigListResponse)
async def list_ate_configs(
    workspace_id: str = Query(...),
    current_user: dict[str, Any] = Depends(get_current_user),
    ate_service: ATEService = Depends(get_ate_service),
) -> ATEConfigListResponse:
    _require_roles(
        current_user, {"workspace_admin", "platform_admin", "superadmin", "workspace_member"}
    )
    return await ate_service.list_configs(workspace_id)


@router.post("/ate/configs", response_model=ATEConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_ate_config(
    workspace_id: str = Query(...),
    payload: ATEConfigCreate = Body(...),
    current_user: dict[str, Any] = Depends(get_current_user),
    ate_service: ATEService = Depends(get_ate_service),
) -> ATEConfigResponse:
    _require_roles(current_user, {"workspace_admin", "platform_admin", "superadmin"})
    return await ate_service.create_config(workspace_id, payload)


@router.get("/ate/configs/{config_id}", response_model=ATEConfigResponse)
async def get_ate_config(
    config_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    ate_service: ATEService = Depends(get_ate_service),
) -> ATEConfigResponse:
    _require_roles(
        current_user, {"workspace_admin", "platform_admin", "superadmin", "workspace_member"}
    )
    return await ate_service.get_config(config_id)


@router.post("/ate/runs", response_model=ATERunResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_ate_run(
    payload: ATERunRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    ate_service: ATEService = Depends(get_ate_service),
) -> ATERunResponse:
    _require_roles(current_user, {"trust_certifier", "platform_admin", "superadmin"})
    return await ate_service.run(payload)


@router.get("/ate/runs/{simulation_id}", response_model=ATERunResponse)
async def get_ate_run(
    simulation_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    ate_service: ATEService = Depends(get_ate_service),
) -> ATERunResponse:
    _require_roles(current_user, {"trust_certifier", "platform_admin", "superadmin"})
    return await ate_service.get_run_status(simulation_id)


@router.get("/circuit-breaker/{agent_id}/status", response_model=CircuitBreakerStatusResponse)
async def get_circuit_breaker_status(
    agent_id: str,
    workspace_id: str = Query(...),
    fleet_id: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    circuit_breaker_service: CircuitBreakerService = Depends(get_circuit_breaker_service),
) -> CircuitBreakerStatusResponse:
    _require_roles(current_user, {"workspace_admin", "platform_admin", "superadmin"})
    return await circuit_breaker_service.get_status(agent_id, workspace_id, fleet_id=fleet_id)


@router.post("/circuit-breaker/{agent_id}/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_circuit_breaker(
    agent_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    circuit_breaker_service: CircuitBreakerService = Depends(get_circuit_breaker_service),
) -> Response:
    _require_roles(current_user, {"platform_admin", "superadmin"})
    await circuit_breaker_service.reset(agent_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/circuit-breaker/configs", response_model=CircuitBreakerConfigListResponse)
async def list_circuit_breaker_configs(
    workspace_id: str = Query(...),
    current_user: dict[str, Any] = Depends(get_current_user),
    circuit_breaker_service: CircuitBreakerService = Depends(get_circuit_breaker_service),
) -> CircuitBreakerConfigListResponse:
    _require_roles(current_user, {"workspace_admin", "platform_admin", "superadmin"})
    return await circuit_breaker_service.list_configs(workspace_id)


@router.post(
    "/circuit-breaker/configs",
    response_model=CircuitBreakerConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upsert_circuit_breaker_config(
    payload: CircuitBreakerConfigCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    circuit_breaker_service: CircuitBreakerService = Depends(get_circuit_breaker_service),
) -> CircuitBreakerConfigResponse:
    _require_roles(current_user, {"workspace_admin", "platform_admin", "superadmin"})
    return await circuit_breaker_service.upsert_config(payload)


@router.post("/privacy/assess", response_model=PrivacyAssessmentResponse)
async def assess_privacy(
    payload: PrivacyAssessmentRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    privacy_service: PrivacyAssessmentService = Depends(get_privacy_assessment_service),
) -> PrivacyAssessmentResponse:
    _require_service_account(current_user)
    return await privacy_service.assess(payload)
