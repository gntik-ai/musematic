from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from platform.auth.password import hash_password
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user, get_db
from platform.common.exceptions import AuthorizationError, NotFoundError
from platform.common.logging import get_logger
from platform.common.tenant_context import current_tenant
from platform.incident_response.dependencies import get_incident_service
from platform.incident_response.schemas import IncidentRef, IncidentSeverity, IncidentSignal
from platform.incident_response.services.incident_service import IncidentService
from platform.status_page.dependencies import get_status_page_service
from platform.status_page.schemas import SourceKind
from platform.status_page.service import StatusPageService
from platform.tenants.seeder import DEFAULT_TENANT_ID
from platform.testing.schemas_e2e import (
    ChaosKillPodRequest,
    ChaosKillPodResponse,
    ChaosPartitionRequest,
    ChaosPartitionResponse,
    E2EUserProvisionRequest,
    E2EUserProvisionResponse,
    KafkaEventsResponse,
    MockLLMCallsResponse,
    MockLLMClearRequest,
    MockLLMRateLimitRequest,
    MockLLMRateLimitResponse,
    MockLLMSetRequest,
    MockLLMSetResponse,
    ResetRequest,
    ResetResponse,
    SeedRequest,
    SeedResponse,
    SyntheticFailureInjectRequest,
    SyntheticFailureInjectResponse,
)
from platform.testing.service_e2e import (
    ChaosService,
    KafkaObserver,
    ResetService,
    SeedService,
    build_mock_llm_service,
)
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/_e2e", tags=["_e2e"])
LOGGER = get_logger(__name__)


class E2ESignupModeRequest(BaseModel):
    signup_mode: Literal["open", "invite_only", "admin_approval"]


class E2EExpiredVerificationTokenRequest(BaseModel):
    email: str


class E2EIncidentTriggerRequest(BaseModel):
    scenario: str = "status_page"
    severity: IncidentSeverity = IncidentSeverity.critical
    title: str | None = None
    description: str | None = None


class E2EIncidentResolveRequest(BaseModel):
    incident_id: UUID
    resolved_at: datetime | None = None
    auto_resolved: bool = False


def _role_names(current_user: dict[str, Any]) -> set[str]:
    roles = current_user.get("roles", [])
    return {
        str(item.get("role"))
        for item in roles
        if isinstance(item, dict) and item.get("role") is not None
    }


def _scopes(current_user: dict[str, Any]) -> set[str]:
    scopes = current_user.get("scopes", [])
    if isinstance(scopes, str):
        return {item for item in scopes.split() if item}
    if isinstance(scopes, list):
        return {str(item) for item in scopes}
    return set()


