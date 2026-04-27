from __future__ import annotations

import hashlib
from datetime import datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import AuthorizationError
from platform.incident_response.dependencies import (
    get_incident_service,
    get_integration_service,
    get_post_mortem_service,
    get_runbook_service,
)
from platform.incident_response.schemas import (
    IncidentDetailResponse,
    IncidentListItem,
    IncidentRef,
    IncidentResolveRequest,
    IncidentSeverity,
    IncidentSignal,
    IntegrationCreateRequest,
    IntegrationResponse,
    IntegrationUpdateRequest,
    LinkCertificationRequest,
    LinkExecutionRequest,
    PostMortemDistributeRequest,
    PostMortemResponse,
    PostMortemSectionUpdateRequest,
    RunbookCreateRequest,
    RunbookListItem,
    RunbookResponse,
    RunbookUpdateRequest,
)
from platform.incident_response.services.incident_service import IncidentService
from platform.incident_response.services.integration_service import IntegrationService
from platform.incident_response.services.post_mortem_service import PostMortemService
from platform.incident_response.services.runbook_service import RunbookService
from platform.incident_response.trigger_interface import get_incident_trigger
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

router = APIRouter()


def _role_names(current_user: dict[str, Any]) -> set[str]:
    roles = current_user.get("roles", [])
    return {str(item.get("role")) for item in roles if isinstance(item, dict)}


def _require_operator(current_user: dict[str, Any]) -> None:
    if {"operator", "workspace_admin", "platform_admin", "superadmin"} & _role_names(current_user):
        return
    raise AuthorizationError("PERMISSION_DENIED", "Operator role required")


def _require_admin(current_user: dict[str, Any]) -> None:
    if {"workspace_admin", "platform_admin", "superadmin"} & _role_names(current_user):
        return
    raise AuthorizationError("PERMISSION_DENIED", "Admin role required")


def _require_superadmin(current_user: dict[str, Any]) -> None:
    if "superadmin" in _role_names(current_user):
        return
    raise AuthorizationError("PERMISSION_DENIED", "Superadmin role required")


def _requester_id(current_user: dict[str, Any]) -> UUID | None:
    subject = current_user.get("sub")
    return UUID(str(subject)) if subject else None


@router.post(
    "/api/v1/internal/alerts/audit-chain-anomaly",
    response_model=IncidentRef,
    tags=["incident-response-internal-alerts"],
)
async def receive_audit_chain_anomaly_alert(payload: dict[str, Any]) -> IncidentRef:
    alerts = payload.get("alerts")
    alert = alerts[0] if isinstance(alerts, list) and alerts else payload
    labels = alert.get("labels", {}) if isinstance(alert, dict) else {}
    annotations = alert.get("annotations", {}) if isinstance(alert, dict) else {}
    sequence_or_hash = (
        labels.get("sequence_number")
        or labels.get("entry_hash")
        or annotations.get("sequence_number")
        or annotations.get("entry_hash")
        or alert.get("fingerprint")
        or "unknown"
    )
    fingerprint = hashlib.sha256(f"audit_chain_anomaly:{sequence_or_hash}".encode()).hexdigest()
    signal = IncidentSignal(
        alert_rule_class="audit_chain_anomaly",
        severity=IncidentSeverity.critical,
        title="Audit chain integrity violation",
        description=str(
            annotations.get(
                "description",
                "Audit-chain mismatch or invalid-hash logs were emitted.",
            )
        ),
        condition_fingerprint=fingerprint,
        runbook_scenario="audit-chain-anomaly",
    )
    return await get_incident_trigger().fire(signal)


@router.get(
    "/api/v1/incidents",
    response_model=list[IncidentListItem],
    tags=["incident-response-incidents"],
)
async def list_incidents(
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    cursor: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: dict[str, Any] = Depends(get_current_user),
    incident_service: IncidentService = Depends(get_incident_service),
) -> list[IncidentListItem]:
    _require_operator(current_user)
    return await incident_service.list(
        status=status,
        severity=severity,
        since=since,
        until=until,
        cursor=cursor,
        limit=limit,
    )


@router.get(
    "/api/v1/incidents/{incident_id}",
    response_model=IncidentDetailResponse,
    tags=["incident-response-incidents"],
)
async def get_incident(
    incident_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    incident_service: IncidentService = Depends(get_incident_service),
) -> IncidentDetailResponse:
    _require_operator(current_user)
    return await incident_service.get(incident_id)


