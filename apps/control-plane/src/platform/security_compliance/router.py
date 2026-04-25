from __future__ import annotations

from datetime import datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.security_compliance.dependencies import (
    get_compliance_service,
    get_jit_service,
    get_pentest_service,
    get_rotation_service,
    get_sbom_service,
    get_vuln_scan_service,
)
from platform.security_compliance.schemas import (
    BundleExportRequest,
    BundleExportResponse,
    ComplianceEvidenceResponse,
    FrameworkListResponse,
    FrameworkResponse,
    JitApprovalRequest,
    JitApproverPolicyResponse,
    JitGrantRequest,
    JitGrantResponse,
    JitRejectRequest,
    JitUsageRequest,
    ManualEvidenceFormResponse,
    PentestExecuteRequest,
    PentestFindingResponse,
    PentestFindingsImportRequest,
    PentestFindingUpdate,
    PentestResponse,
    PentestScheduleRequest,
    RotationResponse,
    RotationScheduleCreate,
    RotationScheduleUpdate,
    RotationTriggerRequest,
    RotationTriggerResponse,
    SbomHashResponse,
    SbomIngestRequest,
    SbomResponse,
    ScanIngestRequest,
    ScanResultResponse,
    ScanStatusResponse,
    VulnerabilityExceptionCreate,
    VulnerabilityExceptionResponse,
)
from platform.security_compliance.services.compliance_service import ComplianceService
from platform.security_compliance.services.jit_service import JitService
from platform.security_compliance.services.pentest_service import PentestService
from platform.security_compliance.services.sbom_service import SbomService
from platform.security_compliance.services.secret_rotation_service import SecretRotationService
from platform.security_compliance.services.vuln_scan_service import VulnScanService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

router = APIRouter(prefix="/api/v1/security", tags=["admin", "security"])


def _role_names(current_user: dict[str, Any]) -> set[str]:
    roles = current_user.get("roles", [])
    return {str(item.get("role")) for item in roles if isinstance(item, dict)}


def _require_roles(current_user: dict[str, Any], accepted: set[str]) -> None:
    if _role_names(current_user) & accepted:
        return
    raise AuthorizationError("PERMISSION_DENIED", "Insufficient role for security endpoint")


def _subject(current_user: dict[str, Any]) -> UUID:
    try:
        return UUID(str(current_user["sub"]))
    except Exception as exc:
        raise ValidationError("USER_ID_REQUIRED", "Authenticated user id required") from exc


def _pentest_response(pentest: Any, findings: list[Any] | None = None) -> PentestResponse:
    return PentestResponse.model_validate(pentest).model_copy(
        update={
            "findings": [
                PentestFindingResponse.model_validate(finding) for finding in (findings or [])
            ]
        }
    )


@router.post("/sbom", response_model=SbomResponse, tags=["admin", "security", "sbom"])
async def ingest_sbom(
    payload: SbomIngestRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: SbomService = Depends(get_sbom_service),
) -> SbomResponse:
    _require_roles(current_user, {"release_publisher", "platform_admin", "superadmin"})
    return SbomResponse.model_validate(
        await service.ingest(
            release_version=payload.release_version,
            sbom_format=payload.format,
            content=payload.content,
        )
    )


@router.get(
    "/sbom/{release_version}", response_model=SbomResponse, tags=["admin", "security", "sbom"]
)
async def get_sbom(
    release_version: str,
    sbom_format: str = Query(..., alias="format"),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: SbomService = Depends(get_sbom_service),
) -> SbomResponse:
    _require_roles(current_user, {"auditor", "superadmin"})
    return SbomResponse.model_validate(await service.get(release_version, sbom_format))


@router.get(
    "/sbom/{release_version}/hash",
    response_model=SbomHashResponse,
    tags=["admin", "security", "sbom"],
)
async def get_sbom_hash(
    release_version: str,
    sbom_format: str = Query(..., alias="format"),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: SbomService = Depends(get_sbom_service),
) -> SbomHashResponse:
    _require_roles(current_user, {"auditor", "superadmin"})
    digest, valid = await service.get_hash(release_version, sbom_format)
    return SbomHashResponse(
        release_version=release_version,
        format=sbom_format,
        content_sha256=digest,
        valid=valid,
    )


