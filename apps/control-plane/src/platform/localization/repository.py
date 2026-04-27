from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from platform.localization.exceptions import LocaleFileVersionConflictError
from platform.localization.models import LocaleFile, UserPreferences
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


class LocalizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user_preferences(self, user_id: UUID) -> UserPreferences | None:
        result = await self.session.execute(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert_user_preferences(self, user_id: UUID, **fields: Any) -> UserPreferences:
        values = {"user_id": user_id, **fields}
        statement = insert(UserPreferences).values(**values)
        update_values = {
            field: getattr(statement.excluded, field)
            for field in fields
            if hasattr(statement.excluded, field)
        }
        update_values["updated_at"] = func.now()
        result = await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[UserPreferences.user_id],
                set_=update_values,
            ).returning(UserPreferences)
        )
        return result.scalar_one()

    async def clear_default_workspace(self, workspace_id: UUID) -> list[UserPreferences]:
        result = await self.session.execute(
            update(UserPreferences)
            .where(UserPreferences.default_workspace_id == workspace_id)
            .values(default_workspace_id=None, updated_at=func.now())
            .returning(UserPreferences)
        )
        return list(result.scalars().all())

    async def get_latest_locale_file(self, locale_code: str) -> LocaleFile | None:
        result = await self.session.execute(
            select(LocaleFile)
            .where(LocaleFile.locale_code == locale_code, LocaleFile.published_at.is_not(None))
            .order_by(desc(LocaleFile.version))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_locale_files(self, locale_code: str | None = None) -> list[LocaleFile]:
        statement = select(LocaleFile)
        if locale_code is not None:
            statement = statement.where(LocaleFile.locale_code == locale_code)
        result = await self.session.execute(
            statement.order_by(LocaleFile.locale_code, desc(LocaleFile.version))
        )
        return list(result.scalars().all())

    async def insert_locale_file_version(
        self,
        *,
        locale_code: str,
        translations: dict[str, Any],
        published_by: UUID | None,
        vendor_source_ref: str | None,
    ) -> LocaleFile:
        try:
            latest_result = await self.session.execute(
                select(LocaleFile)
                .where(LocaleFile.locale_code == locale_code)
                .order_by(desc(LocaleFile.version))
                .limit(1)
                .with_for_update()
            )
            latest = latest_result.scalar_one_or_none()
            version = 1 if latest is None else latest.version + 1
            row = LocaleFile(
                locale_code=locale_code,
                version=version,
                translations=translations,
                published_at=datetime.now(UTC),
                published_by=published_by,
                vendor_source_ref=vendor_source_ref,
            )
            self.session.add(row)
            await self.session.flush()
            await self.session.refresh(row)
            return row
        except IntegrityError as exc:
            raise LocaleFileVersionConflictError(locale_code) from exc

    async def get_namespace_publish_timestamps_per_locale(
        self,
    ) -> dict[str, dict[str, datetime]]:
        result = await self.session.execute(
            select(LocaleFile)
            .where(LocaleFile.published_at.is_not(None))
            .order_by(desc(LocaleFile.published_at), desc(LocaleFile.version))
        )
        timestamps: dict[str, dict[str, datetime]] = defaultdict(dict)
        for row in result.scalars().all():
            if row.published_at is None:
                continue
            for namespace in row.translations:
                timestamps[row.locale_code].setdefault(namespace, row.published_at)
        return {locale: dict(namespaces) for locale, namespaces in timestamps.items()}

