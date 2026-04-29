from __future__ import annotations

from datetime import UTC, datetime
from platform.common.tagging.exceptions import (
    EntityNotFoundForTagError,
    EntityTypeNotRegisteredError,
    InvalidTagError,
    TagAttachLimitExceededError,
)
from platform.common.tagging.tag_service import TagService
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest


class RepoStub:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, UUID, str], SimpleNamespace] = {}
        self.cascaded: list[tuple[str, UUID]] = []
        self.search_visible: dict[str, set[UUID]] | None = None

    async def get_tag(
        self,
        entity_type: str,
        entity_id: UUID,
        tag: str,
    ) -> SimpleNamespace | None:
        return self.rows.get((entity_type, entity_id, tag))

    async def count_tags_for_entity(self, entity_type: str, entity_id: UUID) -> int:
        return sum(
            1
            for row_entity_type, row_entity_id, _tag in self.rows
            if row_entity_type == entity_type and row_entity_id == entity_id
        )

    async def insert_tag(
        self,
        entity_type: str,
        entity_id: UUID,
        tag: str,
        created_by: UUID | None,
    ) -> SimpleNamespace:
        row = SimpleNamespace(
            entity_type=entity_type,
            entity_id=entity_id,
            tag=tag,
            created_by=created_by,
            created_at=datetime.now(UTC),
        )
        self.rows.setdefault((entity_type, entity_id, tag), row)
        return self.rows[(entity_type, entity_id, tag)]

    async def delete_tag(self, entity_type: str, entity_id: UUID, tag: str) -> bool:
        return self.rows.pop((entity_type, entity_id, tag), None) is not None

    async def list_tags_for_entity(
        self,
        entity_type: str,
        entity_id: UUID,
    ) -> list[SimpleNamespace]:
        return [
            row
            for (row_entity_type, row_entity_id, _tag), row in self.rows.items()
            if row_entity_type == entity_type and row_entity_id == entity_id
        ]

    async def list_entities_by_tag(
        self,
        tag: str,
        visible_entity_ids_by_type: dict[str, set[UUID]],
        *,
        cursor: str | None,
        limit: int,
    ) -> list[tuple[str, UUID]]:
        del cursor, limit
        self.search_visible = visible_entity_ids_by_type
        return [
            (entity_type, entity_id)
            for (entity_type, entity_id, row_tag) in self.rows
            if row_tag == tag and entity_id in visible_entity_ids_by_type.get(entity_type, set())
        ]

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


class FailingAuditStub:
    async def append(
        self,
        audit_event_id: UUID | None,
        audit_event_source: str,
        canonical_payload: bytes,
    ) -> None:
        del audit_event_id, audit_event_source, canonical_payload
        raise RuntimeError("audit chain unavailable")


class ResolverStub:
    def __init__(self, visible: dict[str, set[UUID]]) -> None:
        self.visible = visible

    async def resolve_visible_entity_ids(
        self,
        requester: object,
        entity_types: list[str] | None = None,
    ) -> dict[str, set[UUID]]:
        del requester
        if entity_types is None:
            return self.visible
        return {entity_type: self.visible.get(entity_type, set()) for entity_type in entity_types}


@pytest.mark.asyncio
async def test_attach_is_idempotent_and_audits_only_the_insert() -> None:
    repo = RepoStub()
    audit = AuditStub()
    service = TagService(repo, audit_chain=audit)
    entity_id = uuid4()
    actor_id = uuid4()

    first = await service.attach(
        entity_type="agent",
        entity_id=entity_id,
        tag="production",
        requester={"sub": str(actor_id)},
    )
    second = await service.attach(
        entity_type="agent",
        entity_id=entity_id,
        tag="production",
        requester={"sub": str(actor_id)},
    )

    assert first.tag == "production"
    assert second.tag == "production"
    assert await repo.count_tags_for_entity("agent", entity_id) == 1
    assert len(audit.entries) == 1
    assert audit.entries[0][1] == "common_tagging"