@router.post(
    "/scans/{release_version}/results",
    response_model=ScanResultResponse,
    tags=["admin", "security", "scans"],
)
async def ingest_scan_result(
    release_version: str,
    payload: ScanIngestRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: VulnScanService = Depends(get_vuln_scan_service),
) -> ScanResultResponse:
    _require_roles(current_user, {"release_publisher", "platform_admin", "superadmin"})
    scan = await service.ingest_scan(
        release_version=release_version,
        scanner=payload.scanner,
        findings=[item.model_dump() for item in payload.findings],
        max_severity=payload.max_severity,
        gating_result=payload.gating_result,
    )
    return ScanResultResponse.model_validate(scan)


@router.get(
    "/scans/{release_version}",
    response_model=list[ScanResultResponse],
    tags=["admin", "security", "scans"],
)
async def list_scan_results(
    release_version: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: VulnScanService = Depends(get_vuln_scan_service),
) -> list[ScanResultResponse]:
    _require_roles(current_user, {"auditor", "superadmin"})
    return [
        ScanResultResponse.model_validate(item)
        for item in await service.repository.list_scans(release_version)
    ]


@router.get(
    "/scans/{release_version}/status",
    response_model=ScanStatusResponse,
    tags=["admin", "security", "scans"],
)
async def get_scan_status(
    release_version: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: VulnScanService = Depends(get_vuln_scan_service),
) -> ScanStatusResponse:
    _require_roles(current_user, {"auditor", "superadmin"})
    return ScanStatusResponse.model_validate(await service.evaluate_gating(release_version))


@router.post(
    "/vulnerability-exceptions",
    response_model=VulnerabilityExceptionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["admin", "security", "exceptions"],
)
async def create_vulnerability_exception(
    payload: VulnerabilityExceptionCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: VulnScanService = Depends(get_vuln_scan_service),
) -> VulnerabilityExceptionResponse:
    _require_roles(current_user, {"superadmin"})
    item = await service.create_exception(
        **payload.model_dump(), requester_id=_subject(current_user)
    )
    return VulnerabilityExceptionResponse.model_validate(item)


@router.get(
    "/vulnerability-exceptions",
    response_model=list[VulnerabilityExceptionResponse],
    tags=["admin", "security", "exceptions"],
)
async def list_vulnerability_exceptions(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: VulnScanService = Depends(get_vuln_scan_service),
) -> list[VulnerabilityExceptionResponse]:
    _require_roles(current_user, {"auditor", "superadmin"})
    return [
        VulnerabilityExceptionResponse.model_validate(item)
        for item in await service.list_active_exceptions()
    ]


@router.get(
    "/rotations", response_model=list[RotationResponse], tags=["admin", "security", "rotations"]
)
async def list_rotations(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: SecretRotationService = Depends(get_rotation_service),
) -> list[RotationResponse]:
    _require_roles(current_user, {"auditor", "superadmin"})
    return [RotationResponse.model_validate(item) for item in await service.list_schedules()]


@router.post("/rotations", response_model=RotationResponse, tags=["admin", "security", "rotations"])
async def create_rotation(
    payload: RotationScheduleCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: SecretRotationService = Depends(get_rotation_service),
) -> RotationResponse:
    _require_roles(current_user, {"superadmin"})
    return RotationResponse.model_validate(await service.create_schedule(**payload.model_dump()))


@router.patch(
    "/rotations/{rotation_id}",
    response_model=RotationResponse,
    tags=["admin", "security", "rotations"],
)
async def update_rotation(
    rotation_id: UUID,
    payload: RotationScheduleUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: SecretRotationService = Depends(get_rotation_service),
) -> RotationResponse:
    _require_roles(current_user, {"superadmin"})
    return RotationResponse.model_validate(
        await service.update_schedule(
            rotation_id,
            **payload.model_dump(exclude_none=True),
        )
    )


