from __future__ import annotations

from platform.memory.models import EmbeddingJobStatus, EmbeddingStatus
from platform.memory.repository import MemoryRepository
from platform.memory.write_gate import request_embedding
from typing import Any
from uuid import UUID


class EmbeddingWorker:
    def __init__(
        self,
        *,
        repository: MemoryRepository,
        qdrant: Any,
        settings: Any,
    ) -> None:
        self.repository = repository
        self.qdrant = qdrant
        self.settings = settings

    async def run(self) -> None:
        await self._process_pending_jobs()

    async def _process_pending_jobs(self, limit: int = 50) -> None:
        jobs = await self.repository.get_pending_embedding_jobs(limit=limit)
        for job in jobs:
            await self.repository.update_embedding_job_status(
                job,
                status=EmbeddingJobStatus.processing,
            )
            entry = await self.repository.get_memory_entry_any(job.memory_entry_id)
            if entry is None:
                await self.repository.update_embedding_job_status(
                    job,
                    status=EmbeddingJobStatus.failed,
                    error_message="Memory entry missing",
                )
                continue
            try:
                embedding = await self._generate_embedding(entry.content)
                await self._upsert_to_qdrant(
                    entry.id,
                    embedding,
                    {
                        "memory_entry_id": str(entry.id),
                        "workspace_id": str(entry.workspace_id),
                        "agent_fqn": entry.agent_fqn,
                        "scope": entry.scope.value,
                        "source_authority": entry.source_authority,
                        "created_at_ts": entry.created_at.timestamp(),
                        "tags": list(entry.tags),
                    },
                )
                await self.repository.update_memory_entry_embedding(
                    entry.id,
                    status=EmbeddingStatus.completed,
                    qdrant_point_id=entry.id,
                )
                await self.repository.update_embedding_job_status(
                    job,
                    status=EmbeddingJobStatus.completed,
                    error_message=None,
                )
            except Exception as exc:
                retries = job.retry_count + 1
                next_status = (
                    EmbeddingJobStatus.failed if retries >= 3 else EmbeddingJobStatus.pending
                )
                await self.repository.update_embedding_job_status(
                    job,
                    status=next_status,
                    retry_count=retries,
                    error_message=str(exc),
                )
        if hasattr(self.repository.session, "commit"):
            await self.repository.session.commit()

    async def _generate_embedding(self, content: str) -> list[float]:
        return await request_embedding(
            api_url=self.settings.memory.embedding_api_url,
            model=self.settings.memory.embedding_model,
            content=content,
        )

    async def _upsert_to_qdrant(
        self,
        memory_entry_id: UUID,
        embedding: list[float],
        payload: dict[str, Any],
    ) -> None:
        await self.qdrant.upsert_vectors(
            "platform_memory",
            [{"id": str(memory_entry_id), "vector": embedding, "payload": payload}],
        )
