"""Status page public router for FR-675-FR-682.

See specs/095-public-status-banner-workbench-uis/plan.md for the implementation plan.
"""

from __future__ import annotations

from datetime import datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import AuthorizationError
from platform.status_page.dependencies import (
    enforce_subscribe_rate_limit,
    get_status_page_service,
)
from platform.status_page.feed_builders import build_atom, build_rss
from platform.status_page.schemas import (
    AntiEnumerationResponse,
    ComponentDetail,
    EmailSubscribeRequest,
    PlatformStatusSnapshotRead,
    PublicIncidentsResponse,
    SlackSubscribeRequest,
    TokenActionResponse,
    WebhookSubscribeRequest,
    WebhookSubscribeResponse,
)
from platform.status_page.service import StatusPageService
from typing import Any

from anyio import Path as AsyncPath
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

router = APIRouter(tags=["public-status"])


def _role_names(current_user: dict[str, Any]) -> set[str]:
    roles = current_user.get("roles", [])
    values: set[str] = set()
    if isinstance(roles, list):
        for role in roles:
            if isinstance(role, dict) and role.get("role") is not None:
                values.add(str(role["role"]))
            elif isinstance(role, str):
                values.add(role)
    return values


def _require_superadmin(current_user: dict[str, Any]) -> None:
    if "superadmin" in _role_names(current_user):
        return
    raise AuthorizationError("PERMISSION_DENIED", "Superadmin role required")


def _base_url(request: Request) -> str:
    forwarded_proto = request.headers.get("X-Forwarded-Proto")
    forwarded_host = request.headers.get("X-Forwarded-Host")
    if forwarded_host:
        scheme = forwarded_proto or request.url.scheme
        return f"{scheme}://{forwarded_host}".rstrip("/")
    return str(request.base_url).rstrip("/")


@router.get(
    "/api/v1/public/status",
    response_model=PlatformStatusSnapshotRead,
)
async def get_public_status(
    response: Response,
    service: StatusPageService = Depends(get_status_page_service),
) -> PlatformStatusSnapshotRead:
    result = await service.get_public_snapshot()
    response.headers["Cache-Control"] = "public, max-age=30, must-revalidate"
    response.headers["X-Snapshot-Age-Seconds"] = str(result.age_seconds)
    response.headers["X-Snapshot-Source"] = result.source
    return result.snapshot


@router.get(
    "/api/v1/public/components/{component_id}",
    response_model=ComponentDetail,
)
async def get_public_component(
    component_id: str,
    response: Response,
    days: int = Query(default=30, ge=1, le=90),
    service: StatusPageService = Depends(get_status_page_service),
) -> ComponentDetail:
    response.headers["Cache-Control"] = "public, max-age=30, must-revalidate"
    try:
        return await service.get_component_detail(component_id, days=days)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown component") from exc


@router.get(
    "/api/v1/public/incidents",
    response_model=PublicIncidentsResponse,
)
async def list_public_incidents(
    response: Response,
    status: str | None = Query(default=None, pattern="^(active|resolved)$"),
    since: datetime | None = Query(default=None),
    service: StatusPageService = Depends(get_status_page_service),
) -> PublicIncidentsResponse:
    del since
    response.headers["Cache-Control"] = "public, max-age=60, must-revalidate"
    return await service.list_public_incidents(status=status)


@router.get("/api/v1/public/status/feed.rss")
async def get_public_status_rss(
    request: Request,
    response: Response,
    service: StatusPageService = Depends(get_status_page_service),
) -> Response:
    snapshot = (await service.get_public_snapshot()).snapshot
    incidents = (await service.list_public_incidents()).incidents
    response.headers["Cache-Control"] = "public, max-age=60, must-revalidate"
    return Response(
        content=build_rss(snapshot, incidents, base_url=_base_url(request)),
        media_type="application/rss+xml; charset=utf-8",
        headers=dict(response.headers),
    )


@router.get("/api/v1/public/status/feed.atom")
async def get_public_status_atom(
    request: Request,
    response: Response,
    service: StatusPageService = Depends(get_status_page_service),
) -> Response:
    snapshot = (await service.get_public_snapshot()).snapshot
    incidents = (await service.list_public_incidents()).incidents
    response.headers["Cache-Control"] = "public, max-age=60, must-revalidate"
    return Response(
        content=build_atom(snapshot, incidents, base_url=_base_url(request)),
        media_type="application/atom+xml; charset=utf-8",
        headers=dict(response.headers),
    )


@router.post(
    "/api/v1/public/subscribe/email",
    response_model=AntiEnumerationResponse,
    status_code=202,
    dependencies=[Depends(enforce_subscribe_rate_limit)],
)
async def subscribe_email(
    payload: EmailSubscribeRequest,
    service: StatusPageService = Depends(get_status_page_service),
) -> AntiEnumerationResponse:
    return await service.submit_email_subscription(
        email=payload.email,
        scope_components=payload.scope_components,
    )


@router.get("/api/v1/public/subscribe/email/confirm", response_model=TokenActionResponse)
async def confirm_email_subscription(
    token: str = Query(min_length=16),
    service: StatusPageService = Depends(get_status_page_service),
) -> TokenActionResponse:
    return await service.confirm_email_subscription(token)


@router.get("/api/v1/public/subscribe/email/unsubscribe", response_model=TokenActionResponse)
async def unsubscribe_email_subscription(
    token: str = Query(min_length=16),
    service: StatusPageService = Depends(get_status_page_service),
) -> TokenActionResponse:
    return await service.unsubscribe(token)


@router.post(
    "/api/v1/public/subscribe/webhook",
    response_model=WebhookSubscribeResponse,
    status_code=202,
    dependencies=[Depends(enforce_subscribe_rate_limit)],
)
async def subscribe_webhook(
    payload: WebhookSubscribeRequest,
    service: StatusPageService = Depends(get_status_page_service),
) -> WebhookSubscribeResponse:
    return await service.submit_webhook_subscription(
        url=payload.url,
        scope_components=payload.scope_components,
        contact_email=payload.contact_email,
    )


@router.post(
    "/api/v1/public/subscribe/slack",
    response_model=WebhookSubscribeResponse,
    status_code=202,
    dependencies=[Depends(enforce_subscribe_rate_limit)],
)
async def subscribe_slack(
    payload: SlackSubscribeRequest,
    service: StatusPageService = Depends(get_status_page_service),
) -> WebhookSubscribeResponse:
    return await service.submit_slack_subscription(
        webhook_url=payload.webhook_url,
        scope_components=payload.scope_components,
    )


@router.post("/api/v1/internal/status_page/regenerate-fallback")
async def regenerate_status_fallback(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: StatusPageService = Depends(get_status_page_service),
) -> dict[str, Any]:
    _require_superadmin(current_user)
    snapshot = await service.compose_current_snapshot()
    target_path = getattr(request.app.state, "status_last_good_path", None)
    if isinstance(target_path, str) and target_path:
        path = AsyncPath(target_path)
        await path.parent.mkdir(parents=True, exist_ok=True)
        await path.write_text(snapshot.model_dump_json(), encoding="utf-8")
    return {
        "status": "ok",
        "snapshot_id": snapshot.snapshot_id,
        "generated_at": snapshot.generated_at.isoformat(),
    }