@router.post(
    "/rotations/{rotation_id}/trigger",
    response_model=RotationTriggerResponse,
    tags=["admin", "security", "rotations"],
)
async def trigger_rotation(
    rotation_id: UUID,
    payload: RotationTriggerRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: SecretRotationService = Depends(get_rotation_service),
) -> RotationTriggerResponse:
    _require_roles(current_user, {"superadmin"})
    result = await service.trigger(
        rotation_id,
        emergency=payload.emergency,
        skip_overlap=payload.skip_overlap,
        requester_id=_subject(current_user),
        approved_by=payload.approved_by,
    )
    return RotationTriggerResponse(
        rotation_id=result.id,
        status=result.rotation_state,
        next_rotation_at=result.next_rotation_at,
        overlap_ends_at=result.overlap_ends_at,
    )


@router.get(
    "/rotations/{rotation_id}/history",
    response_model=list[RotationResponse],
    tags=["admin", "security", "rotations"],
)
async def get_rotation_history(
    rotation_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: SecretRotationService = Depends(get_rotation_service),
) -> list[RotationResponse]:
    _require_roles(current_user, {"auditor", "superadmin"})
    schedule = await service._get(rotation_id)
    return [RotationResponse.model_validate(schedule)]


@router.post("/jit-grants", response_model=JitGrantResponse, tags=["admin", "security", "jit"])
async def request_jit_grant(
    payload: JitGrantRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: JitService = Depends(get_jit_service),
) -> JitGrantResponse:
    grant, policy = await service.request_grant(
        user_id=_subject(current_user),
        operation=payload.operation,
        purpose=payload.purpose,
        requested_expiry_minutes=payload.requested_expiry_minutes,
    )
    return JitGrantResponse.model_validate(grant).model_copy(
        update={
            "required_approvers": policy.required_roles,
            "min_approvers": policy.min_approvers,
            "max_expiry_minutes": policy.max_expiry_minutes,
        }
    )


@router.get("/jit-grants", response_model=list[JitGrantResponse], tags=["admin", "security", "jit"])
async def list_jit_grants(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: JitService = Depends(get_jit_service),
) -> list[JitGrantResponse]:
    return [
        JitGrantResponse.model_validate(item)
        for item in await service.list_grants(_subject(current_user))
    ]


@router.get(
    "/jit-grants/{grant_id}",
    response_model=JitGrantResponse,
    tags=["admin", "security", "jit"],
)
async def get_jit_grant(
    grant_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: JitService = Depends(get_jit_service),
) -> JitGrantResponse:
    grant = await service._get(grant_id)
    if grant.user_id != _subject(current_user):
        _require_roles(current_user, {"auditor", "superadmin", "platform_admin"})
    return JitGrantResponse.model_validate(grant)


@router.post(
    "/jit-grants/{grant_id}/approve",
    response_model=JitGrantResponse,
    tags=["admin", "security", "jit"],
)
async def approve_jit_grant(
    grant_id: UUID,
    _payload: JitApprovalRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: JitService = Depends(get_jit_service),
) -> JitGrantResponse:
    grant, token = await service.approve_grant(
        grant_id=grant_id,
        approver_id=_subject(current_user),
        approver_roles=_role_names(current_user),
    )
    return JitGrantResponse.model_validate(grant).model_copy(update={"jwt": token})


@router.post(
    "/jit-grants/{grant_id}/reject",
    response_model=JitGrantResponse,
    tags=["admin", "security", "jit"],
)
async def reject_jit_grant(
    grant_id: UUID,
    payload: JitRejectRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: JitService = Depends(get_jit_service),
) -> JitGrantResponse:
    _require_roles(current_user, {"platform_admin", "superadmin"})
    return JitGrantResponse.model_validate(
        await service.reject_grant(grant_id, reason=payload.reason)
    )