@pytest.mark.asyncio
async def test_attach_rejects_invalid_tag_and_limit_excess() -> None:
    repo = RepoStub()
    entity_id = uuid4()
    service = TagService(repo, max_tags_per_entity=1)

    with pytest.raises(InvalidTagError):
        await service.attach(
            entity_type="agent",
            entity_id=entity_id,
            tag="invalid tag",
            requester={"sub": str(uuid4())},
        )

    await service.attach(
        entity_type="agent",
        entity_id=entity_id,
        tag="one",
        requester={"sub": str(uuid4())},
    )
    with pytest.raises(TagAttachLimitExceededError):
        await service.attach(
            entity_type="agent",
            entity_id=entity_id,
            tag="two",
            requester={"sub": str(uuid4())},
        )


@pytest.mark.asyncio
async def test_cross_entity_search_passes_visible_ids_to_repository() -> None:
    visible_agent = uuid4()
    hidden_agent = uuid4()
    visible_fleet = uuid4()
    repo = RepoStub()
    await repo.insert_tag("agent", visible_agent, "production", uuid4())
    await repo.insert_tag("agent", hidden_agent, "production", uuid4())
    await repo.insert_tag("fleet", visible_fleet, "production", uuid4())
    service = TagService(
        repo,
        visibility_resolver=ResolverStub(
            {"agent": {visible_agent}, "fleet": {visible_fleet}},
        ),
    )

    result = await service.cross_entity_search(
        tag="production",
        requester={"sub": str(uuid4())},
        entity_types=["agent", "fleet"],
    )

    assert result.entities == {"agent": [visible_agent], "fleet": [visible_fleet]}
    assert repo.search_visible == {"agent": {visible_agent}, "fleet": {visible_fleet}}


@pytest.mark.asyncio
async def test_detach_and_cascade() -> None:
    repo = RepoStub()
    audit = AuditStub()
    service = TagService(repo, audit_chain=audit)
    entity_id = uuid4()
    await service.attach(
        entity_type="workspace",
        entity_id=entity_id,
        tag="production",
        requester={"sub": str(uuid4())},
    )

    await service.detach(
        entity_type="workspace",
        entity_id=entity_id,
        tag="production",
        requester={"sub": str(uuid4())},
    )
    await service.cascade_on_entity_deletion("workspace", entity_id)

    assert await repo.count_tags_for_entity("workspace", entity_id) == 0
    assert repo.cascaded == [("workspace", entity_id)]
    assert len(audit.entries) == 2


@pytest.mark.asyncio
async def test_audit_failures_propagate_for_tag_mutations() -> None:
    repo = RepoStub()
    service = TagService(repo, audit_chain=FailingAuditStub())

    with pytest.raises(RuntimeError, match="audit chain unavailable"):
        await service.attach(
            entity_type="agent",
            entity_id=uuid4(),
            tag="production",
            requester={"sub": str(uuid4())},
        )


@pytest.mark.asyncio
async def test_list_access_denial_and_paginated_search_paths() -> None:
    allowed_entity = uuid4()
    second_entity = uuid4()
    actor_id = uuid4()
    repo = RepoStub()
    await repo.insert_tag("agent", allowed_entity, "production", actor_id)
    await repo.insert_tag("agent", second_entity, "production", actor_id)

    async def allow_only_agent(
        entity_type: str,
        entity_id: UUID,
        requester: object,
        action: str,
    ) -> bool:
        del requester, action
        return entity_type == "agent" and entity_id == allowed_entity

    service = TagService(
        repo,
        visibility_resolver=ResolverStub({"agent": {allowed_entity, second_entity}}),
        entity_access_check=allow_only_agent,
    )

    tags = await service.list_for_entity(
        "agent",
        allowed_entity,
        requester=SimpleNamespace(id=actor_id),
    )
    search = await service.cross_entity_search(
        tag="production",
        requester={"sub": str(actor_id)},
        entity_types=["agent"],
        cursor="5",
        limit=1,
    )

    assert [tag.tag for tag in tags] == ["production"]
    assert search.entities == {"agent": [allowed_entity]}
    assert search.next_cursor == "6"

    with pytest.raises(EntityNotFoundForTagError):
        await service.attach(
            entity_type="agent",
            entity_id=second_entity,
            tag="blocked",
            requester={"sub": str(actor_id)},
        )
    with pytest.raises(EntityTypeNotRegisteredError):
        await service.list_for_entity("unknown", allowed_entity, requester={"sub": str(actor_id)})
