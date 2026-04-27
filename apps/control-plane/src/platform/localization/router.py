from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.localization.dependencies import (
    get_locale_file_service,
    get_locale_resolver,
    get_localization_service,
    get_preferences_service,
)
from platform.localization.schemas import (
    LocaleFileListItem,
    LocaleFilePublishRequest,
    LocaleFileResponse,
    LocaleResolveRequest,
    LocaleResolveResponse,
    UserPreferencesResponse,
    UserPreferencesUpdateRequest,
)
from platform.localization.service import LocalizationService
from platform.localization.services.locale_file_service import LocaleFileService
from platform.localization.services.locale_resolver import LocaleResolver
from platform.localization.services.preferences_service import PreferencesService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response

router = APIRouter()


def _role_names(current_user: dict[str, Any]) -> set[str]:
    roles = current_user.get("roles", [])
    if not isinstance(roles, list):
        return set()
    names: set[str] = set()
    for item in roles:
        if isinstance(item, dict) and item.get("role") is not None:
            names.add(str(item["role"]))
        elif isinstance(item, str):
            names.add(item)
    return names


def _require_superadmin(current_user: dict[str, Any]) -> None:
    if "superadmin" not in _role_names(current_user):
        raise AuthorizationError("SUPERADMIN_REQUIRED", "Superadmin role required")


def _requester_id(current_user: dict[str, Any]) -> UUID:
    subject = current_user.get("sub")
    if subject is None:
        raise ValidationError("USER_ID_REQUIRED", "Authenticated user subject is required")
    return UUID(str(subject))


@router.get(
    "/api/v1/me/preferences",
    response_model=UserPreferencesResponse,
    tags=["localization-preferences"],
)
async def get_my_preferences(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: PreferencesService = Depends(get_preferences_service),
) -> UserPreferencesResponse:
    return await service.get_for_user(_requester_id(current_user))


@router.patch(
    "/api/v1/me/preferences",
    response_model=UserPreferencesResponse,
    tags=["localization-preferences"],
)
async def patch_my_preferences(
    payload: UserPreferencesUpdateRequest,
    response: Response,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: PreferencesService = Depends(get_preferences_service),
) -> UserPreferencesResponse:
    fields = payload.model_dump(exclude_unset=True)
    updated = await service.upsert(_requester_id(current_user), current_user, **fields)
    if payload.theme is not None:
        response.set_cookie(
            "musematic-theme",
            payload.theme,
            httponly=False,
            samesite="lax",
        )
    if payload.language is not None:
        response.set_cookie(
            "musematic-locale",
            payload.language,
            httponly=False,
            samesite="lax",
        )
    return updated


@router.get(
    "/api/v1/locales",
    response_model=list[LocaleFileListItem],
    tags=["localization-locales"],
)
async def list_locales(
    service: LocaleFileService = Depends(get_locale_file_service),
) -> list[LocaleFileListItem]:
    return await service.list_available()


@router.get(
    "/api/v1/locales/{locale_code}",
    response_model=LocaleFileResponse,
    tags=["localization-locales"],
)
async def get_locale_file(
    locale_code: str,
    service: LocaleFileService = Depends(get_locale_file_service),
) -> LocaleFileResponse:
    return await service.get_latest(locale_code)


@router.post(
    "/api/v1/locales/resolve",
    response_model=LocaleResolveResponse,
    tags=["localization-locales"],
)
async def resolve_locale(
    payload: LocaleResolveRequest,
    resolver: LocaleResolver = Depends(get_locale_resolver),
) -> LocaleResolveResponse:
    locale, source = await resolver.resolve(
        url_hint=payload.url_hint,
        user_preference=payload.user_preference,
        accept_language=payload.accept_language,
    )
    return LocaleResolveResponse(locale=locale, source=source)


@router.post(
    "/api/v1/admin/locales",
    response_model=LocaleFileResponse,
    status_code=201,
    tags=["localization-admin-locales"],
)
async def publish_locale_file(
    payload: LocaleFilePublishRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: LocalizationService = Depends(get_localization_service),
) -> LocaleFileResponse:
    _require_superadmin(current_user)
    return await service.publish_locale_file(
        locale_code=payload.locale_code,
        translations=payload.translations,
        requester=current_user,
        vendor_source_ref=payload.vendor_source_ref,
    )
