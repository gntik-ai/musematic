from __future__ import annotations

from collections.abc import Iterable
from platform.common.tagging.models import EntityLabel, EntityTag, SavedView
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession


class TaggingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_tag(self, entity_type: str, entity_id: UUID, tag: str) -> EntityTag | None:
        result = await self.session.execute(
            select(EntityTag).where(
                EntityTag.entity_type == entity_type,
                EntityTag.entity_id == entity_id,
                EntityTag.tag == tag,
            )
        )
        return result.scalar_one_or_none()

    async def insert_tag(
        self,
        entity_type: str,
        entity_id: UUID,
        tag: str,
        created_by: UUID | None,
    ) -> EntityTag:
        statement = (
            insert(EntityTag)
            .values(
                entity_type=entity_type,
                entity_id=entity_id,
                tag=tag,
                created_by=created_by,
            )
            .on_conflict_do_nothing(
                index_elements=["entity_type", "entity_id", "tag"],
            )
            .returning(EntityTag)
        )
        result = await self.session.execute(statement)
        inserted = result.scalar_one_or_none()
        if inserted is not None:
            await self.session.flush()
            return inserted
        existing = await self.get_tag(entity_type, entity_id, tag)
        if existing is None:  # pragma: no cover - defensive consistency guard
            raise RuntimeError("entity tag insert conflicted but existing row was not found")
        return existing

    async def delete_tag(self, entity_type: str, entity_id: UUID, tag: str) -> bool:
        result = await self.session.execute(
            delete(EntityTag).where(
                EntityTag.entity_type == entity_type,
                EntityTag.entity_id == entity_id,
                EntityTag.tag == tag,
            )
        )
        await self.session.flush()
        return bool(getattr(result, "rowcount", 0))

    async def list_tags_for_entity(self, entity_type: str, entity_id: UUID) -> list[EntityTag]:
        result = await self.session.execute(
            select(EntityTag)
            .where(EntityTag.entity_type == entity_type, EntityTag.entity_id == entity_id)
            .order_by(EntityTag.tag.asc(), EntityTag.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_entities_by_tag(
        self,
        tag: str,
        visible_entity_ids_by_type: dict[str, set[UUID]],
        *,
        cursor: str | None,
        limit: int,
    ) -> list[tuple[str, UUID]]:
        clauses = []
        for entity_type, entity_ids in visible_entity_ids_by_type.items():
            if entity_ids:
                clauses.append(
                    (EntityTag.entity_type == entity_type)
                    & (EntityTag.entity_id.in_(sorted(entity_ids, key=str)))
                )
        if not clauses:
            return []
        offset = int(cursor or 0)
        result = await self.session.execute(
            select(EntityTag.entity_type, EntityTag.entity_id)
            .where(EntityTag.tag == tag, or_(*clauses))
            .order_by(EntityTag.entity_type.asc(), EntityTag.entity_id.asc())
            .offset(offset)
            .limit(limit)
        )
        return [(str(entity_type), UUID(str(entity_id))) for entity_type, entity_id in result.all()]

    async def count_tags_for_entity(self, entity_type: str, entity_id: UUID) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(EntityTag)
            .where(EntityTag.entity_type == entity_type, EntityTag.entity_id == entity_id)
        )
        return int(total or 0)

    async def upsert_label(
        self,
        entity_type: str,
        entity_id: UUID,
        key: str,
        value: str,
        updated_by: UUID | None,
    ) -> tuple[EntityLabel, str | None]:
        existing = await self.get_label(entity_type, entity_id, key)
        old_value = existing.label_value if existing is not None else None
        statement = (
            insert(EntityLabel)
            .values(
                entity_type=entity_type,
                entity_id=entity_id,
                label_key=key,
                label_value=value,
                created_by=updated_by,
            )
            .on_conflict_do_update(
                index_elements=["entity_type", "entity_id", "label_key"],
                set_={"label_value": value, "updated_at": func.now()},
            )
            .returning(EntityLabel)
        )
        result = await self.session.execute(statement)
        row = result.scalar_one()
        await self.session.flush()
        return row, old_value

    async def get_label(
        self,
        entity_type: str,
        entity_id: UUID,
        key: str,
    ) -> EntityLabel | None:
        result = await self.session.execute(
            select(EntityLabel).where(
                EntityLabel.entity_type == entity_type,
                EntityLabel.entity_id == entity_id,
                EntityLabel.label_key == key,
            )
        )
        return result.scalar_one_or_none()

    async def delete_label(self, entity_type: str, entity_id: UUID, key: str) -> bool:
        result = await self.session.execute(
            delete(EntityLabel).where(
                EntityLabel.entity_type == entity_type,
                EntityLabel.entity_id == entity_id,
                EntityLabel.label_key == key,
            )
        )
        await self.session.flush()
        return bool(getattr(result, "rowcount", 0))

    async def list_labels_for_entity(self, entity_type: str, entity_id: UUID) -> list[EntityLabel]:
        result = await self.session.execute(
            select(EntityLabel)
            .where(EntityLabel.entity_type == entity_type, EntityLabel.entity_id == entity_id)
            .order_by(EntityLabel.label_key.asc())
        )
        return list(result.scalars().all())

    async def filter_entities_by_labels(
        self,
        entity_type: str,
        label_filters: dict[str, str],
        visible_entity_ids: set[UUID],
        *,
        cursor: str | None,
        limit: int,
    ) -> list[UUID]:
        if not label_filters or not visible_entity_ids:
            return []
        offset = int(cursor or 0)
        result = await self.session.execute(
            select(EntityLabel.entity_id)
            .where(
                EntityLabel.entity_type == entity_type,
                EntityLabel.entity_id.in_(_sorted_uuids(visible_entity_ids)),
            )
            .where(
                tuple_(EntityLabel.label_key, EntityLabel.label_value).in_(
                    sorted(label_filters.items())
                )
            )
            .group_by(EntityLabel.entity_id)
            .having(func.count(func.distinct(EntityLabel.label_key)) == len(label_filters))
            .order_by(EntityLabel.entity_id.asc())
            .offset(offset)
            .limit(limit)
        )
        return [UUID(str(entity_id)) for entity_id in result.scalars().all()]

    async def count_labels_for_entity(self, entity_type: str, entity_id: UUID) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(EntityLabel)
            .where(EntityLabel.entity_type == entity_type, EntityLabel.entity_id == entity_id)
        )
        return int(total or 0)

    async def cascade_on_entity_deletion(self, entity_type: str, entity_id: UUID) -> None:
        await self.session.execute(
            delete(EntityTag).where(
                EntityTag.entity_type == entity_type,
                EntityTag.entity_id == entity_id,
            )
        )
        await self.session.execute(
            delete(EntityLabel).where(
                EntityLabel.entity_type == entity_type,
                EntityLabel.entity_id == entity_id,
            )
        )
        await self.session.flush()

    async def insert_saved_view(
        self,
        *,
        owner_id: UUID,
        workspace_id: UUID | None,
        name: str,
        entity_type: str,
        filters: dict[str, Any],
        shared: bool,
    ) -> SavedView:
        view = SavedView(
            owner_id=owner_id,
            workspace_id=workspace_id,
            name=name,
            entity_type=entity_type,
            filters=filters,
            shared=shared,
        )
        self.session.add(view)
        await self.session.flush()
        return view

    async def get_saved_view(self, view_id: UUID) -> SavedView | None:
        result = await self.session.execute(select(SavedView).where(SavedView.id == view_id))
        return result.scalar_one_or_none()

    async def list_personal_views(
        self,
        owner_id: UUID,
        entity_type: str,
        workspace_id: UUID | None = None,
    ) -> list[SavedView]:
        query = select(SavedView).where(
            SavedView.owner_id == owner_id,
            SavedView.entity_type == entity_type,
        )
        if workspace_id is not None:
            query = query.where(SavedView.workspace_id == workspace_id)
        result = await self.session.execute(
            query.order_by(SavedView.name.asc(), SavedView.id.asc())
        )
        return list(result.scalars().all())

    async def list_shared_views(self, workspace_id: UUID, entity_type: str) -> list[SavedView]:
        result = await self.session.execute(
            select(SavedView)
            .where(
                SavedView.workspace_id == workspace_id,
                SavedView.entity_type == entity_type,
                SavedView.shared.is_(True),
            )
            .order_by(SavedView.name.asc(), SavedView.id.asc())
        )
        return list(result.scalars().all())

    async def update_saved_view(
        self,
        view_id: UUID,
        expected_version: int,
        **fields: Any,
    ) -> SavedView | None:
        values = {key: value for key, value in fields.items() if value is not None}
        if values:
            values["version"] = SavedView.version + 1
            values["updated_at"] = func.now()
        result = await self.session.execute(
            update(SavedView)
            .where(SavedView.id == view_id, SavedView.version == expected_version)
            .values(**values)
            .returning(SavedView)
        )
        await self.session.flush()
        return result.scalar_one_or_none()

    async def delete_saved_view(self, view_id: UUID) -> bool:
        result = await self.session.execute(delete(SavedView).where(SavedView.id == view_id))
        await self.session.flush()
        return bool(getattr(result, "rowcount", 0))

    async def transfer_saved_view_ownership(self, view_id: UUID, new_owner_id: UUID) -> None:
        await self.session.execute(
            update(SavedView)
            .where(SavedView.id == view_id)
            .values(owner_id=new_owner_id, is_orphan_transferred=True, updated_at=func.now())
        )
        await self.session.flush()

    async def list_views_owned_by_user_in_workspace(
        self,
        owner_id: UUID,
        workspace_id: UUID,
    ) -> list[SavedView]:
        result = await self.session.execute(
            select(SavedView)
            .where(SavedView.owner_id == owner_id, SavedView.workspace_id == workspace_id)
            .order_by(SavedView.created_at.asc(), SavedView.id.asc())
        )
        return list(result.scalars().all())


def _sorted_uuids(values: Iterable[UUID]) -> list[UUID]:
    return sorted(values, key=str)
