"""Admin security surface (UPD-050).

Mounts under the existing ``/api/v1/admin/*`` composite router. Endpoints
defined here serve the super-admin tuning + suspension-review surface
per ``specs/100-abuse-prevention/contracts/admin-security-rest.md``.

Route handlers are wired in UPD-050 Phases 4 to 8 (T032 / T037 / T060).
This module implements the suspension queue + email-override CRUD here;
the geo-policy and the abuse-prevention settings GET/PATCH endpoints
are stubbed in below for the foundational scaffold.
"""

from __future__ import annotations

from platform.admin.rbac import require_superadmin
from platform.audit.dependencies import build_audit_chain_service
from platform.common import database
from platform.common.exceptions import NotFoundError
from platform.notifications.dependencies import build_notifications_service
from platform.security.abuse_prevention.exceptions import SettingKeyUnknownError
from platform.security.abuse_prevention.models import (
    DisposableEmailOverride,
    TrustedSourceAllowlistEntry,
)
from platform.security.abuse_prevention.schemas import (
    AbusePreventionSettingValue,
    EmailOverrideAdd,
    GeoPolicyUpdate,
    GeoPolicyView,
    SuspensionCreateRequest,
    SuspensionDetailView,
    SuspensionLiftRequest,
    SuspensionView,
    TrustedAllowlistAdd,
)
from platform.security.abuse_prevention.settings_service import (
    AbusePreventionSettingsService,
)
from platform.security.abuse_prevention.suspension import SuspensionService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/security", tags=["admin.security"])


def _actor_id(current_user: dict[str, Any]) -> UUID:
    raw = current_user.get("user_id") or current_user.get("id") or current_user.get("sub")
    if raw is None:
        raise RuntimeError("require_superadmin returned a user without an id")
    return UUID(str(raw))


def _event_producer(request: Request) -> Any:
    return getattr(request.app.state, "event_producer", None)


def _alert_service(request: Request) -> Any:
    return getattr(request.app.state, "alert_service", None)


def _settings_service(
    request: Request, session: AsyncSession
) -> AbusePreventionSettingsService:
    return AbusePreventionSettingsService(
        session=session,
        audit_chain=build_audit_chain_service(
            session=session,
            settings=request.app.state.settings,
            producer=_event_producer(request),
        ),
        event_producer=_event_producer(request),
    )


def _suspension_service(
    request: Request, session: AsyncSession
) -> SuspensionService:
    alert_service = _alert_service(request)
    redis_client = getattr(request.app.state, "redis_client", None)
    if alert_service is None and redis_client is not None:
        # Build a notifications service lazily so the dependency is
        # injectable in tests but still wired in production.
        alert_service = build_notifications_service(
            session=session,
            settings=request.app.state.settings,
            redis_client=redis_client,
            producer=_event_producer(request),
            workspaces_service=None,
        )
    return SuspensionService(
        session=session,
        audit_chain=build_audit_chain_service(
            session=session,
            settings=request.app.state.settings,
            producer=_event_producer(request),
        ),
        event_producer=_event_producer(request),
        alert_service=alert_service,
    )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@router.get("/abuse-prevention/settings")
async def get_settings(
    request: Request,
    _current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> dict[str, Any]:
    return await _settings_service(request, session).get_all()


@router.patch("/abuse-prevention/settings/{setting_key}")
async def patch_setting(
    setting_key: str,
    payload: AbusePreventionSettingValue,
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> dict[str, str]:
    try:
        await _settings_service(request, session).set(
            _actor_id(current_user), setting_key, payload.value
        )
    except SettingKeyUnknownError:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "setting_value_invalid", "message": str(exc)}
        ) from exc
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Suspensions
# ---------------------------------------------------------------------------


