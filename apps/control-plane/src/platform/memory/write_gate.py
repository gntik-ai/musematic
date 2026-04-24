from __future__ import annotations

import hashlib
import math
import random
import re
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from importlib import import_module
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.memory.events import (
    ConflictDetectedPayload,
    MemoryWrittenPayload,
    publish_conflict_detected,
    publish_memory_written,
)
from platform.memory.exceptions import (
    MemoryError as MemoryDomainError,
)
from platform.memory.exceptions import (
    WriteGateAuthError,
    WriteGateRateLimitError,
    WriteGateRetentionError,
)
from platform.memory.models import EmbeddingStatus, MemoryScope, RetentionPolicy
from platform.memory.repository import MemoryRepository
from platform.memory.schemas import MemoryWriteRequest, WriteGateResult
from typing import Any
from uuid import UUID, uuid4

import httpx

_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")


def _normalized_edit_distance(left: str, right: str) -> float:
    return 1.0 - SequenceMatcher(a=left, b=right).ratio()


async def request_embedding(
    *,
    api_url: str,
    model: str,
    content: str,
) -> list[float]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            api_url,
            json={
                "input": content,
                "model": model,
            },
        )
        response.raise_for_status()
        data = response.json()
    if isinstance(data.get("embedding"), list):
        return [float(item) for item in data["embedding"]]
    items = data.get("data")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        embedding = items[0].get("embedding")
        if isinstance(embedding, list):
            return [float(item) for item in embedding]
    raise MemoryDomainError("MEMORY_EMBEDDING_INVALID", "Embedding response missing vector")


