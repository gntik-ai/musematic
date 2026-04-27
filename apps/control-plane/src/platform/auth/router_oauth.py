from __future__ import annotations

import base64
import json
from platform.auth.dependencies_oauth import get_oauth_service, rate_limit_callback
from platform.auth.schemas import (
    OAuthAuditEntryListResponse,
    OAuthAuthorizeResponse,
    OAuthConnectivityTestResponse,
    OAuthLinkListResponse,
    OAuthProviderAdminListResponse,
    OAuthProviderAdminResponse,
    OAuthProviderCreate,
    OAuthProviderPublicListResponse,
)
from platform.auth.services.oauth_service import OAuthService
from platform.common.dependencies import get_current_user
from platform.common.exceptions import AuthorizationError, PlatformError
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import RedirectResponse

oauth_router = APIRouter(tags=["oauth"])


def _require_platform_admin(current_user: dict[str, Any]) -> None:
    role_names = {
        str(item.get("role")) for item in current_user.get("roles", []) if isinstance(item, dict)
    }
    if "platform_admin" in role_names or "superadmin" in role_names:
        return
    raise AuthorizationError("PERMISSION_DENIED", "Platform admin role required")


def _frontend_oauth_callback_redirect(request: Request, provider: str) -> str:
    origin = request.headers.get("Origin")
    if origin:
        return f"{origin.rstrip('/')}/auth/oauth/{provider}/callback"
    return f"/auth/oauth/{provider}/callback"


def _frontend_profile_redirect(request: Request) -> str:
    origin = request.headers.get("Origin")
    if origin:
        return f"{origin.rstrip('/')}/profile"
    return "/profile"


def _oauth_session_fragment(payload: dict[str, Any]) -> str:
    encoded = base64.urlsafe_b64encode(
        json.dumps(jsonable_encoder(payload)).encode("utf-8")
    ).decode("utf-8")
    return encoded.rstrip("=")


@oauth_router.get("/api/v1/auth/oauth/providers", response_model=OAuthProviderPublicListResponse)
async def list_public_oauth_providers(
    oauth_service: OAuthService = Depends(get_oauth_service),
) -> OAuthProviderPublicListResponse:
    return await oauth_service.list_public_providers()


@oauth_router.get("/api/v1/auth/oauth/links", response_model=OAuthLinkListResponse)
async def list_oauth_links(
    current_user: dict[str, Any] = Depends(get_current_user),
    oauth_service: OAuthService = Depends(get_oauth_service),
) -> OAuthLinkListResponse:
    return await oauth_service.list_links(UUID(str(current_user["sub"])))


@oauth_router.get(
    "/api/v1/auth/oauth/{provider}/authorize",
    response_model=OAuthAuthorizeResponse,
)
async def authorize_oauth_provider(
    provider: str,
    oauth_service: OAuthService = Depends(get_oauth_service),
) -> OAuthAuthorizeResponse:
    return await oauth_service.get_authorization_url(provider)


@oauth_router.post(
    "/api/v1/auth/oauth/{provider}/link",
    response_model=OAuthAuthorizeResponse,
)
async def link_oauth_provider(
    provider: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    oauth_service: OAuthService = Depends(get_oauth_service),
) -> OAuthAuthorizeResponse:
    return await oauth_service.get_authorization_url(
        provider,
        link_for_user_id=UUID(str(current_user["sub"])),
    )


