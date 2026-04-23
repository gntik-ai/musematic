from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from platform.common.clients.opensearch import AsyncOpenSearchClient
from platform.registry.exceptions import DecommissionImmutableError
from platform.registry.models import (
    AgentMaturityRecord,
    AgentNamespace,
    AgentProfile,
    AgentRevision,
    AssessmentMethod,
    EmbeddingStatus,
    LifecycleAuditEntry,
    LifecycleStatus,
)
from typing import Any
from uuid import UUID

from sqlalchemy import false, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

_WILDCARD_PATTERN = re.compile(r"^[A-Za-z0-9:_*.-]+$")


class RegistryRepository:
    def __init__(
        self,
        session: AsyncSession,
        opensearch: AsyncOpenSearchClient | None = None,
    ) -> None:
        self.session = session
        self.opensearch = opensearch

    async def create_namespace(
        self,
        *,
        workspace_id: UUID,
        name: str,
        description: str | None,
        created_by: UUID,
    ) -> AgentNamespace:
        namespace = AgentNamespace(
            workspace_id=workspace_id,
            name=name,
            description=description,
            created_by=created_by,
        )
        self.session.add(namespace)
        await self.session.flush()
        return namespace

    async def get_namespace_by_name(self, workspace_id: UUID, name: str) -> AgentNamespace | None:
        result = await self.session.execute(
            select(AgentNamespace).where(
                AgentNamespace.workspace_id == workspace_id,
                AgentNamespace.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def get_namespace_by_id(
        self,
        workspace_id: UUID,
        namespace_id: UUID,
    ) -> AgentNamespace | None:
        result = await self.session.execute(
            select(AgentNamespace).where(
                AgentNamespace.workspace_id == workspace_id,
                AgentNamespace.id == namespace_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_namespaces(self, workspace_id: UUID) -> list[AgentNamespace]:
        result = await self.session.execute(
            select(AgentNamespace)
            .where(AgentNamespace.workspace_id == workspace_id)
            .order_by(AgentNamespace.created_at.asc(), AgentNamespace.id.asc())
        )
        return list(result.scalars().all())

    async def delete_namespace(self, namespace: AgentNamespace) -> None:
        await self.session.delete(namespace)
        await self.session.flush()

    async def namespace_has_agents(self, namespace_id: UUID) -> bool:
        total = await self.session.scalar(
            select(func.count())
            .select_from(AgentProfile)
            .where(AgentProfile.namespace_id == namespace_id)
        )
        return bool(total)

    async def upsert_agent_profile(
        self,
        *,
        workspace_id: UUID,
        namespace: AgentNamespace,
        local_name: str,
        display_name: str | None,
        purpose: str,
        approach: str | None,
        role_types: list[str],
        custom_role_description: str | None,
        tags: list[str],
        mcp_server_refs: list[str] | None = None,
        maturity_level: int,
        actor_id: UUID,
    ) -> tuple[AgentProfile, bool]:
        fqn = f"{namespace.name}:{local_name}"
        resolved_mcp_server_refs = list(mcp_server_refs or [])
        existing = await self.get_agent_by_fqn(workspace_id, fqn)
        if existing is None:
            profile = AgentProfile(
                workspace_id=workspace_id,
                namespace_id=namespace.id,
                local_name=local_name,
                fqn=fqn,
                display_name=display_name,
                purpose=purpose,
                approach=approach,
                role_types=role_types,
                custom_role_description=custom_role_description,
                visibility_agents=[],
                visibility_tools=[],
                tags=tags,
                mcp_server_refs=resolved_mcp_server_refs,
                status=LifecycleStatus.draft,
                maturity_level=maturity_level,
                embedding_status=EmbeddingStatus.pending,
                needs_reindex=False,
                created_by=actor_id,
            )
            self.session.add(profile)
            await self.session.flush()
            return profile, True

        existing.display_name = display_name
        existing.purpose = purpose
        existing.approach = approach
        existing.role_types = role_types
        existing.custom_role_description = custom_role_description
        existing.tags = tags
        existing.mcp_server_refs = resolved_mcp_server_refs
        existing.maturity_level = maturity_level
        existing.embedding_status = EmbeddingStatus.pending
        await self.session.flush()
        return existing, False

    async def update_agent_profile(self, profile: AgentProfile, **fields: Any) -> AgentProfile:
        immutable_fields = [
            key
            for key in ("decommissioned_at", "decommission_reason", "decommissioned_by")
            if key in fields
            and getattr(profile, key) is not None
            and fields[key] != getattr(profile, key)
        ]
        if immutable_fields:
            raise DecommissionImmutableError(immutable_fields)
        for key, value in fields.items():
            setattr(profile, key, value)
        await self.session.flush()
        return profile

    async def get_agent_by_id(self, workspace_id: UUID, agent_id: UUID) -> AgentProfile | None:
        result = await self.session.execute(
            self._profile_query().where(
                AgentProfile.workspace_id == workspace_id,
                AgentProfile.id == agent_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_agent_by_id_any(self, agent_id: UUID) -> AgentProfile | None:
        result = await self.session.execute(
            self._profile_query().where(AgentProfile.id == agent_id)
        )
        return result.scalar_one_or_none()

    async def get_agent_by_fqn(
        self,
        workspace_id: UUID,
        fqn: str,
        *,
        include_decommissioned: bool = False,
    ) -> AgentProfile | None:
        filters = [
            AgentProfile.workspace_id == workspace_id,
            AgentProfile.fqn == fqn,
        ]
        if not include_decommissioned:
            filters.append(AgentProfile.status != LifecycleStatus.decommissioned)
        result = await self.session.execute(
            self._profile_query()
            .where(*filters)
            .order_by(AgentProfile.created_at.desc(), AgentProfile.id.desc())
        )
        return result.scalars().first()

    async def get_by_fqn(self, workspace_id: UUID, fqn: str) -> AgentProfile | None:
        return await self.get_agent_by_fqn(workspace_id, fqn, include_decommissioned=True)

    async def list_agents_by_workspace(
        self,
        workspace_id: UUID,
        *,
        status: LifecycleStatus | None,
        maturity_min: int,
        limit: int,
        offset: int,
        visibility_filter: Any | None = None,
        include_decommissioned: bool = False,
    ) -> tuple[list[AgentProfile], int]:
        filters = [
            AgentProfile.workspace_id == workspace_id,
            AgentProfile.maturity_level >= maturity_min,
            AgentProfile.status != LifecycleStatus.archived,
        ]
        if not include_decommissioned:
            filters.append(AgentProfile.status != LifecycleStatus.decommissioned)
        if status is not None:
            filters.append(AgentProfile.status == status)
        filters.append(self._visibility_predicate(visibility_filter))

        total = await self.session.scalar(
            select(func.count()).select_from(AgentProfile).where(*filters)
        )
        result = await self.session.execute(
            self._profile_query()
            .where(*filters)
            .order_by(AgentProfile.created_at.asc(), AgentProfile.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def get_agents_by_ids(
        self,
        workspace_id: UUID,
        agent_ids: Sequence[UUID],
        *,
        visibility_filter: Any | None = None,
    ) -> list[AgentProfile]:
        if not agent_ids:
            return []
        result = await self.session.execute(
            self._profile_query().where(
                AgentProfile.workspace_id == workspace_id,
                AgentProfile.id.in_(list(agent_ids)),
                self._visibility_predicate(visibility_filter),
            )
        )
        profiles = list(result.scalars().all())
        by_id = {profile.id: profile for profile in profiles}
        return [by_id[agent_id] for agent_id in agent_ids if agent_id in by_id]

    async def insert_revision(
        self,
        *,
        revision_id: UUID,
        workspace_id: UUID,
        agent_profile_id: UUID,
        version: str,
        sha256_digest: str,
        storage_key: str,
        manifest_snapshot: dict[str, Any],
        uploaded_by: UUID,
    ) -> AgentRevision:
        revision = AgentRevision(
            id=revision_id,
            workspace_id=workspace_id,
            agent_profile_id=agent_profile_id,
            version=version,
            sha256_digest=sha256_digest,
            storage_key=storage_key,
            manifest_snapshot=manifest_snapshot,
            uploaded_by=uploaded_by,
        )
        self.session.add(revision)
        await self.session.flush()
        return revision

    async def get_revision_by_id(self, revision_id: UUID) -> AgentRevision | None:
        result = await self.session.execute(
            select(AgentRevision).where(AgentRevision.id == revision_id)
        )
        return result.scalar_one_or_none()

    async def get_latest_revision(self, agent_profile_id: UUID) -> AgentRevision | None:
        result = await self.session.execute(
            select(AgentRevision)
            .where(AgentRevision.agent_profile_id == agent_profile_id)
            .order_by(AgentRevision.created_at.desc(), AgentRevision.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_revisions(self, agent_profile_id: UUID) -> list[AgentRevision]:
        result = await self.session.execute(
            select(AgentRevision)
            .where(AgentRevision.agent_profile_id == agent_profile_id)
            .order_by(AgentRevision.created_at.asc(), AgentRevision.id.asc())
        )
        return list(result.scalars().all())

    async def insert_maturity_record(
        self,
        *,
        workspace_id: UUID,
        agent_profile_id: UUID,
        previous_level: int,
        new_level: int,
        assessment_method: AssessmentMethod,
        reason: str | None,
        actor_id: UUID,
    ) -> AgentMaturityRecord:
        record = AgentMaturityRecord(
            workspace_id=workspace_id,
            agent_profile_id=agent_profile_id,
            previous_level=previous_level,
            new_level=new_level,
            assessment_method=assessment_method,
            reason=reason,
            actor_id=actor_id,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def persist_decommission(
        self,
        profile: AgentProfile,
        *,
        reason: str,
        actor_id: UUID,
    ) -> AgentProfile:
        if profile.status is LifecycleStatus.decommissioned:
            return profile
        profile.status = LifecycleStatus.decommissioned
        profile.decommissioned_at = datetime.now(UTC)
        profile.decommission_reason = reason
        profile.decommissioned_by = actor_id
        await self.session.flush()
        return profile

    async def insert_lifecycle_audit(
        self,
        *,
        workspace_id: UUID,
        agent_profile_id: UUID,
        previous_status: LifecycleStatus,
        new_status: LifecycleStatus,
        actor_id: UUID,
        reason: str | None,
    ) -> LifecycleAuditEntry:
        entry = LifecycleAuditEntry(
            workspace_id=workspace_id,
            agent_profile_id=agent_profile_id,
            previous_status=previous_status,
            new_status=new_status,
            actor_id=actor_id,
            reason=reason,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_lifecycle_audit(self, agent_profile_id: UUID) -> list[LifecycleAuditEntry]:
        result = await self.session.execute(
            select(LifecycleAuditEntry)
            .where(LifecycleAuditEntry.agent_profile_id == agent_profile_id)
            .order_by(LifecycleAuditEntry.created_at.asc(), LifecycleAuditEntry.id.asc())
        )
        return list(result.scalars().all())

    async def get_agents_needing_reindex(self, limit: int = 100) -> list[AgentProfile]:
        result = await self.session.execute(
            self._profile_query()
            .where(AgentProfile.needs_reindex.is_(True))
            .order_by(AgentProfile.updated_at.asc(), AgentProfile.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def set_needs_reindex(self, agent_profile_id: UUID, needs_reindex: bool) -> None:
        profile = await self.session.get(AgentProfile, agent_profile_id)
        if profile is None:
            return
        profile.needs_reindex = needs_reindex
        await self.session.flush()

    async def set_embedding_status(
        self,
        agent_profile_id: UUID,
        status: EmbeddingStatus,
    ) -> None:
        profile = await self.session.get(AgentProfile, agent_profile_id)
        if profile is None:
            return
        profile.embedding_status = status
        await self.session.flush()

    async def search_by_keyword(
        self,
        *,
        workspace_id: UUID,
        keyword: str,
        status: LifecycleStatus | None,
        maturity_min: int,
        limit: int,
        offset: int,
        index_name: str,
    ) -> tuple[list[UUID], int]:
        if self.opensearch is None:
            return [], 0
        raw_client = await self.opensearch._ensure_client()
        filters: list[dict[str, Any]] = [{"term": {"workspace_id": str(workspace_id)}}]
        if status is not None:
            filters.append({"term": {"status": status.value}})
        else:
            filters.append(
                {"bool": {"must_not": [{"terms": {"status": ["archived", "decommissioned"]}}]}}
            )
        filters.append({"range": {"maturity_level": {"gte": maturity_min}}})
        response = await raw_client.search(
            index=index_name,
            body={
                "from": offset,
                "size": limit,
                "query": {
                    "bool": {
                        "must": [
                            {
                                "multi_match": {
                                    "query": keyword,
                                    "fields": [
                                        "display_name^3",
                                        "purpose^2",
                                        "approach",
                                        "tags",
                                    ],
                                }
                            }
                        ],
                        "filter": filters,
                    }
                },
            },
        )
        hits = response.get("hits", {}).get("hits", [])
        total_value = response.get("hits", {}).get("total", {}).get("value", len(hits))
        ids: list[UUID] = []
        for hit in hits:
            source = hit.get("_source", {})
            candidate = source.get("agent_profile_id") or hit.get("_id")
            if not isinstance(candidate, str):
                continue
            try:
                ids.append(UUID(candidate))
            except ValueError:
                continue
        return ids, int(total_value)

    def _profile_query(self) -> Select[tuple[AgentProfile]]:
        return select(AgentProfile).options(selectinload(AgentProfile.namespace))

    def _visibility_predicate(self, visibility_filter: Any | None) -> Any:
        patterns = list(getattr(visibility_filter, "agent_patterns", []) or [])
        if visibility_filter is None:
            return true()
        if not patterns:
            return false()

        predicates: list[Any] = []
        for pattern in patterns:
            normalized = str(pattern).strip()
            if not normalized:
                continue
            if "*" not in normalized and _WILDCARD_PATTERN.fullmatch(normalized):
                predicates.append(AgentProfile.fqn == normalized)
                continue
            if _WILDCARD_PATTERN.fullmatch(normalized):
                predicates.append(AgentProfile.fqn.like(normalized.replace("*", "%")))
                continue
            predicates.append(AgentProfile.fqn.op("~")(normalized))

        if not predicates:
            return false()
        return or_(*predicates)
