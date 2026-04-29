from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.common.tagging.exceptions import (
    EntityNotFoundForTagError,
    InvalidLabelKeyError,
    LabelAttachLimitExceededError,
    LabelValueTooLongError,
    ReservedLabelNamespaceError,
    SavedViewNotFoundError,
)
from platform.common.tagging.label_service import LabelService
from platform.common.tagging.saved_view_service import SavedViewService
from platform.common.tagging.service import TaggingService
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest


class LabelRepoStub:
    def __init__(self) -> None:
        self.labels: dict[tuple[str, UUID, str], SimpleNamespace] = {}
        self.deleted: list[tuple[str, UUID, str]] = []
        self.cascaded: list[tuple[str, UUID]] = []
        self.filter_args: tuple[str, dict[str, str], set[UUID], str | None, int] | None = None

    async def upsert_label(
        self,
        entity_type: str,
        entity_id: UUID,
        key: str,
        value: str,
        updated_by: UUID | None,
    ) -> tuple[SimpleNamespace, str | None]:
        old = self.labels.get((entity_type, entity_id, key))
        row = SimpleNamespace(
            entity_type=entity_type,
            entity_id=entity_id,
            label_key=key,
            label_value=value,
            created_by=updated_by,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.labels[(entity_type, entity_id, key)] = row
        return row, old.label_value if old is not None else None

    async def get_label(
        self,
        entity_type: str,
        entity_id: UUID,
        key: str,
    ) -> SimpleNamespace | None:
        return self.labels.get((entity_type, entity_id, key))

    async def count_labels_for_entity(self, entity_type: str, entity_id: UUID) -> int:
        return sum(
            1
            for row_entity_type, row_entity_id, _key in self.labels
            if row_entity_type == entity_type and row_entity_id == entity_id
        )

    async def delete_label(self, entity_type: str, entity_id: UUID, key: str) -> bool:
        self.deleted.append((entity_type, entity_id, key))
        return self.labels.pop((entity_type, entity_id, key), None) is not None

    async def list_labels_for_entity(
        self,
        entity_type: str,
        entity_id: UUID,
    ) -> list[SimpleNamespace]:
        return [
            row
            for (row_type, row_id, _key), row in self.labels.items()
            if row_type == entity_type and row_id == entity_id
        ]

    async def filter_entities_by_labels(
        self,
        entity_type: str,
        label_filters: dict[str, str],
        visible_entity_ids: set[UUID],
        *,
        cursor: str | None,
        limit: int,
    ) -> list[UUID]:
        self.filter_args = (entity_type, label_filters, visible_entity_ids, cursor, limit)
        return sorted(visible_entity_ids, key=str)

    async def list_label_keys(self, *, prefix: str, limit: int) -> list[str]:
        del limit
        return sorted(
            {
                key
                for (_entity_type, _entity_id, key), _row in self.labels.items()
                if key.startswith(prefix)
            }
        )

    async def list_label_values(self, *, key: str, prefix: str, limit: int) -> list[str]:
        del limit
        return sorted(
            {
                row.label_value
                for (_entity_type, _entity_id, row_key), row in self.labels.items()
                if row_key == key and row.label_value.startswith(prefix)
            }
        )

    async def cascade_on_entity_deletion(self, entity_type: str, entity_id: UUID) -> None:
        self.cascaded.append((entity_type, entity_id))


class AuditStub:
    def __init__(self) -> None:
        self.entries: list[tuple[UUID | None, str, bytes]] = []

    async def append(
        self,
        audit_event_id: UUID | None,
        audit_event_source: str,
        canonical_payload: bytes,
    ) -> None:
        self.entries.append((audit_event_id, audit_event_source, canonical_payload))


class SavedViewRepoStub:
    def __init__(self) -> None:
        self.views: dict[UUID, SimpleNamespace] = {}
        self.personal: list[SimpleNamespace] = []
        self.shared: list[SimpleNamespace] = []
        self.deleted: list[UUID] = []

    async def insert_saved_view(
        self,
        *,
        owner_id: UUID,
        workspace_id: UUID | None,
        name: str,
        entity_type: str,
        filters: dict[str, object],
        shared: bool,
    ) -> SimpleNamespace:
        row = _saved_view_row(
            owner_id=owner_id,
            workspace_id=workspace_id,
            name=name,
            entity_type=entity_type,
            filters=filters,
            shared=shared,
        )
        self.views[row.id] = row
        return row

    async def get_saved_view(self, view_id: UUID) -> SimpleNamespace | None:
        return self.views.get(view_id)

    async def list_personal_views(
        self,
        owner_id: UUID,
        entity_type: str,
        workspace_id: UUID | None,
    ) -> list[SimpleNamespace]:
        return [
            view
            for view in self.personal
            if view.owner_id == owner_id
            and view.entity_type == entity_type
            and view.workspace_id == workspace_id
        ]

    async def list_shared_views(
        self,
        workspace_id: UUID,
        entity_type: str,
    ) -> list[SimpleNamespace]:
        return [
            view
            for view in self.shared
            if view.workspace_id == workspace_id and view.entity_type == entity_type
        ]

    async def update_saved_view(
        self,
        view_id: UUID,
        expected_version: int,
        **fields: object,
    ) -> SimpleNamespace | None:
        view = self.views.get(view_id)
        if view is None or view.version != expected_version:
            return None
        for key, value in fields.items():
            if value is not None:
                setattr(view, key, value)
        view.version += 1
        view.updated_at = datetime.now(UTC)
        return view

    async def delete_saved_view(self, view_id: UUID) -> bool:
        self.deleted.append(view_id)
        return self.views.pop(view_id, None) is not None


def _saved_view_row(
    *,
    owner_id: UUID,
    workspace_id: UUID | None,
    name: str,
    entity_type: str,
    filters: dict[str, object] | None = None,
    shared: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        owner_id=owner_id,
        workspace_id=workspace_id,
        name=name,
        entity_type=entity_type,
        filters=filters or {},
        shared=shared,
        is_orphan_transferred=False,
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_label_service_validates_reserved_keys_and_delegates_queries() -> None:
    repo = LabelRepoStub()
    service = LabelService(repo, max_labels_per_entity=3)  # type: ignore[arg-type]
    entity_id = uuid4()
    actor_id = uuid4()

    with pytest.raises(ReservedLabelNamespaceError):
        await service.attach(
            entity_type="agent",
            entity_id=entity_id,
            key="system.owner",
            value="platform",
            requester={"sub": str(actor_id)},
        )
    with pytest.raises(InvalidLabelKeyError):
        await service.attach(
            entity_type="agent",
            entity_id=entity_id,
            key="1invalid",
            value="platform",
            requester={"sub": str(actor_id)},
        )
    with pytest.raises(LabelValueTooLongError):
        await service.attach(
            entity_type="agent",
            entity_id=entity_id,
            key="owner",
            value="x" * 513,
            requester={"sub": str(actor_id)},
        )

    label = await service.attach(
        entity_type="agent",
        entity_id=entity_id,
        key="system.owner",
        value="platform",
        requester={"roles": [{"role": "superadmin"}], "sub": str(actor_id)},
    )
    service_account_label = await service.attach(
        entity_type="agent",
        entity_id=entity_id,
        key="platform.lifecycle",
        value="active",
        requester={"service_account": True, "user_id": str(actor_id)},
    )
    labels = await service.list_for_entity("agent", entity_id, {"sub": str(actor_id)})
    visible_ids = {entity_id, uuid4()}
    filtered = await service.filter_query(
        "agent",
        {"system.owner": "platform"},
        visible_ids,
        cursor="2",
        limit=10,
    )
    keys = await service.list_keys(prefix="platform", limit=10)
    values = await service.list_values(key="platform.lifecycle", prefix="act", limit=10)
    await service.detach(
        entity_type="agent",
        entity_id=entity_id,
        key="system.owner",
        requester={"sub": str(actor_id)},
    )
    await service.cascade_on_entity_deletion("agent", entity_id)

    assert label.is_reserved is True
    assert service_account_label.key == "platform.lifecycle"
    assert {item.key for item in labels} == {"system.owner", "platform.lifecycle"}
    assert filtered == sorted(visible_ids, key=str)
    assert keys == ["platform.lifecycle"]
    assert values == ["active"]
    assert repo.filter_args == ("agent", {"system.owner": "platform"}, visible_ids, "2", 10)
    assert repo.deleted == [("agent", entity_id, "system.owner")]
    assert repo.cascaded == [("agent", entity_id)]


@pytest.mark.asyncio
async def test_label_service_limit_and_access_checks() -> None:
    repo = LabelRepoStub()
    allowed_id = uuid4()
    blocked_id = uuid4()

    async def access_check(
        entity_type: str,
        entity_id: UUID,
        requester: object,
        action: str,
    ) -> bool:
        del requester, action
        return entity_type == "agent" and entity_id == allowed_id

    service = LabelService(
        repo,
        entity_access_check=access_check,
        max_labels_per_entity=1,
    )  # type: ignore[arg-type]

    await service.attach(
        entity_type="agent",
        entity_id=allowed_id,
        key="env",
        value="production",
        requester={"sub": str(uuid4())},
    )
    await service.attach(
        entity_type="agent",
        entity_id=allowed_id,
        key="env",
        value="staging",
        requester={"sub": str(uuid4())},
    )

    with pytest.raises(LabelAttachLimitExceededError):
        await service.attach(
            entity_type="agent",
            entity_id=allowed_id,
            key="tier",
            value="critical",
            requester={"sub": str(uuid4())},
        )
    with pytest.raises(EntityNotFoundForTagError):
        await service.attach(
            entity_type="agent",
            entity_id=blocked_id,
            key="env",
            value="production",
            requester={"sub": str(uuid4())},
        )


@pytest.mark.asyncio
async def test_label_service_audits_upsert_with_old_and_new_values() -> None:
    repo = LabelRepoStub()
    audit = AuditStub()
    service = LabelService(repo, audit_chain=audit)  # type: ignore[arg-type]
    entity_id = uuid4()
    actor_id = uuid4()

    await service.attach(
        entity_type="agent",
        entity_id=entity_id,
        key="env",
        value="staging",
        requester={"sub": str(actor_id)},
    )
    await service.attach(
        entity_type="agent",
        entity_id=entity_id,
        key="env",
        value="production",
        requester={"sub": str(actor_id)},
    )

    first_payload = json.loads(audit.entries[0][2].decode("utf-8"))
    second_payload = json.loads(audit.entries[1][2].decode("utf-8"))
    assert audit.entries[0][1] == "common_tagging"
    assert first_payload["old_value"] is None
    assert first_payload["new_value"] == "staging"
    assert second_payload["old_value"] == "staging"
    assert second_payload["new_value"] == "production"


@pytest.mark.asyncio
async def test_saved_view_service_owner_shared_and_not_found_paths() -> None:
    repo = SavedViewRepoStub()
    service = SavedViewService(repo)  # type: ignore[arg-type]
    owner_id = uuid4()
    workspace_id = uuid4()
    requester = SimpleNamespace(id=owner_id)

    with pytest.raises(SavedViewNotFoundError):
        await service.create(
            requester={},
            workspace_id=workspace_id,
            name="mine",
            entity_type="agent",
            filters={},
            shared=False,
        )

    created = await service.create(
        requester=requester,
        workspace_id=workspace_id,
        name="mine",
        entity_type="agent",
        filters={"labels": {"env": "prod"}},
        shared=False,
    )
    shared = _saved_view_row(
        owner_id=uuid4(),
        workspace_id=workspace_id,
        name="shared",
        entity_type="agent",
        shared=True,
    )
    repo.personal = [repo.views[created.id]]
    repo.shared = [shared, repo.views[created.id]]

    listed = await service.list_for_user(
        {"sub": str(owner_id)},
        entity_type="agent",
        workspace_id=workspace_id,
    )
    renamed = await service.update(
        created.id,
        created.version,
        {"sub": str(owner_id)},
        name="renamed",
    )
    shared_view = await service.share(created.id, {"sub": str(owner_id)})
    unshared_view = await service.unshare(created.id, {"sub": str(owner_id)})
    await service.delete(created.id, {"sub": str(owner_id)})

    assert created.is_owner is True
    assert {view.name for view in listed} == {"mine", "shared"}
    assert renamed.name == "renamed"
    assert shared_view.is_shared is True
    assert unshared_view.is_shared is False
    assert repo.deleted == [created.id]

    with pytest.raises(SavedViewNotFoundError):
        await service.get(uuid4(), {"sub": str(owner_id)})
    with pytest.raises(SavedViewNotFoundError):
        await service.update(uuid4(), 1, {"sub": str(owner_id)}, name="missing")
    with pytest.raises(SavedViewNotFoundError):
        await service.delete(uuid4(), {"sub": str(owner_id)})
    assert await service.list_for_user({}, "agent", workspace_id) == []


@pytest.mark.asyncio
async def test_tagging_service_cascades_through_tag_service() -> None:
    cascaded: list[tuple[str, UUID]] = []

    class Tags:
        async def cascade_on_entity_deletion(self, entity_type: str, entity_id: UUID) -> None:
            cascaded.append((entity_type, entity_id))

    service = TaggingService(Tags(), object(), object())  # type: ignore[arg-type]
    entity_id = uuid4()

    await service.cascade_on_entity_deletion("workspace", entity_id)
    await service.handle_workspace_archived(entity_id)

    assert service.labels is not None
    assert service.saved_views is not None
    assert cascaded == [("workspace", entity_id)]