def require_admin_or_e2e_scope(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    role_names = _role_names(current_user)
    if {"platform_admin", "superadmin"} & role_names:
        return current_user
    if "e2e" in _scopes(current_user):
        return current_user
    raise AuthorizationError(
        "PERMISSION_DENIED",
        "Admin role or e2e scope required",
    )


def require_operator_or_e2e_scope(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    role_names = _role_names(current_user)
    if {"operator", "workspace_admin", "platform_admin", "superadmin"} & role_names:
        return current_user
    if "e2e" in _scopes(current_user):
        return current_user
    raise AuthorizationError(
        "PERMISSION_DENIED",
        "Operator role or e2e scope required",
    )


def _settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _redis(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


def _current_tenant_id() -> UUID:
    tenant = current_tenant.get(None)
    return tenant.id if tenant is not None else DEFAULT_TENANT_ID


async def _bind_rls_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


@router.put("/accounts/signup-mode")
async def set_account_signup_mode(
    payload: E2ESignupModeRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> dict[str, str]:
    del current_user
    settings = _settings(request)
    previous = str(settings.accounts.signup_mode)
    settings.accounts.signup_mode = payload.signup_mode
    return {"previous": previous, "current": str(settings.accounts.signup_mode)}


@router.delete("/accounts/signup-rate-limits", status_code=status.HTTP_204_NO_CONTENT)
async def clear_account_signup_rate_limits(
    request: Request,
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> Response:
    del current_user
    client = await _redis(request)._get_client()
    keys: list[Any] = []
    async for key in client.scan_iter(match="accounts:signup:*", count=100):
        keys.append(key)
    if keys:
        await client.delete(*keys)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/accounts/verification-token")
async def get_account_verification_token(
    request: Request,
    email: str = Query(...),
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> dict[str, str | None]:
    del current_user
    client = await _redis(request)._get_client()
    raw = await client.get(f"e2e:accounts:verification-token:{email.lower()}")
    token = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    return {"email": email.lower(), "token": token}


@router.get("/status-subscriptions/tokens")
async def get_status_subscription_tokens(
    request: Request,
    email: str = Query(...),
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> dict[str, str | None]:
    del current_user
    normalized = email.strip().lower()
    client = await _redis(request)._get_client()
    raw = await client.get(f"e2e:status-subscriptions:tokens:{normalized}")
    if raw is None:
        return {
            "email": normalized,
            "confirmation_token": None,
            "unsubscribe_token": None,
        }
    value = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    payload = json.loads(value)
    return {
        "email": normalized,
        "confirmation_token": payload.get("confirmation_token"),
        "unsubscribe_token": payload.get("unsubscribe_token"),
    }


@router.get("/status-subscriptions/dispatches")
async def get_status_subscription_dispatches(
    email: str = Query(...),
    event_kind: str = Query("incident.created"),
    outcome: str = Query("sent"),
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str | int]:
    del current_user
    normalized = email.strip().lower()
    count = (
        await session.execute(
            text(
                """
                SELECT count(*)
                  FROM subscription_dispatches dispatch
                  JOIN status_subscriptions subscription
                    ON subscription.id = dispatch.subscription_id
                 WHERE subscription.target = :email
                   AND dispatch.event_kind = :event_kind
                   AND dispatch.outcome = :outcome
                """
            ),
            {
                "email": normalized,
                "event_kind": event_kind,
                "outcome": outcome,
            },
        )
    ).scalar_one()
    return {
        "email": normalized,
        "event_kind": event_kind,
        "outcome": outcome,
        "count": int(count or 0),
    }


@router.post("/accounts/expired-verification-token")
async def create_expired_account_verification_token(
    payload: E2EExpiredVerificationTokenRequest,
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    del current_user
    email = payload.email.strip().lower()
    tenant_id = _current_tenant_id()
    await _bind_rls_tenant(session, tenant_id)
    user_id = (
        await session.execute(
            text("SELECT id FROM accounts_users WHERE email = :email LIMIT 1"),
            {"email": email},
        )
    ).scalar_one_or_none()
    if user_id is None:
        raise NotFoundError("USER_NOT_FOUND", "User not found")
    token = secrets.token_urlsafe(32)
    await session.execute(
        text(
            """
            INSERT INTO accounts_email_verifications (
                user_id,
                token_hash,
                expires_at,
                tenant_id
            )
            VALUES (:user_id, :token_hash, now() - interval '1 second', :tenant_id)
            """
        ),
        {
            "user_id": str(user_id),
            "token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "tenant_id": str(tenant_id),
        },
    )
    return {"email": email, "token": token}


@router.post("/seed", response_model=SeedResponse)
async def seed(
    payload: SeedRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> SeedResponse:
    del request, current_user
    return await SeedService().seed(payload.scope)


@router.post("/reset", response_model=ResetResponse)
async def reset(
    payload: ResetRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> ResetResponse:
    del request, current_user
    return await ResetService().reset(
        payload.scope,
        include_baseline=payload.include_baseline,
    )


@router.post("/users", response_model=E2EUserProvisionResponse)
async def provision_user(
    payload: E2EUserProvisionRequest,
    session: AsyncSession = Depends(get_db),
) -> E2EUserProvisionResponse:
    display_name = payload.display_name or payload.email.split("@", 1)[0]
    tenant_id = _current_tenant_id()
    await _bind_rls_tenant(session, tenant_id)
    await session.execute(
        text(
            """
            INSERT INTO users (id, email, display_name, status, tenant_id)
            VALUES (:id, :email, :display_name, :status, :tenant_id)
            ON CONFLICT (id) DO UPDATE SET
                email = EXCLUDED.email,
                display_name = EXCLUDED.display_name,
                status = EXCLUDED.status,
                tenant_id = EXCLUDED.tenant_id,
                updated_at = now()
            """
        ),
        {
            "id": str(payload.id),
            "email": payload.email,
            "display_name": display_name,
            "status": payload.status,
            "tenant_id": str(tenant_id),
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO accounts_users (id, email, display_name, status, signup_source, tenant_id)
            VALUES (:id, :email, :display_name, :status, 'self_registration', :tenant_id)
            ON CONFLICT (email) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                status = EXCLUDED.status,
                tenant_id = EXCLUDED.tenant_id,
                updated_at = now()
            """
        ),
        {
            "id": str(payload.id),
            "email": payload.email,
            "display_name": display_name,
            "status": payload.status,
            "tenant_id": str(tenant_id),
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO user_credentials (user_id, email, password_hash, is_active, tenant_id)
            VALUES (:id, :email, :password_hash, true, :tenant_id)
            ON CONFLICT (user_id) DO UPDATE SET
                email = EXCLUDED.email,
                password_hash = EXCLUDED.password_hash,
                is_active = true,
                tenant_id = EXCLUDED.tenant_id,
                updated_at = now()
            """
        ),
        {
            "id": str(payload.id),
            "email": payload.email,
            "password_hash": hash_password(payload.password),
            "tenant_id": str(tenant_id),
        },
    )
    if payload.status == "pending_approval":
        await session.execute(
            text(
                """
                INSERT INTO accounts_approval_requests (user_id, requested_at, tenant_id)
                VALUES (:id, now(), :tenant_id)
                ON CONFLICT (user_id) DO NOTHING
                """
            ),
            {"id": str(payload.id), "tenant_id": str(tenant_id)},
        )
    for role in payload.roles:
        await session.execute(
            text(
                """
                INSERT INTO user_roles (user_id, role, workspace_id, tenant_id)
                SELECT
                    CAST(:id AS uuid),
                    CAST(:role AS varchar),
                    CAST(NULL AS uuid),
                    CAST(:tenant_id AS uuid)
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM user_roles
                    WHERE user_id = CAST(:id AS uuid)
                      AND role = CAST(:role AS varchar)
                      AND workspace_id IS NULL
                )
                """
            ),
            {"id": str(payload.id), "role": role, "tenant_id": str(tenant_id)},
        )
    return E2EUserProvisionResponse(id=payload.id, email=payload.email, status=payload.status)


@router.post("/incidents/seed/{scenario}", response_model=IncidentRef)
async def seed_incident(
    scenario: str,
    current_user: dict[str, Any] = Depends(require_operator_or_e2e_scope),
    incident_service: IncidentService = Depends(get_incident_service),
) -> IncidentRef:
    del current_user
    normalized = scenario.replace("-", "_")
    fingerprint = hashlib.sha256(f"e2e:{normalized}:{uuid4()}".encode()).hexdigest()
    signal = IncidentSignal(
        alert_rule_class=f"e2e_{normalized}",
        severity=IncidentSeverity.critical,
        title=f"E2E {normalized.replace('_', ' ').title()} Incident",
        description=(
            "Synthetic E2E incident generated by /api/v1/_e2e/incidents/seed "
            "for local smoke testing."
        ),
        condition_fingerprint=fingerprint,
        runbook_scenario=normalized,
    )
    return await incident_service.create_from_signal(signal)


@router.post("/incidents/trigger", response_model=IncidentRef)
async def trigger_incident(
    payload: E2EIncidentTriggerRequest,
    current_user: dict[str, Any] = Depends(require_operator_or_e2e_scope),
    incident_service: IncidentService = Depends(get_incident_service),
    status_page_service: StatusPageService = Depends(get_status_page_service),
) -> IncidentRef:
    del current_user
    normalized = payload.scenario.replace("-", "_")
    fingerprint = hashlib.sha256(f"e2e:trigger:{normalized}:{uuid4()}".encode()).hexdigest()
    signal = IncidentSignal(
        alert_rule_class=f"e2e_{normalized}",
        severity=payload.severity,
        title=payload.title or f"E2E {normalized.replace('_', ' ').title()} Incident",
        description=payload.description
        or "Synthetic E2E incident generated by /api/v1/_e2e/incidents/trigger.",
        condition_fingerprint=fingerprint,
        runbook_scenario=normalized,
    )
    incident = await incident_service.create_from_signal(signal)
    await _refresh_status_projection(
        status_page_service,
        event_kind="incident.created",
        payload={
            "incident_id": str(incident.incident_id),
            "title": signal.title,
            "severity": signal.severity.value,
            "components_affected": _status_components_for_scenario(normalized, signal.title),
        },
    )
    return incident


@router.post("/incidents/resolve", response_model=IncidentRef)
async def resolve_incident(
    payload: E2EIncidentResolveRequest,
    current_user: dict[str, Any] = Depends(require_operator_or_e2e_scope),
    incident_service: IncidentService = Depends(get_incident_service),
    status_page_service: StatusPageService = Depends(get_status_page_service),
) -> IncidentRef:
    del current_user
    incident = await incident_service.resolve(
        payload.incident_id,
        resolved_at=payload.resolved_at,
        auto_resolved=payload.auto_resolved,
    )
    await _refresh_status_projection(
        status_page_service,
        event_kind="incident.resolved",
        payload={
            "incident_id": str(incident.id),
            "title": incident.title,
            "severity": incident.severity.value,
            "components_affected": _status_components_for_scenario(
                incident.runbook_scenario or "",
                incident.title,
            ),
        },
    )
    return IncidentRef(incident_id=incident.id)


async def _refresh_status_projection(
    status_page_service: StatusPageService,
    *,
    event_kind: str,
    payload: dict[str, Any],
) -> None:
    await status_page_service.compose_current_snapshot(source_kind=SourceKind.kafka)
    await status_page_service.dispatch_event(event_kind, payload)


def _status_components_for_scenario(scenario: str, title: str) -> list[str]:
    lowered = f"{scenario} {title}".lower()
    components: list[str] = []
    if "status" in lowered or "control" in lowered or "api" in lowered:
        components.append("control-plane-api")
    if "reasoning" in lowered:
        components.append("reasoning-engine")
    if "workflow" in lowered or "execution" in lowered:
        components.append("workflow-engine")
    return components


@router.post("/chaos/kill-pod", response_model=ChaosKillPodResponse)
async def kill_pod(
    payload: ChaosKillPodRequest,
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> ChaosKillPodResponse:
    del current_user
    return await ChaosService().kill_pod(
        payload.namespace,
        payload.label_selector,
        payload.count,
    )


@router.post("/chaos/partition-network", response_model=ChaosPartitionResponse)
async def partition_network(
    payload: ChaosPartitionRequest,
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> ChaosPartitionResponse:
    del current_user
    return await ChaosService().partition_network(
        payload.from_namespace,
        payload.to_namespace,
        payload.ttl_seconds,
    )


@router.post("/mock-llm/set-response", response_model=MockLLMSetResponse)
async def set_mock_llm_response(
    payload: MockLLMSetRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> MockLLMSetResponse:
    del current_user
    service = build_mock_llm_service(_redis(request))
    queue_depth = await service.set_response(
        payload.prompt_pattern,
        payload.response,
        payload.streaming_chunks,
    )
    return MockLLMSetResponse(queue_depth=queue_depth)


@router.post("/mock-llm/rate-limit", response_model=MockLLMRateLimitResponse)
async def set_mock_llm_rate_limit(
    payload: MockLLMRateLimitRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> MockLLMRateLimitResponse:
    del current_user
    service = build_mock_llm_service(_redis(request))
    await service.set_rate_limit_error(payload.prompt_pattern, payload.count)
    return MockLLMRateLimitResponse(
        prompt_pattern=payload.prompt_pattern,
        remaining=payload.count,
    )


@router.get("/mock-llm/calls", response_model=MockLLMCallsResponse)
async def get_mock_llm_calls(
    request: Request,
    pattern: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> MockLLMCallsResponse:
    del current_user
    service = build_mock_llm_service(_redis(request))
    records = await service.get_calls(
        pattern=pattern,
        since=since.isoformat() if since else None,
    )
    return MockLLMCallsResponse(calls=records)


@router.post("/mock-llm/clear", status_code=204)
async def clear_mock_llm(
    payload: MockLLMClearRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> None:
    del current_user
    service = build_mock_llm_service(_redis(request))
    await service.clear_queue(payload.prompt_pattern)


@router.post("/inject-failure", response_model=SyntheticFailureInjectResponse)
async def inject_failure(
    payload: SyntheticFailureInjectRequest,
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> SyntheticFailureInjectResponse:
    del current_user
    LOGGER.error(
        payload.error_message,
        service=payload.service,
        bounded_context="synthetic_e2e",
        correlation_id=payload.correlation_id,
        trace_id=payload.trace_id,
        event_type="e2e.synthetic_failure.injected",
    )
    return SyntheticFailureInjectResponse(
        correlation_id=payload.correlation_id,
        service=payload.service,
        trace_id=payload.trace_id,
    )


@router.get("/kafka/events", response_model=KafkaEventsResponse)
async def kafka_events(
    request: Request,
    topic: str = Query(...),
    since: datetime = Query(...),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    key: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> KafkaEventsResponse:
    del current_user
    observer = KafkaObserver(_settings(request))
    resolved_until = until or datetime.now(UTC)
    return await observer.get_events(
        topic=topic,
        since=since,
        until=resolved_until,
        limit=limit,
        key=key,
    )