class MemoryWriteGate:
    def __init__(
        self,
        *,
        repository: MemoryRepository,
        qdrant: Any,
        redis_client: Any,
        settings: Any,
        registry_service: Any | None,
        workspaces_service: Any | None,
        producer: EventProducer | None,
    ) -> None:
        self.repository = repository
        self.qdrant = qdrant
        self.redis_client = redis_client
        self.settings = settings
        self.registry_service = registry_service
        self.workspaces_service = workspaces_service
        self.producer = producer

    async def validate_and_write(
        self,
        request: MemoryWriteRequest,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> WriteGateResult:
        await self._check_authorization(agent_fqn, request.namespace, request.scope, workspace_id)
        remaining_min, remaining_hour = await self._check_rate_limit(agent_fqn)
        ttl_expires_at = self._validate_retention(
            request.retention_policy,
            request.scope,
            request.execution_id,
            request.ttl_seconds,
        )
        raw_content = request.content
        content, privacy_applied = await self._apply_differential_privacy(
            request.content,
            workspace_id,
        )
        embedding: list[float] | None = None
        embedding_failed = False
        try:
            embedding = await self._generate_embedding(content)
        except Exception:
            embedding_failed = True
        contradiction = await self._find_contradiction(
            content=raw_content,
            scope=request.scope,
            agent_fqn=agent_fqn,
            workspace_id=workspace_id,
            embedding=embedding,
        )

        entry = await self.repository.create_memory_entry(
            workspace_id=workspace_id,
            agent_fqn=agent_fqn,
            namespace=request.namespace,
            scope=request.scope,
            content=content,
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            source_authority=request.source_authority,
            retention_policy=request.retention_policy,
            ttl_expires_at=ttl_expires_at,
            execution_id=request.execution_id,
            tags=request.tags,
        )

        if embedding is not None:
            try:
                await self.qdrant.upsert_vectors(
                    "platform_memory",
                    [
                        {
                            "id": str(entry.id),
                            "vector": embedding,
                            "payload": {
                                "memory_entry_id": str(entry.id),
                                "workspace_id": str(workspace_id),
                                "agent_fqn": agent_fqn,
                                "scope": request.scope.value,
                                "source_authority": request.source_authority,
                                "created_at_ts": entry.created_at.timestamp(),
                                "tags": list(request.tags),
                            },
                        }
                    ],
                )
                await self.repository.update_memory_entry_embedding(
                    entry.id,
                    status=EmbeddingStatus.completed,
                    qdrant_point_id=entry.id,
                )
            except Exception as exc:
                await self.repository.soft_delete_memory_entry(entry)
                raise MemoryDomainError(
                    "MEMORY_VECTOR_WRITE_FAILED",
                    "Failed to store vector payload for memory entry",
                    {"memory_entry_id": str(entry.id), "reason": str(exc)},
                ) from exc
        else:
            existing_job = await self.repository.get_embedding_job(entry.id)
            if existing_job is None:
                await self.repository.create_embedding_job(entry.id)
            await self.repository.update_memory_entry_embedding(
                entry.id,
                status=EmbeddingStatus.pending,
            )
            if embedding_failed:
                remaining_min = max(0, remaining_min)
                remaining_hour = max(0, remaining_hour)

        conflict_id: UUID | None = None
        if contradiction is not None:
            contradiction_id, similarity = contradiction
            conflict = await self.repository.create_evidence_conflict(
                workspace_id=workspace_id,
                memory_entry_id_a=contradiction_id,
                memory_entry_id_b=entry.id,
                conflict_description="Potential contradiction detected by memory write gate",
                similarity_score=similarity,
            )
            conflict_id = conflict.id
            await publish_conflict_detected(
                self.producer,
                ConflictDetectedPayload(
                    conflict_id=conflict.id,
                    workspace_id=workspace_id,
                    memory_entry_id_a=conflict.memory_entry_id_a,
                    memory_entry_id_b=conflict.memory_entry_id_b,
                    similarity_score=similarity,
                ),
                CorrelationContext(
                    correlation_id=uuid4(),
                    workspace_id=workspace_id,
                    execution_id=request.execution_id,
                ),
            )

        correlation = CorrelationContext(
            correlation_id=uuid4(),
            workspace_id=workspace_id,
            execution_id=request.execution_id,
        )
        await publish_memory_written(
            self.producer,
            MemoryWrittenPayload(
                memory_entry_id=entry.id,
                workspace_id=workspace_id,
                agent_fqn=agent_fqn,
                scope=request.scope,
                namespace=request.namespace,
                contradiction_detected=conflict_id is not None,
                conflict_id=conflict_id,
            ),
            correlation,
        )
        return WriteGateResult(
            memory_entry_id=entry.id,
            contradiction_detected=conflict_id is not None,
            conflict_id=conflict_id,
            privacy_applied=privacy_applied,
            rate_limit_remaining_min=remaining_min,
            rate_limit_remaining_hour=remaining_hour,
        )

    async def _check_authorization(
        self,
        agent_fqn: str,
        namespace: str,
        scope: MemoryScope,
        workspace_id: UUID,
    ) -> None:
        namespace_record = None
        profile = None
        registry_repo = getattr(self.registry_service, "repository", None) or getattr(
            self.registry_service, "repo", None
        )
        if registry_repo is not None and hasattr(registry_repo, "get_namespace_by_name"):
            namespace_record = await registry_repo.get_namespace_by_name(workspace_id, namespace)
        if self.registry_service is not None and hasattr(self.registry_service, "get_by_fqn"):
            profile = await self.registry_service.get_by_fqn(workspace_id, agent_fqn)
        elif registry_repo is not None and hasattr(registry_repo, "get_agent_by_fqn"):
            profile = await registry_repo.get_agent_by_fqn(workspace_id, agent_fqn)

        workspace_repo = getattr(self.workspaces_service, "repo", None)
        workspace = None
        if workspace_repo is not None and hasattr(workspace_repo, "get_workspace_by_id_any"):
            workspace = await workspace_repo.get_workspace_by_id_any(workspace_id)
        if workspace is None or namespace_record is None or profile is None:
            raise WriteGateAuthError(namespace, agent_fqn)

        profile_namespace = getattr(getattr(profile, "namespace", None), "name", None)
        if profile_namespace != namespace:
            raise WriteGateAuthError(namespace, agent_fqn)
        if scope is MemoryScope.shared_orchestrator and "orchestrator" not in set(
            getattr(profile, "role_types", []) or []
        ):
            raise WriteGateAuthError(namespace, agent_fqn)

    async def _check_rate_limit(self, agent_fqn: str) -> tuple[int, int]:
        minute_limit = self.settings.memory.rate_limit_per_min
        hour_limit = self.settings.memory.rate_limit_per_hour
        minute_result = await self.redis_client.check_rate_limit(
            "memory",
            f"{agent_fqn}:min",
            minute_limit,
            60_000,
        )
        hour_result = await self.redis_client.check_rate_limit(
            "memory",
            f"{agent_fqn}:hour",
            hour_limit,
            3_600_000,
        )
        if not minute_result.allowed or not hour_result.allowed:
            retry_after_ms = max(minute_result.retry_after_ms, hour_result.retry_after_ms)
            raise WriteGateRateLimitError(math.ceil(retry_after_ms / 1000))
        return minute_result.remaining, hour_result.remaining

    async def _find_contradiction(
        self,
        *,
        content: str,
        scope: MemoryScope,
        agent_fqn: str,
        workspace_id: UUID,
        embedding: list[float] | None,
    ) -> tuple[UUID, float] | None:
        if embedding is None:
            return None

        qdrant_models = import_module("qdrant_client.models")
        must: list[Any] = [
            qdrant_models.FieldCondition(
                key="workspace_id",
                match=qdrant_models.MatchValue(value=str(workspace_id)),
            ),
            qdrant_models.FieldCondition(
                key="scope",
                match=qdrant_models.MatchValue(value=scope.value),
            ),
        ]
        if scope is MemoryScope.per_agent:
            must.append(
                qdrant_models.FieldCondition(
                    key="agent_fqn",
                    match=qdrant_models.MatchValue(value=agent_fqn),
                )
            )
        results = await self.qdrant.search_vectors(
            "platform_memory",
            embedding,
            5,
            filter=qdrant_models.Filter(must=must),
        )
        if not results:
            return None

        candidate_ids: list[UUID] = []
        candidate_scores: dict[UUID, float] = {}
        for item in results:
            raw_id = item["payload"].get("memory_entry_id") or item["id"]
            candidate_id = UUID(str(raw_id))
            candidate_ids.append(candidate_id)
            candidate_scores[candidate_id] = float(item["score"])

        candidates = await self.repository.get_memory_entries_by_ids(workspace_id, candidate_ids)
        for candidate in candidates:
            similarity = candidate_scores.get(candidate.id, 0.0)
            distance = _normalized_edit_distance(content, candidate.content)
            if (
                similarity >= self.settings.memory.contradiction_similarity_threshold
                and distance > self.settings.memory.contradiction_edit_distance_threshold
            ):
                return candidate.id, similarity
        return None

    def _validate_retention(
        self,
        policy: RetentionPolicy,
        scope: MemoryScope,
        execution_id: UUID | None,
        ttl_seconds: int | None,
    ) -> datetime | None:
        del scope
        if policy is RetentionPolicy.session_only and execution_id is None:
            raise WriteGateRetentionError("execution_id is required for session-only retention")
        if policy is RetentionPolicy.time_limited and ttl_seconds is None:
            raise WriteGateRetentionError("ttl_seconds is required for time-limited retention")
        if policy is RetentionPolicy.permanent and ttl_seconds is not None:
            raise WriteGateRetentionError("ttl_seconds is not allowed for permanent retention")
        if ttl_seconds is None:
            return None
        return datetime.now(UTC) + timedelta(seconds=ttl_seconds)

    async def _apply_differential_privacy(
        self,
        content: str,
        workspace_id: UUID,
    ) -> tuple[str, bool]:
        del workspace_id
        if not self.settings.memory.differential_privacy_enabled:
            return content, False
        epsilon = max(self.settings.memory.differential_privacy_epsilon, 0.0001)
        scale = 1.0 / epsilon

        def _replace(match: re.Match[str]) -> str:
            raw = match.group(0)
            numeric = float(raw)
            noisy = numeric + self._laplace_noise(scale)
            if "." not in raw:
                return str(round(noisy))
            return f"{noisy:.4f}".rstrip("0").rstrip(".")

        return _NUMBER_PATTERN.sub(_replace, content), True

    async def _generate_embedding(self, content: str) -> list[float]:
        return await request_embedding(
            api_url=self.settings.memory.embedding_api_url,
            model=self.settings.memory.embedding_model,
            content=content,
        )

    def _laplace_noise(self, scale: float) -> float:
        u = random.random() - 0.5
        return -scale * math.copysign(math.log1p(-2.0 * abs(u)), u)
