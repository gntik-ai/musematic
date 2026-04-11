from __future__ import annotations

import asyncio
import math
import time
from collections import defaultdict
from datetime import UTC, datetime
from platform.memory.models import MemoryEntry, MemoryScope
from platform.memory.repository import MemoryRepository
from platform.memory.schemas import RetrievalQuery, RetrievalResponse, RetrievalResult
from platform.memory.write_gate import request_embedding
from typing import Any
from uuid import UUID


class RetrievalCoordinator:
    def __init__(
        self,
        *,
        repository: MemoryRepository,
        qdrant: Any,
        neo4j: Any,
        settings: Any,
        registry_service: Any | None,
    ) -> None:
        self.repository = repository
        self.qdrant = qdrant
        self.neo4j = neo4j
        self.settings = settings
        self.registry_service = registry_service

    async def retrieve(
        self,
        query: RetrievalQuery,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> RetrievalResponse:
        started = time.perf_counter()
        partial_sources: list[str] = []
        tasks = await asyncio.gather(
            self._wrap_source(
                "vector",
                self._vector_search(
                    query_text=query.query_text,
                    scope_filter=query.scope_filter,
                    agent_fqn=agent_fqn,
                    workspace_id=workspace_id,
                    top_k=min(20, query.top_k),
                ),
            ),
            self._wrap_source(
                "keyword",
                self._keyword_search(
                    query_text=query.query_text,
                    scope_filter=query.scope_filter,
                    agent_fqn=agent_fqn,
                    workspace_id=workspace_id,
                    top_k=min(20, query.top_k),
                    agent_fqn_filter=query.agent_fqn_filter,
                ),
            ),
            self._wrap_source(
                "graph",
                self._graph_search(
                    query_text=query.query_text,
                    workspace_id=workspace_id,
                    top_k=min(20, query.top_k),
                ),
            ),
        )
        results_by_source: dict[str, list[dict[str, Any]]] = {}
        for source_name, result in tasks:
            if isinstance(result, Exception):
                partial_sources.append(source_name)
                results_by_source[source_name] = []
            else:
                results_by_source[source_name] = result

        fused = self._reciprocal_rank_fusion(
            [results_by_source["vector"], results_by_source["keyword"], results_by_source["graph"]],
            query.rrf_k,
        )
        weighted = self._apply_authority_weight(self._apply_recency_weight(fused))
        flagged = (
            await self._flag_contradictions(weighted, workspace_id)
            if query.include_contradictions
            else weighted
        )
        final_results = [
            RetrievalResult(
                memory_entry_id=item["memory_entry_id"],
                content=item["content"],
                scope=item["scope"],
                agent_fqn=item["agent_fqn"],
                source_authority=item["source_authority"],
                rrf_score=item["rrf_score"],
                recency_factor=item["recency_factor"],
                final_score=item["final_score"],
                sources_contributed=item["sources_contributed"],
                contradiction_flag=item["contradiction_flag"],
                conflict_ids=item["conflict_ids"],
            )
            for item in flagged[: query.top_k]
        ]
        return RetrievalResponse(
            results=final_results,
            partial_sources=partial_sources,
            query_time_ms=(time.perf_counter() - started) * 1000,
        )

    async def _vector_search(
        self,
        *,
        query_text: str,
        scope_filter: MemoryScope | None,
        agent_fqn: str,
        workspace_id: UUID,
        top_k: int,
    ) -> list[dict[str, Any]]:
        embedding = await request_embedding(
            api_url=self.settings.memory.embedding_api_url,
            model=self.settings.memory.embedding_model,
            content=query_text,
        )
        is_orchestrator = await self._is_orchestrator(agent_fqn, workspace_id)
        qdrant_models = __import__("qdrant_client.models", fromlist=["models"])
        must: list[Any] = [
            qdrant_models.FieldCondition(
                key="workspace_id",
                match=qdrant_models.MatchValue(value=str(workspace_id)),
            ),
        ]
        if scope_filter is not None:
            must.append(
                qdrant_models.FieldCondition(
                    key="scope",
                    match=qdrant_models.MatchValue(value=scope_filter.value),
                )
            )
        if scope_filter is MemoryScope.per_agent:
            must.append(
                qdrant_models.FieldCondition(
                    key="agent_fqn",
                    match=qdrant_models.MatchValue(value=agent_fqn),
                )
            )
        results = await self.qdrant.search_vectors(
            "platform_memory",
            embedding,
            top_k,
            filter=qdrant_models.Filter(must=must),
        )
        ids = [UUID(str(item["payload"].get("memory_entry_id") or item["id"])) for item in results]
        entries = await self.repository.get_memory_entries_by_ids(workspace_id, ids)
        by_id = {entry.id: entry for entry in entries}
        items: list[dict[str, Any]] = []
        for result in results:
            entry_id = UUID(str(result["payload"].get("memory_entry_id") or result["id"]))
            entry = by_id.get(entry_id)
            if entry is None or not self._is_visible(entry, agent_fqn, is_orchestrator):
                continue
            items.append(self._entry_payload(entry, "vector", float(result["score"])))
        return items

    async def _keyword_search(
        self,
        *,
        query_text: str,
        scope_filter: MemoryScope | None,
        agent_fqn: str,
        workspace_id: UUID,
        top_k: int,
        agent_fqn_filter: str | None,
    ) -> list[dict[str, Any]]:
        rows = await self.repository.find_similar_by_scope(
            query_text=query_text,
            workspace_id=workspace_id,
            agent_fqn=agent_fqn,
            is_orchestrator=await self._is_orchestrator(agent_fqn, workspace_id),
            scope_filter=scope_filter,
            agent_fqn_filter=agent_fqn_filter,
            limit=top_k,
        )
        return [
            self._entry_payload(row["entry"], "keyword", float(row["score"]))
            for row in rows
        ]

    async def _graph_search(
        self,
        *,
        query_text: str,
        workspace_id: UUID,
        top_k: int,
    ) -> list[dict[str, Any]]:
        nodes = await self.repository.list_knowledge_nodes_by_query(
            workspace_id=workspace_id,
            query_text=query_text,
            limit=top_k,
        )
        return [
            {
                "memory_entry_id": node.id,
                "content": node.external_name,
                "scope": MemoryScope.per_workspace,
                "agent_fqn": node.created_by_fqn,
                "source_authority": 1.0,
                "created_at": node.created_at,
                "source": "graph",
                "raw_score": 1.0,
            }
            for node in nodes
        ]

    def _reciprocal_rank_fusion(
        self,
        result_lists: list[list[dict[str, Any]]],
        k: int,
    ) -> list[dict[str, Any]]:
        aggregated: dict[tuple[str, UUID], dict[str, Any]] = {}
        for result_list in result_lists:
            for rank, item in enumerate(result_list, start=1):
                identifier = (
                    (item["source"], item["memory_entry_id"])
                    if item["source"] == "graph"
                    else ("memory", item["memory_entry_id"])
                )
                current = aggregated.setdefault(
                    identifier,
                    {
                        **item,
                        "rrf_score": 0.0,
                        "sources_contributed": [],
                        "recency_factor": 1.0,
                        "final_score": 0.0,
                        "contradiction_flag": False,
                        "conflict_ids": [],
                    },
                )
                current["rrf_score"] += 1.0 / (k + rank)
                source_name = str(item["source"])
                if source_name not in current["sources_contributed"]:
                    current["sources_contributed"].append(source_name)
        return sorted(
            aggregated.values(),
            key=lambda item: (-float(item["rrf_score"]), -float(item["source_authority"])),
        )

    def _apply_recency_weight(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        weighted: list[dict[str, Any]] = []
        now = datetime.now(UTC)
        decay = float(getattr(self.settings.memory, "recency_decay", 0.08))
        for item in results:
            created_at = item["created_at"]
            if not isinstance(created_at, datetime):
                created_at = datetime.now(UTC)
            age_days = max((now - created_at).total_seconds(), 0.0) / 86400.0
            recency_factor = math.exp(-decay * age_days)
            updated = dict(item)
            updated["recency_factor"] = recency_factor
            updated["final_score"] = float(item["rrf_score"]) * recency_factor
            weighted.append(updated)
        return weighted

    def _apply_authority_weight(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        weighted: list[dict[str, Any]] = []
        for item in results:
            updated = dict(item)
            updated["final_score"] = float(item["final_score"]) * max(
                float(item["source_authority"]), 0.01
            )
            weighted.append(updated)
        return sorted(weighted, key=lambda item: float(item["final_score"]), reverse=True)

    async def _flag_contradictions(
        self,
        results: list[dict[str, Any]],
        workspace_id: UUID,
    ) -> list[dict[str, Any]]:
        memory_ids = [item["memory_entry_id"] for item in results if item["source"] != "graph"]
        conflicts = await self.repository.list_open_conflicts_for_entries(workspace_id, memory_ids)
        by_entry: dict[UUID, list[UUID]] = defaultdict(list)
        for conflict in conflicts:
            by_entry[conflict.memory_entry_id_a].append(conflict.id)
            by_entry[conflict.memory_entry_id_b].append(conflict.id)
        flagged: list[dict[str, Any]] = []
        for item in results:
            conflict_ids = by_entry.get(item["memory_entry_id"], [])
            updated = dict(item)
            updated["conflict_ids"] = conflict_ids
            updated["contradiction_flag"] = bool(conflict_ids)
            flagged.append(updated)
        return flagged

    async def _wrap_source(
        self,
        source_name: str,
        coroutine: Any,
    ) -> tuple[str, list[dict[str, Any]] | Exception]:
        try:
            return source_name, await coroutine
        except Exception as exc:
            return source_name, exc

    async def _is_orchestrator(self, agent_fqn: str, workspace_id: UUID) -> bool:
        if self.registry_service is None or not hasattr(self.registry_service, "get_by_fqn"):
            return False
        profile = await self.registry_service.get_by_fqn(workspace_id, agent_fqn)
        if profile is None:
            return False
        return "orchestrator" in set(getattr(profile, "role_types", []) or [])

    def _is_visible(
        self,
        entry: MemoryEntry,
        agent_fqn: str,
        is_orchestrator: bool,
    ) -> bool:
        if entry.scope is MemoryScope.per_workspace:
            return True
        if entry.scope is MemoryScope.per_agent:
            return entry.agent_fqn == agent_fqn
        return is_orchestrator

    def _entry_payload(self, entry: MemoryEntry, source: str, score: float) -> dict[str, Any]:
        return {
            "memory_entry_id": entry.id,
            "content": entry.content,
            "scope": entry.scope,
            "agent_fqn": entry.agent_fqn,
            "source_authority": entry.source_authority,
            "created_at": entry.created_at,
            "source": source,
            "raw_score": score,
        }
