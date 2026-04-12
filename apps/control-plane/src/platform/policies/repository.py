from __future__ import annotations

import re
from datetime import UTC, datetime
from platform.policies.models import (
    AttachmentTargetType,
    PolicyAttachment,
    PolicyBlockedActionRecord,
    PolicyBundleCache,
    PolicyPolicy,
    PolicyStatus,
    PolicyVersion,
)
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

_WILDCARD_PATTERN = re.compile(r"^[A-Za-z0-9:_*.-]+$")


class PolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, policy: PolicyPolicy) -> PolicyPolicy:
        self.session.add(policy)
        await self.session.flush()
        return policy

    async def create_version(self, version: PolicyVersion) -> PolicyVersion:
        self.session.add(version)
        await self.session.flush()
        return version

    async def get_by_id(self, policy_id: UUID) -> PolicyPolicy | None:
        result = await self.session.execute(
            self._policy_query().where(PolicyPolicy.id == policy_id)
        )
        return result.scalar_one_or_none()

    async def list_with_filters(
        self,
        *,
        scope_type: Any | None,
        status: PolicyStatus | None,
        workspace_id: UUID | None,
        offset: int,
        limit: int,
    ) -> tuple[list[PolicyPolicy], int]:
        filters = []
        if scope_type is not None:
            filters.append(PolicyPolicy.scope_type == scope_type)
        if status is not None:
            filters.append(PolicyPolicy.status == status)
        if workspace_id is not None:
            filters.append(PolicyPolicy.workspace_id == workspace_id)
        total = await self.session.scalar(
            select(func.count()).select_from(PolicyPolicy).where(*filters)
        )
        result = await self.session.execute(
            self._policy_query()
            .where(*filters)
            .order_by(PolicyPolicy.created_at.desc(), PolicyPolicy.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def get_versions(self, policy_id: UUID) -> list[PolicyVersion]:
        result = await self.session.execute(
            select(PolicyVersion)
            .where(PolicyVersion.policy_id == policy_id)
            .order_by(PolicyVersion.version_number.asc(), PolicyVersion.id.asc())
        )
        return list(result.scalars().all())

    async def get_version_by_number(
        self,
        policy_id: UUID,
        version_number: int,
    ) -> PolicyVersion | None:
        result = await self.session.execute(
            select(PolicyVersion).where(
                PolicyVersion.policy_id == policy_id,
                PolicyVersion.version_number == version_number,
            )
        )
        return result.scalar_one_or_none()

    async def get_policy_version(self, version_id: UUID) -> PolicyVersion | None:
        result = await self.session.execute(
            select(PolicyVersion).where(PolicyVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    async def create_attachment(self, attachment: PolicyAttachment) -> PolicyAttachment:
        self.session.add(attachment)
        await self.session.flush()
        return attachment

    async def get_attachment(
        self, attachment_id: UUID, policy_id: UUID | None = None
    ) -> PolicyAttachment | None:
        query = (
            select(PolicyAttachment)
            .options(
                selectinload(PolicyAttachment.policy),
                selectinload(PolicyAttachment.policy_version),
            )
            .where(PolicyAttachment.id == attachment_id)
        )
        if policy_id is not None:
            query = query.where(PolicyAttachment.policy_id == policy_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def find_active_attachment(
        self,
        *,
        policy_id: UUID,
        target_type: AttachmentTargetType,
        target_id: str | None,
    ) -> PolicyAttachment | None:
        result = await self.session.execute(
            select(PolicyAttachment).where(
                PolicyAttachment.policy_id == policy_id,
                PolicyAttachment.target_type == target_type,
                PolicyAttachment.target_id == target_id,
                PolicyAttachment.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list_attachments(self, policy_id: UUID) -> list[PolicyAttachment]:
        result = await self.session.execute(
            select(PolicyAttachment)
            .options(selectinload(PolicyAttachment.policy_version))
            .where(
                PolicyAttachment.policy_id == policy_id,
                PolicyAttachment.is_active.is_(True),
            )
            .order_by(PolicyAttachment.created_at.asc(), PolicyAttachment.id.asc())
        )
        return list(result.scalars().all())

    async def deactivate_attachment(self, attachment: PolicyAttachment) -> None:
        attachment.is_active = False
        attachment.deactivated_at = datetime.now(UTC)
        await self.session.flush()

    async def deactivate_attachments_for_policy(self, policy_id: UUID) -> None:
        attachments = await self.list_attachments(policy_id)
        for attachment in attachments:
            attachment.is_active = False
            attachment.deactivated_at = datetime.now(UTC)
        await self.session.flush()

    async def get_all_applicable_attachments(
        self,
        *,
        workspace_id: UUID,
        agent_revision_id: str | None = None,
        deployment_id: str | None = None,
        execution_id: str | None = None,
    ) -> list[PolicyAttachment]:
        predicates = [
            (
                PolicyAttachment.target_type == AttachmentTargetType.global_scope,
                PolicyAttachment.target_id.is_(None),
            ),
            (
                PolicyAttachment.target_type == AttachmentTargetType.workspace,
                PolicyAttachment.target_id == str(workspace_id),
            ),
        ]
        if deployment_id:
            predicates.append(
                (
                    PolicyAttachment.target_type == AttachmentTargetType.deployment,
                    PolicyAttachment.target_id == deployment_id,
                )
            )
        if agent_revision_id:
            predicates.append(
                (
                    PolicyAttachment.target_type == AttachmentTargetType.agent_revision,
                    PolicyAttachment.target_id == agent_revision_id,
                )
            )
        if execution_id:
            predicates.append(
                (
                    PolicyAttachment.target_type == AttachmentTargetType.execution,
                    PolicyAttachment.target_id == execution_id,
                )
            )
        filters = [
            PolicyAttachment.is_active.is_(True),
            PolicyPolicy.status == PolicyStatus.active,
            or_(*[and_clause[0] & and_clause[1] for and_clause in predicates]),
        ]
        result = await self.session.execute(
            select(PolicyAttachment)
            .join(PolicyPolicy, PolicyPolicy.id == PolicyAttachment.policy_id)
            .options(
                selectinload(PolicyAttachment.policy),
                selectinload(PolicyAttachment.policy_version),
            )
            .where(*filters)
            .order_by(PolicyAttachment.created_at.asc(), PolicyAttachment.id.asc())
        )
        return list(result.scalars().all())

    async def create_blocked_action_record(
        self,
        record: PolicyBlockedActionRecord,
    ) -> PolicyBlockedActionRecord:
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_blocked_action_records(
        self,
        *,
        agent_id: UUID | None = None,
        enforcement_component: Any | None = None,
        workspace_id: UUID | None = None,
        execution_id: UUID | None = None,
        since: datetime | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[PolicyBlockedActionRecord], int]:
        filters = []
        if agent_id is not None:
            filters.append(PolicyBlockedActionRecord.agent_id == agent_id)
        if enforcement_component is not None:
            filters.append(PolicyBlockedActionRecord.enforcement_component == enforcement_component)
        if workspace_id is not None:
            filters.append(PolicyBlockedActionRecord.workspace_id == workspace_id)
        if execution_id is not None:
            filters.append(PolicyBlockedActionRecord.execution_id == execution_id)
        if since is not None:
            filters.append(PolicyBlockedActionRecord.created_at >= since)
        total = await self.session.scalar(
            select(func.count()).select_from(PolicyBlockedActionRecord).where(*filters)
        )
        result = await self.session.execute(
            select(PolicyBlockedActionRecord)
            .where(*filters)
            .order_by(
                PolicyBlockedActionRecord.created_at.desc(), PolicyBlockedActionRecord.id.desc()
            )
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def get_blocked_action_record(self, record_id: UUID) -> PolicyBlockedActionRecord | None:
        result = await self.session.execute(
            select(PolicyBlockedActionRecord).where(PolicyBlockedActionRecord.id == record_id)
        )
        return result.scalar_one_or_none()

    async def get_bundle_cache(self, fingerprint: str) -> PolicyBundleCache | None:
        result = await self.session.execute(
            select(PolicyBundleCache).where(
                PolicyBundleCache.fingerprint == fingerprint,
                PolicyBundleCache.expires_at > datetime.now(UTC),
            )
        )
        return result.scalar_one_or_none()

    async def upsert_bundle_cache(self, cache: PolicyBundleCache) -> PolicyBundleCache:
        existing = await self.get_bundle_cache(cache.fingerprint)
        if existing is None:
            self.session.add(cache)
            await self.session.flush()
            return cache
        existing.bundle_data = cache.bundle_data
        existing.source_version_ids = cache.source_version_ids
        existing.expires_at = cache.expires_at
        await self.session.flush()
        return existing

    def _policy_query(self) -> Any:
        return (
            select(PolicyPolicy)
            .options(selectinload(PolicyPolicy.current_version))
            .options(selectinload(PolicyPolicy.versions))
        )
