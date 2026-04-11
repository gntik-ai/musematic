from __future__ import annotations

import time
from datetime import UTC, datetime
from difflib import SequenceMatcher
from platform.common.events.envelope import CorrelationContext
from platform.memory.events import (
    ConsolidationCompletedPayload,
    publish_consolidation_completed,
)
from platform.memory.models import MemoryScope, RetentionPolicy
from platform.memory.repository import MemoryRepository
from platform.memory.schemas import MemoryWriteRequest
from platform.memory.write_gate import MemoryWriteGate
from typing import Any
from uuid import UUID, uuid4

import httpx


class ConsolidationWorker:
    def __init__(
        self,
        *,
        repository: MemoryRepository,
        write_gate: MemoryWriteGate,
        settings: Any,
        producer: Any | None,
    ) -> None:
        self.repository = repository
        self.write_gate = write_gate
        self.settings = settings
        self.producer = producer

    async def run(self) -> None:
        started = time.perf_counter()
        consolidated = 0
        promoted = 0
        last_workspace_id: UUID | None = None
        for workspace_id in await self.repository.list_workspace_ids_with_agent_memories():
            last_workspace_id = workspace_id
            clusters = await self._find_consolidation_candidates(workspace_id)
            for cluster in clusters:
                content = await self._distill(cluster, workspace_id)
                if not content:
                    continue
                await self._promote(content, cluster, workspace_id)
                consolidated += len(cluster)
                promoted += 1
        if hasattr(self.repository.session, "commit"):
            await self.repository.session.commit()
        await publish_consolidation_completed(
            self.producer,
            ConsolidationCompletedPayload(
                workspace_id=last_workspace_id or uuid4(),
                entries_consolidated=consolidated,
                entries_promoted=promoted,
                duration_seconds=time.perf_counter() - started,
                run_at=datetime_now_utc(),
            ),
            CorrelationContext(
                correlation_id=uuid4(),
                workspace_id=last_workspace_id,
            ),
        )

    async def _find_consolidation_candidates(self, workspace_id: UUID) -> list[list[UUID]]:
        entries = await self.repository.get_consolidation_candidates(workspace_id)
        threshold = self.settings.memory.consolidation_cluster_threshold
        min_size = self.settings.memory.consolidation_min_cluster_size
        clusters: list[list[UUID]] = []
        visited: set[UUID] = set()
        for entry in entries:
            if entry.id in visited:
                continue
            cluster = [entry.id]
            visited.add(entry.id)
            for candidate in entries:
                if candidate.id in visited:
                    continue
                similarity = SequenceMatcher(a=entry.content, b=candidate.content).ratio()
                if similarity >= threshold:
                    cluster.append(candidate.id)
                    visited.add(candidate.id)
            if len(cluster) >= min_size:
                clusters.append(cluster)
        return clusters

    async def _distill(self, memory_ids: list[UUID], workspace_id: UUID) -> str:
        entries = await self.repository.get_memory_entries_by_ids(workspace_id, memory_ids)
        if not entries:
            return ""
        if self.settings.memory.consolidation_llm_enabled:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    self.settings.memory.embedding_api_url,
                    json={
                        "input": "\n\n".join(entry.content for entry in entries),
                        "task": "summarize",
                    },
                )
                response.raise_for_status()
                payload = response.json()
            summary = payload.get("summary")
            if isinstance(summary, str):
                return summary
        best = max(entries, key=lambda item: (item.source_authority, item.created_at))
        return best.content

    async def _promote(
        self,
        content: str,
        source_ids: list[UUID],
        workspace_id: UUID,
    ) -> None:
        source_entries = await self.repository.get_memory_entries_by_ids(workspace_id, source_ids)
        if not source_entries:
            return
        champion = max(source_entries, key=lambda item: (item.source_authority, item.created_at))
        result = await self.write_gate.validate_and_write(
            MemoryWriteRequest(
                content=content,
                scope=MemoryScope.per_workspace,
                namespace=champion.namespace,
                source_authority=champion.source_authority,
                retention_policy=RetentionPolicy.permanent,
                tags=list(champion.tags),
            ),
            champion.agent_fqn,
            workspace_id,
        )
        await self.repository.bulk_link_consolidated_entries(
            source_ids=source_ids,
            consolidated_id=result.memory_entry_id,
        )


class SessionMemoryCleaner:
    def __init__(self, *, repository: MemoryRepository, qdrant: Any) -> None:
        self.repository = repository
        self.qdrant = qdrant

    async def run(self) -> None:
        expired = await self.repository.get_session_only_expired()
        for entry in expired:
            await self.repository.soft_delete_memory_entry(entry)
            if entry.qdrant_point_id is not None:
                try:
                    await self.qdrant.delete_points("platform_memory", [str(entry.qdrant_point_id)])
                except Exception:
                    continue
        if hasattr(self.repository.session, "commit"):
            await self.repository.session.commit()


def datetime_now_utc() -> datetime:
    return datetime.now(UTC)
