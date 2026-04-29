from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.common.exceptions import AuthorizationError
from platform.common.tagging.dependencies import (
    get_label_expression_cache,
    get_label_service,
    get_saved_view_service,
    get_tag_service,
)
from platform.common.tagging.exceptions import LabelExpressionSyntaxError
from platform.common.tagging.label_expression.cache import LabelExpressionCache
from platform.common.tagging.label_expression.parser import parse as parse_label_expression
from platform.common.tagging.label_service import LabelService
from platform.common.tagging.saved_view_service import SavedViewService
from platform.common.tagging.schemas import (
    CrossEntityTagSearchResponse,
    EntityLabelsResponse,
    EntityTagsResponse,
    LabelAttachRequest,
    LabelExpressionError,
    LabelExpressionValidationRequest,
    LabelExpressionValidationResponse,
    LabelResponse,
    SavedViewCreateRequest,
    SavedViewResponse,
    SavedViewUpdateRequest,
    TagAttachRequest,
    TagResponse,
)
from platform.common.tagging.tag_service import TagService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

tags_router = APIRouter(prefix="/api/v1/tags", tags=["common-tagging-tags"])
labels_router = APIRouter(prefix="/api/v1/labels", tags=["common-tagging-labels"])
admin_labels_router = APIRouter(
    prefix="/api/v1/admin/labels/reserved",
    tags=["common-tagging-admin-labels"],
)
saved_views_router = APIRouter(
    prefix="/api/v1/saved-views",
    tags=["common-tagging-saved-views"],
)


def _role_names(current_user: dict[str, Any]) -> set[str]:
    roles = current_user.get("roles", [])
    if not isinstance(roles, list):
        return set()
    names: set[str] = set()
    for role in roles:
        if isinstance(role, str):
            names.add(role)
        elif isinstance(role, dict) and isinstance(role.get("role"), str):
            names.add(role["role"])
        elif isinstance(role, dict) and isinstance(role.get("name"), str):
            names.add(role["name"])
    return names


def _require_superadmin(current_user: dict[str, Any]) -> None:
    if "superadmin" in _role_names(current_user):
        return
    raise AuthorizationError(
        "SUPERADMIN_REQUIRED",
        "Only superadmin callers may write reserved labels through the admin endpoint.",
    )


@tags_router.get("/{tag}/entities", response_model=CrossEntityTagSearchResponse)
async def cross_entity_tag_search(
    tag: str,
    entity_types: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict[str, Any] = Depends(get_current_user),
    tag_service: TagService = Depends(get_tag_service),
) -> CrossEntityTagSearchResponse:
    requested_types = (
        [item.strip() for item in entity_types.split(",") if item.strip()]
        if entity_types
        else None
    )
    return await tag_service.cross_entity_search(
        tag=tag,
        requester=current_user,
        entity_types=requested_types,
        cursor=cursor,
        limit=limit,
    )


@tags_router.post("/{entity_type}/{entity_id}", response_model=TagResponse)
async def attach_tag(
    entity_type: str,
    entity_id: UUID,
    payload: TagAttachRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    tag_service: TagService = Depends(get_tag_service),
) -> TagResponse:
    return await tag_service.attach(
        entity_type=entity_type,
        entity_id=entity_id,
        tag=payload.tag,
        requester=current_user,
    )


@tags_router.delete("/{entity_type}/{entity_id}/{tag}", status_code=204)
async def detach_tag(
    entity_type: str,
    entity_id: UUID,
    tag: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    tag_service: TagService = Depends(get_tag_service),
) -> Response:
    await tag_service.detach(
        entity_type=entity_type,
        entity_id=entity_id,
        tag=tag,
        requester=current_user,
    )
    return Response(status_code=204)


@tags_router.get("/{entity_type}/{entity_id}", response_model=EntityTagsResponse)
async def list_tags(
    entity_type: str,
    entity_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    tag_service: TagService = Depends(get_tag_service),
) -> EntityTagsResponse:
    return EntityTagsResponse(
        entity_type=entity_type,
        entity_id=entity_id,
        tags=await tag_service.list_for_entity(entity_type, entity_id, current_user),
    )


@labels_router.post(
    "/expression/validate",
    response_model=LabelExpressionValidationResponse,
    tags=["common-tagging-label-expression"],
)
async def validate_label_expression(
    payload: LabelExpressionValidationRequest,
    _current_user: dict[str, Any] = Depends(get_current_user),
    _label_expression_cache: LabelExpressionCache = Depends(get_label_expression_cache),
) -> LabelExpressionValidationResponse:
    del _current_user, _label_expression_cache
    try:
        parse_label_expression(payload.expression)
    except LabelExpressionSyntaxError as exc:
        return LabelExpressionValidationResponse(
            valid=False,
            error=LabelExpressionError(
                line=exc.line,
                col=exc.col,
                token=exc.token,
                message=exc.message,
            ),
        )
    return LabelExpressionValidationResponse(valid=True)