@router.post(
    "/api/v1/incidents/{incident_id}/resolve",
    response_model=IncidentDetailResponse,
    tags=["incident-response-incidents"],
)
async def resolve_incident(
    incident_id: UUID,
    payload: IncidentResolveRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    incident_service: IncidentService = Depends(get_incident_service),
) -> IncidentDetailResponse:
    _require_operator(current_user)
    await incident_service.resolve(
        incident_id,
        resolved_at=payload.resolved_at,
        auto_resolved=payload.auto_resolved,
    )
    return await incident_service.get(incident_id)


@router.post(
    "/api/v1/admin/incidents/integrations",
    response_model=IntegrationResponse,
    tags=["incident-response-admin-integrations"],
)
async def create_integration(
    payload: IntegrationCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> IntegrationResponse:
    _require_superadmin(current_user)
    return await integration_service.create(
        provider=payload.provider,
        integration_key_ref=payload.integration_key_ref,
        alert_severity_mapping=payload.alert_severity_mapping,
        enabled=payload.enabled,
    )


@router.get(
    "/api/v1/admin/incidents/integrations",
    response_model=list[IntegrationResponse],
    tags=["incident-response-admin-integrations"],
)
async def list_integrations(
    current_user: dict[str, Any] = Depends(get_current_user),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> list[IntegrationResponse]:
    _require_superadmin(current_user)
    return await integration_service.list()


@router.get(
    "/api/v1/admin/incidents/integrations/{integration_id}",
    response_model=IntegrationResponse,
    tags=["incident-response-admin-integrations"],
)
async def get_integration(
    integration_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> IntegrationResponse:
    _require_superadmin(current_user)
    return await integration_service.get(integration_id)


@router.patch(
    "/api/v1/admin/incidents/integrations/{integration_id}",
    response_model=IntegrationResponse,
    tags=["incident-response-admin-integrations"],
)
async def update_integration(
    integration_id: UUID,
    payload: IntegrationUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> IntegrationResponse:
    _require_superadmin(current_user)
    return await integration_service.update(
        integration_id,
        enabled=payload.enabled,
        alert_severity_mapping=payload.alert_severity_mapping,
    )


@router.delete(
    "/api/v1/admin/incidents/integrations/{integration_id}",
    status_code=204,
    tags=["incident-response-admin-integrations"],
)
async def delete_integration(
    integration_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> Response:
    _require_superadmin(current_user)
    await integration_service.delete(integration_id)
    return Response(status_code=204)


@router.get(
    "/api/v1/runbooks",
    response_model=list[RunbookListItem],
    tags=["incident-response-runbooks"],
)
async def list_runbooks(
    status: str | None = Query(default=None),
    scenario_query: str | None = Query(default=None),
    cursor: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: dict[str, Any] = Depends(get_current_user),
    runbook_service: RunbookService = Depends(get_runbook_service),
) -> list[RunbookListItem]:
    _require_operator(current_user)
    return await runbook_service.list(
        status=status,
        scenario_query=scenario_query,
        cursor=cursor,
        limit=limit,
    )


@router.get(
    "/api/v1/runbooks/by-scenario/{scenario}",
    response_model=RunbookResponse | None,
    tags=["incident-response-runbooks"],
)
async def get_runbook_by_scenario(
    scenario: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    runbook_service: RunbookService = Depends(get_runbook_service),
) -> RunbookResponse | None:
    _require_operator(current_user)
    return await runbook_service.get_by_scenario(scenario)


@router.get(
    "/api/v1/runbooks/{runbook_id}",
    response_model=RunbookResponse,
    tags=["incident-response-runbooks"],
)
async def get_runbook(
    runbook_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    runbook_service: RunbookService = Depends(get_runbook_service),
) -> RunbookResponse:
    _require_operator(current_user)
    return await runbook_service.get(runbook_id)


@router.post(
    "/api/v1/admin/runbooks",
    response_model=RunbookResponse,
    tags=["incident-response-admin-runbooks"],
)
async def create_runbook(
    payload: RunbookCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    runbook_service: RunbookService = Depends(get_runbook_service),
) -> RunbookResponse:
    _require_admin(current_user)
    return await runbook_service.create(payload, updated_by=_requester_id(current_user))


@router.patch(
    "/api/v1/admin/runbooks/{runbook_id}",
    response_model=RunbookResponse,
    tags=["incident-response-admin-runbooks"],
)
async def update_runbook(
    runbook_id: UUID,
    payload: RunbookUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    runbook_service: RunbookService = Depends(get_runbook_service),
) -> RunbookResponse:
    _require_admin(current_user)
    return await runbook_service.update(
        runbook_id,
        payload,
        updated_by=_requester_id(current_user),
    )


@router.post(
    "/api/v1/admin/runbooks/{runbook_id}/retire",
    response_model=RunbookResponse,
    tags=["incident-response-admin-runbooks"],
)
async def retire_runbook(
    runbook_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    runbook_service: RunbookService = Depends(get_runbook_service),
) -> RunbookResponse:
    _require_admin(current_user)
    return await runbook_service.retire(runbook_id, updated_by=_requester_id(current_user))


@router.post(
    "/api/v1/incidents/{incident_id}/post-mortem",
    response_model=PostMortemResponse,
    tags=["incident-response-post-mortems"],
)
async def start_post_mortem(
    incident_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    post_mortem_service: PostMortemService = Depends(get_post_mortem_service),
) -> PostMortemResponse:
    _require_operator(current_user)
    return await post_mortem_service.start(incident_id, _requester_id(current_user))


@router.get(
    "/api/v1/incidents/{incident_id}/post-mortem",
    response_model=PostMortemResponse,
    tags=["incident-response-post-mortems"],
)
async def get_post_mortem_by_incident(
    incident_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    post_mortem_service: PostMortemService = Depends(get_post_mortem_service),
) -> PostMortemResponse:
    _require_operator(current_user)
    return await post_mortem_service.get_by_incident(incident_id)


@router.get(
    "/api/v1/post-mortems/{post_mortem_id}",
    response_model=PostMortemResponse,
    tags=["incident-response-post-mortems"],
)
async def get_post_mortem(
    post_mortem_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    post_mortem_service: PostMortemService = Depends(get_post_mortem_service),
) -> PostMortemResponse:
    _require_operator(current_user)
    return await post_mortem_service.get(post_mortem_id)


@router.patch(
    "/api/v1/post-mortems/{post_mortem_id}",
    response_model=PostMortemResponse,
    tags=["incident-response-post-mortems"],
)
async def update_post_mortem_sections(
    post_mortem_id: UUID,
    payload: PostMortemSectionUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    post_mortem_service: PostMortemService = Depends(get_post_mortem_service),
) -> PostMortemResponse:
    _require_operator(current_user)
    return await post_mortem_service.save_section(
        post_mortem_id,
        impact_assessment=payload.impact_assessment,
        root_cause=payload.root_cause,
        action_items=payload.action_items,
    )


@router.post(
    "/api/v1/post-mortems/{post_mortem_id}/blameless",
    response_model=PostMortemResponse,
    tags=["incident-response-post-mortems"],
)
async def mark_post_mortem_blameless(
    post_mortem_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    post_mortem_service: PostMortemService = Depends(get_post_mortem_service),
) -> PostMortemResponse:
    _require_operator(current_user)
    return await post_mortem_service.mark_blameless(post_mortem_id)


@router.post(
    "/api/v1/post-mortems/{post_mortem_id}/publish",
    response_model=PostMortemResponse,
    tags=["incident-response-post-mortems"],
)
async def publish_post_mortem(
    post_mortem_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    post_mortem_service: PostMortemService = Depends(get_post_mortem_service),
) -> PostMortemResponse:
    _require_admin(current_user)
    return await post_mortem_service.publish(post_mortem_id)


@router.post(
    "/api/v1/post-mortems/{post_mortem_id}/distribute",
    response_model=PostMortemResponse,
    tags=["incident-response-post-mortems"],
)
async def distribute_post_mortem(
    post_mortem_id: UUID,
    payload: PostMortemDistributeRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    post_mortem_service: PostMortemService = Depends(get_post_mortem_service),
) -> PostMortemResponse:
    _require_admin(current_user)
    return await post_mortem_service.distribute(post_mortem_id, payload.recipients)


@router.post(
    "/api/v1/post-mortems/{post_mortem_id}/links/executions",
    response_model=PostMortemResponse,
    tags=["incident-response-post-mortems"],
)
async def link_post_mortem_execution(
    post_mortem_id: UUID,
    payload: LinkExecutionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    post_mortem_service: PostMortemService = Depends(get_post_mortem_service),
) -> PostMortemResponse:
    _require_operator(current_user)
    return await post_mortem_service.link_execution(post_mortem_id, payload.execution_id)


@router.post(
    "/api/v1/post-mortems/{post_mortem_id}/links/certifications",
    response_model=PostMortemResponse,
    tags=["incident-response-post-mortems"],
)
async def link_post_mortem_certification(
    post_mortem_id: UUID,
    payload: LinkCertificationRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    post_mortem_service: PostMortemService = Depends(get_post_mortem_service),
) -> PostMortemResponse:
    _require_operator(current_user)
    return await post_mortem_service.link_certification(post_mortem_id, payload.certification_id)