@router.post(
    "/jit-grants/{grant_id}/revoke",
    response_model=JitGrantResponse,
    tags=["admin", "security", "jit"],
)
async def revoke_jit_grant(
    grant_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: JitService = Depends(get_jit_service),
) -> JitGrantResponse:
    _require_roles(current_user, {"platform_admin", "superadmin"})
    return JitGrantResponse.model_validate(
        await service.revoke_grant(grant_id, revoked_by=_subject(current_user))
    )


@router.post(
    "/jit-grants/{grant_id}/usage",
    response_model=JitGrantResponse,
    tags=["admin", "security", "jit"],
)
async def record_jit_usage(
    grant_id: UUID,
    payload: JitUsageRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: JitService = Depends(get_jit_service),
) -> JitGrantResponse:
    del current_user
    return JitGrantResponse.model_validate(
        await service.record_usage(grant_id, **payload.model_dump())
    )


@router.get(
    "/jit-approver-policies",
    response_model=list[JitApproverPolicyResponse],
    tags=["admin", "security", "jit"],
)
async def list_jit_policies(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: JitService = Depends(get_jit_service),
) -> list[JitApproverPolicyResponse]:
    _require_roles(current_user, {"auditor", "superadmin"})
    return [
        JitApproverPolicyResponse.model_validate(item) for item in await service.list_policies()
    ]


@router.get(
    "/pentests/findings/overdue",
    response_model=list[PentestFindingResponse],
    tags=["admin", "security", "pentest"],
)
async def list_overdue_findings(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: PentestService = Depends(get_pentest_service),
) -> list[PentestFindingResponse]:
    _require_roles(current_user, {"auditor", "platform_admin", "superadmin"})
    return [PentestFindingResponse.model_validate(item) for item in await service.list_overdue()]


@router.get(
    "/pentests/export", response_model=dict[str, Any], tags=["admin", "security", "pentest"]
)
async def export_pentest_history(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: PentestService = Depends(get_pentest_service),
) -> dict[str, Any]:
    _require_roles(current_user, {"auditor", "superadmin"})
    return await service.export_history(from_, to)


@router.post("/pentests", response_model=PentestResponse, tags=["admin", "security", "pentest"])
async def schedule_pentest(
    payload: PentestScheduleRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: PentestService = Depends(get_pentest_service),
) -> PentestResponse:
    _require_roles(current_user, {"platform_admin", "superadmin"})
    return _pentest_response(await service.schedule(**payload.model_dump()))


@router.get(
    "/pentests", response_model=list[PentestResponse], tags=["admin", "security", "pentest"]
)
async def list_pentests(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: PentestService = Depends(get_pentest_service),
) -> list[PentestResponse]:
    _require_roles(current_user, {"auditor", "superadmin"})
    return [_pentest_response(item) for item in await service.list_pentests()]


@router.get(
    "/pentests/{pentest_id}", response_model=PentestResponse, tags=["admin", "security", "pentest"]
)
async def get_pentest(
    pentest_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: PentestService = Depends(get_pentest_service),
) -> PentestResponse:
    _require_roles(current_user, {"auditor", "superadmin"})
    pentest, findings = await service.get_detail(pentest_id)
    return _pentest_response(pentest, findings)


@router.post(
    "/pentests/{pentest_id}/execute",
    response_model=PentestResponse,
    tags=["admin", "security", "pentest"],
)
async def execute_pentest(
    pentest_id: UUID,
    payload: PentestExecuteRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: PentestService = Depends(get_pentest_service),
) -> PentestResponse:
    _require_roles(current_user, {"platform_admin", "superadmin"})
    return _pentest_response(await service.execute(pentest_id, **payload.model_dump()))


@router.post(
    "/pentests/{pentest_id}/findings",
    response_model=list[PentestFindingResponse],
    tags=["admin", "security", "pentest"],
)
async def import_pentest_findings(
    pentest_id: UUID,
    payload: PentestFindingsImportRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: PentestService = Depends(get_pentest_service),
) -> list[PentestFindingResponse]:
    _require_roles(current_user, {"platform_admin", "superadmin"})
    findings = await service.import_findings(
        pentest_id,
        [item.model_dump() for item in payload.findings],
    )
    return [PentestFindingResponse.model_validate(item) for item in findings]


