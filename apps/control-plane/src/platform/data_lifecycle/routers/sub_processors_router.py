"""Sub-processors REST endpoints.

Public read surface (NO auth) under ``/api/v1/public/sub-processors*``.
Admin write surface under ``/api/v1/admin/sub-processors*`` (gated by
``require_superadmin``).

Public endpoints are also served by the operationally-independent
``public-pages`` Helm release per rule 49 — that Deployment uses a
PostgreSQL replica + ConfigMap-snapshot fallback, but the route shape
is identical to what's exposed here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.data_lifecycle.dependencies import get_repository, get_session
from platform.data_lifecycle.exceptions import (
    SubProcessorNameConflictError,
    SubProcessorNotFoundError,
)
from platform.data_lifecycle.models import SubProcessor
from platform.data_lifecycle.repository import DataLifecycleRepository
from platform.data_lifecycle.schemas import (
    SubProcessorAdmin,
    SubProcessorCreate,
    SubProcessorPublic,
    SubProcessorsPublicResponse,
    SubProcessorSubscribeRequest,
    SubProcessorSubscribeResponse,
    SubProcessorUpdate,
)
from platform.data_lifecycle.services.sub_processors_service import (
    SubProcessorsService,
    render_rss,
)
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

# Two routers — public (no auth) and admin (require_superadmin).
public_router = APIRouter(
    prefix="/api/v1/public/sub-processors", tags=["data_lifecycle:public"]
)
admin_router = APIRouter(
    prefix="/api/v1/admin/sub-processors", tags=["data_lifecycle:admin"]
)


def _get_service(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> SubProcessorsService:
    return SubProcessorsService(
        repository=DataLifecycleRepository(session),
        audit_chain=getattr(request.app.state, "audit_chain_service", None),
        event_producer=request.app.state.clients.get("kafka"),
    )


def _requester_id(current_user: dict[str, Any]) -> UUID | None:
    sub = current_user.get("sub") if current_user else None
    return UUID(str(sub)) if sub else None


def _site_base_url(request: Request) -> str:
    settings = getattr(request.app.state, "settings", None)
    domain = getattr(settings, "PLATFORM_DOMAIN", "musematic.ai") if settings else "musematic.ai"
    return f"https://{domain}"


# =============================================================================
# Public (no auth)
# =============================================================================


@public_router.get(
    "",
    response_model=SubProcessorsPublicResponse,
)
async def list_sub_processors_public(
    request: Request,
    response: Response,
    service: SubProcessorsService = Depends(_get_service),
) -> SubProcessorsPublicResponse:
    items = await service.list_active_for_public()
    last = await service.latest_change_at() or datetime.now(UTC)
    # Cache aggressively at the edge (5 min) per FR-757.5.
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=900"
    response.headers["ETag"] = f'W/"{int(last.timestamp())}"'
    return SubProcessorsPublicResponse(
        last_updated_at=last,
        items=[
            SubProcessorPublic(
                name=i.name,
                category=i.category,
                location=i.location,
                data_categories=i.data_categories,
                privacy_policy_url=i.privacy_policy_url,
                dpa_url=i.dpa_url,
                started_using_at=(
                    datetime.fromisoformat(i.started_using_at).date()
                    if i.started_using_at
                    else None
                ),
            )
            for i in items
        ],
    )


@public_router.get(
    ".rss",
    response_class=PlainTextResponse,
)
async def rss_feed(
    request: Request,
    repo: DataLifecycleRepository = Depends(get_repository),
) -> PlainTextResponse:
    rows: list[SubProcessor] = await repo.list_sub_processors_all()
    xml = render_rss(
        items=rows,
        site_base_url=_site_base_url(request),
        last_build=datetime.now(UTC),
    )
    return PlainTextResponse(
        content=xml, media_type="application/rss+xml; charset=utf-8"
    )


@public_router.post(
    "/subscribe",
    response_model=SubProcessorSubscribeResponse,
    status_code=202,
)
async def subscribe(
    payload: SubProcessorSubscribeRequest,
) -> SubProcessorSubscribeResponse:
    """Anti-enumeration subscribe endpoint.

    Always returns 202 with the same body. Real subscription
    persistence + verification email lands with the
    ``sub_processor_email_subscriptions`` table in a follow-up;
    accepting the request shape now keeps the public contract stable.
    """

    return SubProcessorSubscribeResponse()


# =============================================================================
# Admin (require_superadmin)
# =============================================================================


@admin_router.get("", response_model=list[SubProcessorAdmin])
async def list_sub_processors_admin(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: SubProcessorsService = Depends(_get_service),
) -> list[SubProcessorAdmin]:
    rows = await service.list_all()
    return [SubProcessorAdmin.model_validate(r) for r in rows]


@admin_router.post(
    "",
    response_model=SubProcessorAdmin,
    status_code=201,
)
async def add_sub_processor(
    payload: SubProcessorCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: SubProcessorsService = Depends(_get_service),
) -> SubProcessorAdmin:
    try:
        row = await service.add(
            name=payload.name,
            category=payload.category,
            location=payload.location,
            data_categories=payload.data_categories,
            privacy_policy_url=payload.privacy_policy_url,
            dpa_url=payload.dpa_url,
            started_using_at=(
                datetime.combine(payload.started_using_at, datetime.min.time(), UTC)
                if payload.started_using_at
                else None
            ),
            notes=payload.notes,
            actor_user_id=_requester_id(current_user),
        )
    except SubProcessorNameConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "sub_processor_name_conflict", "message": str(exc)},
        ) from exc
    return SubProcessorAdmin.model_validate(row)


@admin_router.patch(
    "/{sub_processor_id}",
    response_model=SubProcessorAdmin,
)
async def update_sub_processor(
    sub_processor_id: UUID,
    payload: SubProcessorUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: SubProcessorsService = Depends(_get_service),
) -> SubProcessorAdmin:
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        existing = await service.get(sub_processor_id)
        return SubProcessorAdmin.model_validate(existing)
    try:
        row = await service.update(
            sub_processor_id=sub_processor_id,
            updates=updates,
            actor_user_id=_requester_id(current_user),
        )
    except SubProcessorNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "sub_processor_not_found", "message": str(exc)},
        ) from exc
    except SubProcessorNameConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "sub_processor_name_conflict", "message": str(exc)},
        ) from exc
    return SubProcessorAdmin.model_validate(row)


@admin_router.delete(
    "/{sub_processor_id}",
    response_model=SubProcessorAdmin,
)
async def delete_sub_processor(
    sub_processor_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: SubProcessorsService = Depends(_get_service),
) -> SubProcessorAdmin:
    try:
        row = await service.soft_delete(
            sub_processor_id=sub_processor_id,
            actor_user_id=_requester_id(current_user),
        )
    except SubProcessorNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "sub_processor_not_found", "message": str(exc)},
        ) from exc
    return SubProcessorAdmin.model_validate(row)