@oauth_router.delete(
    "/api/v1/auth/oauth/{provider}/link",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def unlink_oauth_provider(
    provider: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    oauth_service: OAuthService = Depends(get_oauth_service),
) -> Response:
    await oauth_service.unlink_account(UUID(str(current_user["sub"])), provider)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@oauth_router.get("/api/v1/auth/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    _rate_limit: None = Depends(rate_limit_callback),
    oauth_service: OAuthService = Depends(get_oauth_service),
) -> RedirectResponse:
    del _rate_limit
    if error is not None:
        return RedirectResponse(
            url=f"{_frontend_oauth_callback_redirect(request, provider)}?error={error}",
            status_code=status.HTTP_302_FOUND,
        )
    if not code or not state:
        return RedirectResponse(
            url=(
                f"{_frontend_oauth_callback_redirect(request, provider)}"
                "?error=invalid_oauth_callback"
            ),
            status_code=status.HTTP_302_FOUND,
        )
    try:
        result = await oauth_service.handle_callback(
            provider_type=provider,
            code=code,
            raw_state=state,
            source_ip=request.client.host if request.client is not None else "0.0.0.0",
            user_agent=request.headers.get("User-Agent", ""),
        )
    except PlatformError as exc:
        return RedirectResponse(
            url=f"{_frontend_oauth_callback_redirect(request, provider)}?error={exc.code.lower()}",
            status_code=status.HTTP_302_FOUND,
        )
    if result.get("linked"):
        return RedirectResponse(
            url=f"{_frontend_profile_redirect(request)}?message=oauth_linked",
            status_code=status.HTTP_302_FOUND,
        )
    fragment = _oauth_session_fragment(result)
    response = RedirectResponse(
        url=f"{_frontend_oauth_callback_redirect(request, provider)}#oauth_session={fragment}",
        status_code=status.HTTP_302_FOUND,
    )
    token_pair = result.get("token_pair")
    if token_pair is not None:
        response.set_cookie(
            "session",
            token_pair.access_token,
            httponly=True,
            samesite="lax",
            secure=False,
        )
    return response


@oauth_router.get(
    "/api/v1/admin/oauth/providers",
    response_model=OAuthProviderAdminListResponse,
    tags=["admin"],
)
async def list_admin_oauth_providers(
    current_user: dict[str, Any] = Depends(get_current_user),
    oauth_service: OAuthService = Depends(get_oauth_service),
) -> OAuthProviderAdminListResponse:
    _require_platform_admin(current_user)
    return await oauth_service.list_admin_providers()


@oauth_router.put(
    "/api/v1/admin/oauth/providers/{provider}",
    response_model=OAuthProviderAdminResponse,
    tags=["admin"],
)
async def upsert_oauth_provider(
    provider: str,
    payload: OAuthProviderCreate,
    response: Response,
    current_user: dict[str, Any] = Depends(get_current_user),
    oauth_service: OAuthService = Depends(get_oauth_service),
) -> OAuthProviderAdminResponse:
    _require_platform_admin(current_user)
    provider_response, created = await oauth_service.upsert_provider(
        provider_type=provider,
        actor_id=UUID(str(current_user["sub"])),
        display_name=payload.display_name,
        enabled=payload.enabled,
        client_id=payload.client_id,
        client_secret_ref=payload.client_secret_ref,
        redirect_uri=payload.redirect_uri,
        scopes=payload.scopes,
        domain_restrictions=payload.domain_restrictions,
        org_restrictions=payload.org_restrictions,
        group_role_mapping=payload.group_role_mapping,
        default_role=payload.default_role,
        require_mfa=payload.require_mfa,
    )
    if created:
        response.status_code = status.HTTP_201_CREATED
    return provider_response


@oauth_router.post(
    "/api/v1/admin/oauth-providers/{provider}/test-connectivity",
    response_model=OAuthConnectivityTestResponse,
    tags=["admin"],
)
@oauth_router.post(
    "/api/v1/admin/oauth/providers/{provider}/test-connectivity",
    response_model=OAuthConnectivityTestResponse,
    tags=["admin"],
    include_in_schema=False,
)
async def probe_oauth_provider_connectivity(
    provider: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    oauth_service: OAuthService = Depends(get_oauth_service),
) -> OAuthConnectivityTestResponse:
    _require_platform_admin(current_user)
    try:
        response = await oauth_service.get_authorization_url(provider, dry_run=True)
    except PlatformError as exc:
        return OAuthConnectivityTestResponse(
            reachable=False,
            auth_url_returned=False,
            diagnostic=exc.message,
        )
    return OAuthConnectivityTestResponse(
        reachable=True,
        auth_url_returned=bool(response.redirect_url),
        diagnostic="authorization_url_generated",
    )


@oauth_router.get(
    "/api/v1/admin/oauth/audit",
    response_model=OAuthAuditEntryListResponse,
    tags=["admin"],
)
async def list_oauth_audit_entries(
    provider_type: str | None = Query(default=None),
    user_id: UUID | None = Query(default=None),
    outcome: str | None = Query(default=None),
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict[str, Any] = Depends(get_current_user),
    oauth_service: OAuthService = Depends(get_oauth_service),
) -> OAuthAuditEntryListResponse:
    _require_platform_admin(current_user)
    return await oauth_service.list_audit_entries(
        provider_type=provider_type,
        user_id=user_id,
        outcome=outcome,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