@router.patch(
    "/pentests/{pentest_id}/findings/{finding_id}",
    response_model=PentestFindingResponse,
    tags=["admin", "security", "pentest"],
)
async def update_pentest_finding(
    pentest_id: UUID,
    finding_id: UUID,
    payload: PentestFindingUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: PentestService = Depends(get_pentest_service),
) -> PentestFindingResponse:
    del pentest_id
    _require_roles(current_user, {"platform_admin", "superadmin"})
    return PentestFindingResponse.model_validate(
        await service.update_finding(finding_id, **payload.model_dump(exclude_none=True))
    )


@router.get(
    "/compliance/frameworks",
    response_model=FrameworkListResponse,
    tags=["admin", "security", "compliance"],
)
async def list_frameworks(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ComplianceService = Depends(get_compliance_service),
) -> FrameworkListResponse:
    _require_roles(current_user, {"auditor", "compliance_officer", "superadmin"})
    return FrameworkListResponse(frameworks=await service.list_frameworks())


@router.get(
    "/compliance/frameworks/{framework}",
    response_model=FrameworkResponse,
    tags=["admin", "security", "compliance"],
)
async def get_framework(
    framework: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ComplianceService = Depends(get_compliance_service),
) -> FrameworkResponse:
    _require_roles(current_user, {"auditor", "compliance_officer", "superadmin"})
    return FrameworkResponse(
        framework=framework,
        controls=await service.list_framework_controls_with_evidence(framework),
    )


@router.post(
    "/compliance/evidence/manual",
    response_model=ManualEvidenceFormResponse,
    tags=["admin", "security", "compliance"],
)
async def upload_manual_evidence(
    control_id: UUID = Form(...),
    description: str = Form(...),
    file: UploadFile = File(...),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ComplianceService = Depends(get_compliance_service),
) -> ManualEvidenceFormResponse:
    _require_roles(current_user, {"compliance_officer", "superadmin"})
    content = await file.read()
    evidence = await service.upload_manual_evidence(
        control_id=control_id,
        description=description,
        filename=file.filename or "evidence.bin",
        content=content,
        content_type=file.content_type or "application/octet-stream",
        collected_by=_subject(current_user),
    )
    return ManualEvidenceFormResponse.model_validate(evidence)


@router.get(
    "/compliance/evidence",
    response_model=list[ComplianceEvidenceResponse],
    tags=["admin", "security", "compliance"],
)
async def list_evidence(
    control_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ComplianceService = Depends(get_compliance_service),
) -> list[ComplianceEvidenceResponse]:
    _require_roles(current_user, {"auditor", "compliance_officer", "superadmin"})
    return [
        ComplianceEvidenceResponse.model_validate(item)
        for item in await service.list_evidence(control_id)
    ]


@router.post(
    "/compliance/bundles",
    response_model=BundleExportResponse,
    tags=["admin", "security", "compliance"],
)
async def create_compliance_bundle(
    payload: BundleExportRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ComplianceService = Depends(get_compliance_service),
) -> BundleExportResponse:
    _require_roles(current_user, {"compliance_officer", "superadmin"})
    return BundleExportResponse.model_validate(
        await service.generate_bundle(**payload.model_dump())
    )


@router.get(
    "/compliance/bundles/{bundle_id}",
    response_model=BundleExportResponse,
    tags=["admin", "security", "compliance"],
)
async def get_compliance_bundle(
    bundle_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> BundleExportResponse:
    _require_roles(current_user, {"compliance_officer", "superadmin"})
    return BundleExportResponse(
        id=bundle_id,
        framework="unknown",
        url=f"s3://compliance-evidence/bundles/{bundle_id}.json",
        manifest_hash="",
        signature="",
    )
