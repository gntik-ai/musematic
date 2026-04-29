from __future__ import annotations

from datetime import UTC, datetime
from platform.common.tagging import router
from platform.common.tagging.schemas import (
    LabelAttachRequest,
    LabelExpressionValidationRequest,
    LabelResponse,
    SavedViewCreateRequest,
    SavedViewResponse,
    SavedViewUpdateRequest,
    TagAttachRequest,
    TagResponse,
)
from uuid import uuid4

import pytest

NOW = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)


class _TagService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def cross_entity_search(self, **kwargs: object) -> object:
        self.calls.append(("cross_entity_search", kwargs))
        return {"tag": kwargs["tag"], "entities": {}, "next_cursor": None}

    async def attach(self, **kwargs: object) -> TagResponse:
        self.calls.append(("attach", kwargs))
        return TagResponse(tag=str(kwargs["tag"]), created_by=None, created_at=NOW)

    async def detach(self, **kwargs: object) -> None:
        self.calls.append(("detach", kwargs))

    async def list_for_entity(
        self,
        entity_type: str,
        entity_id: object,
        requester: dict[str, object],
    ) -> list[TagResponse]:
        self.calls.append(("list_for_entity", (entity_type, entity_id, requester)))
        return [TagResponse(tag="priority", created_by=None, created_at=NOW)]


class _LabelService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def attach(self, **kwargs: object) -> LabelResponse:
        self.calls.append(("attach", kwargs))
        return LabelResponse(
            key=str(kwargs["key"]),
            value=str(kwargs["value"]),
            created_by=None,
            created_at=NOW,
            updated_at=NOW,
            is_reserved=bool(kwargs.get("allow_reserved", False)),
        )

    async def detach(self, **kwargs: object) -> None:
        self.calls.append(("detach", kwargs))

    async def list_for_entity(
        self,
        entity_type: str,
        entity_id: object,
        requester: dict[str, object],
    ) -> list[LabelResponse]:
        self.calls.append(("list_for_entity", (entity_type, entity_id, requester)))
        return [
            LabelResponse(
                key="owner",
                value="ops",
                created_by=None,
                created_at=NOW,
                updated_at=NOW,
                is_reserved=False,
            )
        ]

    async def list_keys(self, **kwargs: object) -> list[str]:
        self.calls.append(("list_keys", kwargs))
        return ["env"]

    async def list_values(self, **kwargs: object) -> list[str]:
        self.calls.append(("list_values", kwargs))
        return ["production"]


class _SavedViewService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.response = SavedViewResponse(
            id=uuid4(),
            owner_id=uuid4(),
            workspace_id=uuid4(),
            name="Ops",
            entity_type="agent",
            filters={"label": "ops"},
            is_owner=True,
            is_shared=False,
            is_orphan_transferred=False,
            version=1,
            created_at=NOW,
            updated_at=NOW,
        )

    async def create(self, **kwargs: object) -> SavedViewResponse:
        self.calls.append(("create", kwargs))
        return self.response

    async def list_for_user(
        self,
        requester: dict[str, object],
        entity_type: str,
        workspace_id: object,
    ) -> list[SavedViewResponse]:
        self.calls.append(("list_for_user", (requester, entity_type, workspace_id)))
        return [self.response]

    async def get(self, view_id: object, requester: dict[str, object]) -> SavedViewResponse:
        self.calls.append(("get", (view_id, requester)))
        return self.response

    async def update(
        self,
        view_id: object,
        expected_version: int,
        requester: dict[str, object],
        **kwargs: object,
    ) -> SavedViewResponse:
        self.calls.append(("update", (view_id, expected_version, requester, kwargs)))
        return self.response

    async def share(self, view_id: object, requester: dict[str, object]) -> SavedViewResponse:
        self.calls.append(("share", (view_id, requester)))
        return self.response

    async def unshare(self, view_id: object, requester: dict[str, object]) -> SavedViewResponse:
        self.calls.append(("unshare", (view_id, requester)))
        return self.response

    async def delete(self, view_id: object, requester: dict[str, object]) -> None:
        self.calls.append(("delete", (view_id, requester)))