@labels_router.get("/keys", response_model=list[str])
async def list_label_keys(
    prefix: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    _current_user: dict[str, Any] = Depends(get_current_user),
    label_service: LabelService = Depends(get_label_service),
) -> list[str]:
    del _current_user
    return await label_service.list_keys(prefix=prefix, limit=limit)


@labels_router.get("/values", response_model=list[str])
async def list_label_values(
    key: str,
    prefix: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    _current_user: dict[str, Any] = Depends(get_current_user),
    label_service: LabelService = Depends(get_label_service),
) -> list[str]:
    del _current_user
    return await label_service.list_values(key=key, prefix=prefix, limit=limit)


@labels_router.post("/{entity_type}/{entity_id}", response_model=LabelResponse)
async def attach_label(
    entity_type: str,
    entity_id: UUID,
    payload: LabelAttachRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    label_service: LabelService = Depends(get_label_service),
) -> Any:
    return await label_service.attach(
        entity_type=entity_type,
        entity_id=entity_id,
        key=payload.key,
        value=payload.value,
        requester=current_user,
    )


@labels_router.delete("/{entity_type}/{entity_id}/{key}", status_code=204)
async def detach_label(
    entity_type: str,
    entity_id: UUID,
    key: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    label_service: LabelService = Depends(get_label_service),
) -> Response:
    await label_service.detach(
        entity_type=entity_type,
        entity_id=entity_id,
        key=key,
        requester=current_user,
    )
    return Response(status_code=204)


@labels_router.get("/{entity_type}/{entity_id}", response_model=EntityLabelsResponse)
async def list_labels(
    entity_type: str,
    entity_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    label_service: LabelService = Depends(get_label_service),
) -> EntityLabelsResponse:
    return EntityLabelsResponse(
        entity_type=entity_type,
        entity_id=entity_id,
        labels=await label_service.list_for_entity(entity_type, entity_id, current_user),
    )


@admin_labels_router.post("/{entity_type}/{entity_id}", response_model=LabelResponse)
async def attach_reserved_label(
    entity_type: str,
    entity_id: UUID,
    payload: LabelAttachRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    label_service: LabelService = Depends(get_label_service),
) -> Any:
    _require_superadmin(current_user)
    return await label_service.attach(
        entity_type=entity_type,
        entity_id=entity_id,
        key=payload.key,
        value=payload.value,
        requester=current_user,
        allow_reserved=True,
    )


@saved_views_router.post("", response_model=SavedViewResponse, status_code=201)
async def create_saved_view(
    payload: SavedViewCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    saved_view_service: SavedViewService = Depends(get_saved_view_service),
) -> SavedViewResponse:
    return await saved_view_service.create(
        requester=current_user,
        workspace_id=payload.workspace_id,
        name=payload.name,
        entity_type=payload.entity_type,
        filters=payload.filters,
        shared=payload.shared,
    )


@saved_views_router.get("", response_model=list[SavedViewResponse])
async def list_saved_views(
    entity_type: str,
    workspace_id: UUID | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
    saved_view_service: SavedViewService = Depends(get_saved_view_service),
) -> list[SavedViewResponse]:
    return await saved_view_service.list_for_user(current_user, entity_type, workspace_id)


@saved_views_router.get("/{view_id}", response_model=SavedViewResponse)
async def get_saved_view(
    view_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    saved_view_service: SavedViewService = Depends(get_saved_view_service),
) -> SavedViewResponse:
    return await saved_view_service.get(view_id, current_user)


@saved_views_router.patch("/{view_id}", response_model=SavedViewResponse)
async def update_saved_view(
    view_id: UUID,
    payload: SavedViewUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    saved_view_service: SavedViewService = Depends(get_saved_view_service),
) -> SavedViewResponse:
    return await saved_view_service.update(
        view_id,
        payload.expected_version,
        current_user,
        name=payload.name,
        filters=payload.filters,
        shared=payload.shared,
    )


@saved_views_router.post("/{view_id}/share", response_model=SavedViewResponse)
async def share_saved_view(
    view_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    saved_view_service: SavedViewService = Depends(get_saved_view_service),
) -> SavedViewResponse:
    return await saved_view_service.share(view_id, current_user)


@saved_views_router.post("/{view_id}/unshare", response_model=SavedViewResponse)
async def unshare_saved_view(
    view_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    saved_view_service: SavedViewService = Depends(get_saved_view_service),
) -> SavedViewResponse:
    return await saved_view_service.unshare(view_id, current_user)


@saved_views_router.delete("/{view_id}", status_code=204)
async def delete_saved_view(
    view_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    saved_view_service: SavedViewService = Depends(get_saved_view_service),
) -> Response:
    await saved_view_service.delete(view_id, current_user)
    return Response(status_code=204)