@router.get("/suspensions")
async def list_suspensions(
    request: Request,
    status: str = Query(default="active"),
    limit: int = Query(default=50, ge=1, le=200),
    _current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> dict[str, list[SuspensionView]]:
    service = _suspension_service(request, session)
    rows = await service.list_active(status=status, limit=limit)
    return {
        "items": [
            SuspensionView(
                id=row.id,
                user_id=row.user_id,
                tenant_id=row.tenant_id,
                reason=row.reason,
                suspended_at=row.suspended_at,
                suspended_by=row.suspended_by,
                suspended_by_user_id=row.suspended_by_user_id,
                lifted_at=row.lifted_at,
                lifted_by_user_id=row.lifted_by_user_id,
            )
            for row in rows
        ]
    }


@router.get("/suspensions/{suspension_id}", response_model=SuspensionDetailView)
async def get_suspension(
    suspension_id: UUID,
    request: Request,
    _current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> SuspensionDetailView:
    from platform.security.abuse_prevention.models import AccountSuspension

    result = await session.execute(
        select(AccountSuspension).where(AccountSuspension.id == suspension_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise NotFoundError("suspension_not_found", "Suspension not found.")
    return SuspensionDetailView(
        id=row.id,
        user_id=row.user_id,
        tenant_id=row.tenant_id,
        reason=row.reason,
        suspended_at=row.suspended_at,
        suspended_by=row.suspended_by,
        suspended_by_user_id=row.suspended_by_user_id,
        lifted_at=row.lifted_at,
        lifted_by_user_id=row.lifted_by_user_id,
        evidence_json=row.evidence_json,
        lift_reason=row.lift_reason,
    )


@router.post("/suspensions/{suspension_id}/lift")
async def lift_suspension(
    suspension_id: UUID,
    payload: SuspensionLiftRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> dict[str, str]:
    await _suspension_service(request, session).lift(
        suspension_id=suspension_id,
        actor_user_id=_actor_id(current_user),
        reason=payload.reason,
    )
    return {"status": "lifted"}


@router.post("/suspensions", status_code=201)
async def manual_create_suspension(
    payload: SuspensionCreateRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> dict[str, str]:
    # Resolve the user's tenant_id from the existing accounts surface;
    # for the manual-create path we accept it as part of the
    # super-admin's session context (default tenant for UPD-050).
    tenant_id = current_user.get("tenant_id") or _DEFAULT_TENANT_UUID
    actor_id = _actor_id(current_user)
    row = await _suspension_service(request, session).suspend(
        user_id=payload.user_id,
        tenant_id=UUID(str(tenant_id)),
        reason=payload.reason,
        evidence={"notes": payload.notes, **payload.evidence},
        suspended_by="super_admin",
        suspended_by_user_id=actor_id,
    )
    return {"status": "suspended", "suspension_id": str(row.id)}


_DEFAULT_TENANT_UUID = UUID("00000000-0000-0000-0000-000000000001")


# ---------------------------------------------------------------------------
# Disposable-email overrides
# ---------------------------------------------------------------------------


@router.get("/email-overrides")
async def list_email_overrides(
    _current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> dict[str, list[dict[str, Any]]]:
    result = await session.execute(select(DisposableEmailOverride))
    return {
        "items": [
            {
                "domain": row.domain,
                "created_at": row.created_at.isoformat(),
                "created_by_user_id": str(row.created_by_user_id),
                "reason": row.reason,
            }
            for row in result.scalars()
        ]
    }


@router.post("/email-overrides", status_code=201)
async def add_email_override(
    payload: EmailOverrideAdd,
    current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> dict[str, str]:
    actor_id = _actor_id(current_user)
    existing = await session.execute(
        select(DisposableEmailOverride).where(
            DisposableEmailOverride.domain == payload.domain
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "email_override_already_exists",
                "domain": payload.domain,
            },
        )
    session.add(
        DisposableEmailOverride(
            domain=payload.domain,
            created_by_user_id=actor_id,
            reason=payload.reason,
        )
    )
    await session.commit()
    return {"status": "added", "domain": payload.domain}


@router.delete("/email-overrides/{domain}")
async def remove_email_override(
    domain: str,
    _current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> dict[str, str]:
    await session.execute(
        delete(DisposableEmailOverride).where(
            DisposableEmailOverride.domain == domain.strip().lower()
        )
    )
    await session.commit()
    return {"status": "removed", "domain": domain}


# ---------------------------------------------------------------------------
# Trusted allowlist
# ---------------------------------------------------------------------------


@router.get("/trusted-allowlist")
async def list_trusted_allowlist(
    _current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> dict[str, list[dict[str, Any]]]:
    result = await session.execute(select(TrustedSourceAllowlistEntry))
    return {
        "items": [
            {
                "id": str(row.id),
                "kind": row.kind,
                "value": row.value,
                "created_at": row.created_at.isoformat(),
                "reason": row.reason,
            }
            for row in result.scalars()
        ]
    }


@router.post("/trusted-allowlist", status_code=201)
async def add_trusted_allowlist(
    payload: TrustedAllowlistAdd,
    current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> dict[str, str]:
    actor_id = _actor_id(current_user)
    session.add(
        TrustedSourceAllowlistEntry(
            kind=payload.kind,
            value=payload.value,
            created_by_user_id=actor_id,
            reason=payload.reason,
        )
    )
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "trusted_allowlist_already_exists",
                "kind": payload.kind,
                "value": payload.value,
            },
        ) from exc
    return {"status": "added"}


@router.delete("/trusted-allowlist/{entry_id}")
async def remove_trusted_allowlist(
    entry_id: UUID,
    _current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> dict[str, str]:
    await session.execute(
        delete(TrustedSourceAllowlistEntry).where(
            TrustedSourceAllowlistEntry.id == entry_id
        )
    )
    await session.commit()
    return {"status": "removed"}


# ---------------------------------------------------------------------------
# Geo policy
# ---------------------------------------------------------------------------


@router.get("/geo-policy", response_model=GeoPolicyView)
async def get_geo_policy(
    request: Request,
    _current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> GeoPolicyView:
    settings = _settings_service(request, session)
    mode = await settings.get("geo_block_mode") or "disabled"
    codes = await settings.get("geo_block_country_codes") or []
    return GeoPolicyView(mode=str(mode), country_codes=list(codes))


@router.patch("/geo-policy")
async def update_geo_policy(
    payload: GeoPolicyUpdate,
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> dict[str, str]:
    settings = _settings_service(request, session)
    actor = _actor_id(current_user)
    await settings.set(actor, "geo_block_mode", payload.mode)
    await settings.set(actor, "geo_block_country_codes", payload.country_codes)
    return {"status": "ok"}