@pytest.mark.asyncio
async def test_tag_router_delegates_and_normalizes_entity_type_filter() -> None:
    service = _TagService()
    requester = {"sub": str(uuid4())}
    entity_id = uuid4()

    search = await router.cross_entity_tag_search(
        "priority",
        entity_types="agent, workflow, ",
        cursor="c1",
        limit=25,
        current_user=requester,
        tag_service=service,  # type: ignore[arg-type]
    )
    tag = await router.attach_tag(
        "agent",
        entity_id,
        TagAttachRequest(tag="priority"),
        current_user=requester,
        tag_service=service,  # type: ignore[arg-type]
    )
    detach_response = await router.detach_tag(
        "agent",
        entity_id,
        "priority",
        current_user=requester,
        tag_service=service,  # type: ignore[arg-type]
    )
    listed = await router.list_tags(
        "agent",
        entity_id,
        current_user=requester,
        tag_service=service,  # type: ignore[arg-type]
    )

    assert search["entities"] == {}
    assert service.calls[0][1]["entity_types"] == ["agent", "workflow"]  # type: ignore[index]
    assert tag.tag == "priority"
    assert detach_response.status_code == 204
    assert listed.tags[0].tag == "priority"


@pytest.mark.asyncio
async def test_label_router_delegates_reserved_and_regular_labels() -> None:
    service = _LabelService()
    requester = {"sub": str(uuid4())}
    admin_requester = {"sub": str(uuid4()), "roles": [{"role": "superadmin"}]}
    entity_id = uuid4()

    label = await router.attach_label(
        "agent",
        entity_id,
        LabelAttachRequest(key="owner", value=" ops "),
        current_user=requester,
        label_service=service,  # type: ignore[arg-type]
    )
    detach_response = await router.detach_label(
        "agent",
        entity_id,
        "owner",
        current_user=requester,
        label_service=service,  # type: ignore[arg-type]
    )
    listed = await router.list_labels(
        "agent",
        entity_id,
        current_user=requester,
        label_service=service,  # type: ignore[arg-type]
    )
    reserved = await router.attach_reserved_label(
        "agent",
        entity_id,
        LabelAttachRequest(key="system.owner", value="platform"),
        current_user=admin_requester,
        label_service=service,  # type: ignore[arg-type]
    )
    validation = await router.validate_label_expression(
        LabelExpressionValidationRequest(expression="env=production"),
        _current_user=requester,
        _label_expression_cache=object(),  # type: ignore[arg-type]
    )
    invalid_validation = await router.validate_label_expression(
        LabelExpressionValidationRequest(expression="env=production AND"),
        _current_user=requester,
        _label_expression_cache=object(),  # type: ignore[arg-type]
    )
    keys = await router.list_label_keys(
        prefix="e",
        limit=10,
        _current_user=requester,
        label_service=service,  # type: ignore[arg-type]
    )
    values = await router.list_label_values(
        key="env",
        prefix="pro",
        limit=10,
        _current_user=requester,
        label_service=service,  # type: ignore[arg-type]
    )

    assert label.value == "ops"
    assert detach_response.status_code == 204
    assert listed.labels[0].key == "owner"
    assert reserved.is_reserved is True
    assert validation.valid is True
    assert invalid_validation.valid is False
    assert invalid_validation.error is not None
    assert keys == ["env"]
    assert values == ["production"]


@pytest.mark.asyncio
async def test_saved_view_router_delegates_lifecycle_actions() -> None:
    service = _SavedViewService()
    requester = {"sub": str(uuid4())}
    view_id = uuid4()
    workspace_id = uuid4()

    created = await router.create_saved_view(
        SavedViewCreateRequest(
            workspace_id=workspace_id,
            name="Ops",
            entity_type="agent",
            filters={"label": "ops"},
            shared=True,
        ),
        current_user=requester,
        saved_view_service=service,  # type: ignore[arg-type]
    )
    listed = await router.list_saved_views(
        "agent",
        workspace_id=workspace_id,
        current_user=requester,
        saved_view_service=service,  # type: ignore[arg-type]
    )
    fetched = await router.get_saved_view(
        view_id,
        current_user=requester,
        saved_view_service=service,  # type: ignore[arg-type]
    )
    updated = await router.update_saved_view(
        view_id,
        SavedViewUpdateRequest(expected_version=1, name="New"),
        current_user=requester,
        saved_view_service=service,  # type: ignore[arg-type]
    )
    shared = await router.share_saved_view(
        view_id,
        current_user=requester,
        saved_view_service=service,  # type: ignore[arg-type]
    )
    unshared = await router.unshare_saved_view(
        view_id,
        current_user=requester,
        saved_view_service=service,  # type: ignore[arg-type]
    )
    deleted = await router.delete_saved_view(
        view_id,
        current_user=requester,
        saved_view_service=service,  # type: ignore[arg-type]
    )

    assert created == service.response
    assert listed == [service.response]
    assert fetched == service.response
    assert updated == service.response
    assert shared == service.response
    assert unshared == service.response
    assert deleted.status_code == 204
    assert [name for name, _ in service.calls] == [
        "create",
        "list_for_user",
        "get",
        "update",
        "share",
        "unshare",
        "delete",
    ]
