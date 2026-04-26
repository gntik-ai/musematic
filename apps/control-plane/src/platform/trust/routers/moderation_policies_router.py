from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from platform.audit.dependencies import build_audit_chain_service
from platform.common.audit_hook import audit_chain_hook
from platform.common.dependencies import get_current_user, get_db
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.trust.dependencies import get_content_moderator
from platform.trust.events import (
    ContentModerationPolicyChangedPayload,
    make_correlation,
)
from platform.trust.exceptions import ModerationPolicyNotFoundError
from platform.trust.models import ContentModerationPolicy
from platform.trust.repository import TrustRepository
from platform.trust.schemas import (
    ModerationPolicyCreateRequest,
    ModerationPolicyResponse,
    ModerationPolicyTestRequest,
    ModerationPolicyTestResponse,
    ModerationVerdict,
)
from platform.trust.services.content_moderator import ContentModerator
from platform.trust.services.moderation_action_resolver import resolve_action
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/moderation/policies", tags=["trust-content-moderation"])


@router.post("", response_model=ModerationPolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    payload: ModerationPolicyCreateRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ModerationPolicyResponse:
    _require_workspace_admin(current_user)
    workspace_id = _workspace_id(request, current_user)
    repo = TrustRepository(session)
    policy = await repo.create_moderation_policy(
        ContentModerationPolicy(
            workspace_id=workspace_id,
            created_by=_optional_uuid(current_user.get("sub")),
            **_policy_fields(payload),
        )
    )
    await _append_policy_audit(
        request,
        session,
        action="created",
        current_user=current_user,
        after=policy,
    )
    await _publish_policy_changed(request, policy, "created", current_user)
    return _policy_response(policy)


@router.get("", response_model=list[ModerationPolicyResponse])
async def list_policies(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[ModerationPolicyResponse]:
    _require_workspace_admin(current_user)
    workspace_id = _workspace_id(request, current_user)
    return [
        _policy_response(item)
        for item in await TrustRepository(session).list_moderation_policy_versions(workspace_id)
    ]


@router.get("/current", response_model=ModerationPolicyResponse)
async def get_current_policy(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ModerationPolicyResponse:
    _require_workspace_admin(current_user)
    workspace_id = _workspace_id(request, current_user)
    policy = await TrustRepository(session).get_active_moderation_policy(workspace_id)
    if policy is None:
        raise ModerationPolicyNotFoundError("active")
    return _policy_response(policy)


@router.get("/{policy_id}", response_model=ModerationPolicyResponse)
async def get_policy(
    policy_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ModerationPolicyResponse:
    _require_workspace_admin(current_user)
    policy = await _load_policy(session, policy_id)
    _assert_workspace(policy.workspace_id, _workspace_id(request, current_user))
    return _policy_response(policy)


@router.patch("/{policy_id}", response_model=ModerationPolicyResponse)
async def update_policy(
    policy_id: UUID,
    payload: ModerationPolicyCreateRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ModerationPolicyResponse:
    _require_workspace_admin(current_user)
    repo = TrustRepository(session)
    existing = await _load_policy(session, policy_id)
    _assert_workspace(existing.workspace_id, _workspace_id(request, current_user))
    before = _policy_audit_payload(existing)
    existing.active = False
    policy = await repo.create_moderation_policy(
        ContentModerationPolicy(
            workspace_id=existing.workspace_id,
            version=existing.version + 1,
            created_by=_optional_uuid(current_user.get("sub")),
            **_policy_fields(payload),
        )
    )
    await _append_policy_audit(
        request,
        session,
        action="updated",
        current_user=current_user,
        before=before,
        after=policy,
    )
    await _publish_policy_changed(request, policy, "updated", current_user)
    return _policy_response(policy)


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    _require_workspace_admin(current_user)
    policy = await _load_policy(session, policy_id)
    _assert_workspace(policy.workspace_id, _workspace_id(request, current_user))
    before = _policy_audit_payload(policy)
    await TrustRepository(session).deactivate_moderation_policy(policy_id)
    await _append_policy_audit(
        request,
        session,
        action="deactivated",
        current_user=current_user,
        before=before,
        after=policy,
    )
    await _publish_policy_changed(request, policy, "deactivated", current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{policy_id}/test", response_model=ModerationPolicyTestResponse)
async def evaluate_policy_sample(
    policy_id: UUID,
    payload: ModerationPolicyTestRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    moderator: ContentModerator = Depends(get_content_moderator),
) -> ModerationPolicyTestResponse:
    _require_workspace_admin(current_user)
    policy = await _load_policy(session, policy_id)
    _assert_workspace(policy.workspace_id, _workspace_id(request, current_user))
    provider_name = policy.language_pins.get(payload.language or "") or policy.primary_provider
    provider = moderator.providers.get(provider_name)
    scored = await provider.score(
        payload.content,
        language=payload.language,
        categories=set(policy.categories),
    )
    triggered = [
        category
        for category, score in scored.scores.items()
        if score >= float(policy.thresholds.get(category, 1.0))
    ]
    action = resolve_action(triggered, policy) if triggered else "deliver_unchanged"
    await _append_policy_audit(
        request,
        session,
        action="tested",
        current_user=current_user,
        after=policy,
        sample_hash=hashlib.sha256(payload.content.encode("utf-8")).hexdigest(),
    )
    return ModerationPolicyTestResponse(
        verdict=ModerationVerdict(
            action=action,
            content=(
                "This response was blocked by content safety policy."
                if action == "block"
                else "[REDACTED]"
                if action == "redact"
                else payload.content
            ),
            triggered_categories=triggered,
            scores=scored.scores,
            provider=scored.provider,
            policy_id=policy.id,
        ),
        persisted=False,
    )


async def _load_policy(session: AsyncSession, policy_id: UUID) -> ContentModerationPolicy:
    policy = await TrustRepository(session).get_moderation_policy(policy_id)
    if policy is None:
        raise ModerationPolicyNotFoundError(policy_id)
    return policy


def _policy_fields(payload: ModerationPolicyCreateRequest) -> dict[str, Any]:
    return {
        "categories": [str(item.value) for item in payload.categories],
        "thresholds": {
            str(getattr(key, "value", key)): float(value)
            for key, value in payload.thresholds.items()
        },
        "action_map": {
            str(getattr(key, "value", key)): str(getattr(value, "value", value))
            for key, value in payload.action_map.items()
        },
        "default_action": payload.default_action.value,
        "primary_provider": str(
            getattr(payload.primary_provider, "value", payload.primary_provider)
        ),
        "fallback_provider": (
            str(getattr(payload.fallback_provider, "value", payload.fallback_provider))
            if payload.fallback_provider is not None
            else None
        ),
        "tie_break_rule": payload.tie_break_rule.value,
        "provider_failure_action": payload.provider_failure_action.value,
        "language_pins": {
            key: str(getattr(value, "value", value)) for key, value in payload.language_pins.items()
        },
        "agent_allowlist": [
            item.model_dump(mode="json", exclude_none=True) for item in payload.agent_allowlist
        ],
        "monthly_cost_cap_eur": payload.monthly_cost_cap_eur,
        "per_call_timeout_ms": payload.per_call_timeout_ms,
        "per_execution_budget_ms": payload.per_execution_budget_ms,
    }


def _policy_response(policy: ContentModerationPolicy) -> ModerationPolicyResponse:
    return ModerationPolicyResponse.model_validate(policy)


async def _publish_policy_changed(
    request: Request,
    policy: ContentModerationPolicy,
    action: str,
    current_user: dict[str, Any],
) -> None:
    producer = request.app.state.clients.get("kafka")
    from platform.trust.events import TrustEventPublisher

    await TrustEventPublisher(producer).publish_content_moderation_policy_changed(
        ContentModerationPolicyChangedPayload(
            policy_id=policy.id,
            workspace_id=policy.workspace_id,
            action=action,
            actor_id=_optional_uuid(current_user.get("sub")),
            occurred_at=datetime.now(UTC),
        ),
        make_correlation(workspace_id=policy.workspace_id),
    )


async def _append_policy_audit(
    request: Request,
    session: AsyncSession,
    *,
    action: str,
    current_user: dict[str, Any],
    before: dict[str, Any] | None = None,
    after: ContentModerationPolicy | dict[str, Any] | None = None,
    sample_hash: str | None = None,
) -> None:
    settings = getattr(request.app.state, "settings", None)
    if settings is None or not hasattr(settings, "audit") or not callable(
        getattr(session, "execute", None)
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
        "trust.content_moderation.policy",
        {
            "action": action,
            "actor_id": str(current_user.get("sub")) if current_user.get("sub") else None,
            "before": before,
            "after": (
                _policy_audit_payload(after)
                if isinstance(after, ContentModerationPolicy)
                else after
            ),
            "sample_input_hash": sample_hash,
            "occurred_at": datetime.now(UTC),
        },
    )


def _policy_audit_payload(policy: ContentModerationPolicy | None) -> dict[str, Any] | None:
    if policy is None:
        return None
    return {
        "id": str(policy.id),
        "workspace_id": str(policy.workspace_id),
        "version": policy.version,
        "active": policy.active,
        "categories": list(policy.categories or []),
        "thresholds": dict(policy.thresholds or {}),
        "action_map": dict(policy.action_map or {}),
        "default_action": policy.default_action,
        "primary_provider": policy.primary_provider,
        "fallback_provider": policy.fallback_provider,
        "tie_break_rule": policy.tie_break_rule,
        "provider_failure_action": policy.provider_failure_action,
        "language_pins": dict(policy.language_pins or {}),
        "agent_allowlist": list(policy.agent_allowlist or []),
    }


def _workspace_id(request: Request, current_user: dict[str, Any]) -> UUID:
    raw = request.headers.get("X-Workspace-ID") or current_user.get("workspace_id")
    if raw in {None, ""}:
        raise ValidationError("WORKSPACE_REQUIRED", "Workspace context is required")
    return UUID(str(raw))


def _role_names(current_user: dict[str, Any]) -> set[str]:
    return {
        str(item.get("role"))
        for item in current_user.get("roles", [])
        if isinstance(item, dict) and item.get("role") is not None
    }


def _require_workspace_admin(current_user: dict[str, Any]) -> None:
    if _role_names(current_user) & {"workspace_admin", "platform_admin", "superadmin"}:
        return
    raise AuthorizationError("PERMISSION_DENIED", "Workspace admin role required")


def _assert_workspace(actual: UUID, expected: UUID) -> None:
    if actual != expected:
        raise AuthorizationError("PERMISSION_DENIED", "Cannot access another workspace policy")


def _optional_uuid(value: object) -> UUID | None:
    if value in {None, ""}:
        return None
    return UUID(str(value))
