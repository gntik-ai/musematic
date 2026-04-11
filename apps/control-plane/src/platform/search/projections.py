from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from platform.common.clients.opensearch import AsyncOpenSearchClient, BulkIndexResult
from typing import Any

MARKETPLACE_AGENTS_INDEX = "marketplace-agents-000001"
AUDIT_EVENTS_INDEX = "audit-events-000001"


@dataclass(frozen=True, slots=True)
class AgentSearchProjection:
    client: AsyncOpenSearchClient
    index: str = MARKETPLACE_AGENTS_INDEX

    async def index_agent(self, agent_profile: dict[str, Any]) -> str:
        payload = dict(agent_profile)
        payload.setdefault("indexed_at", datetime.now(UTC).isoformat())
        payload.setdefault("updated_at", payload["indexed_at"])
        return await self.client.index_document(
            index=self.index,
            document=payload,
            document_id=str(payload.get("agent_id") or payload.get("id")),
            refresh=False,
        )

    async def delete_agent(self, agent_id: str, workspace_id: str) -> int:
        return await self.client.delete_by_query(
            index=self.index,
            query={"term": {"agent_id": agent_id}},
            workspace_id=workspace_id,
        )

    async def bulk_reindex(self, agents: list[dict[str, Any]]) -> BulkIndexResult:
        prepared: list[dict[str, Any]] = []
        timestamp = datetime.now(UTC).isoformat()
        for agent in agents:
            payload = dict(agent)
            payload.setdefault("indexed_at", timestamp)
            payload.setdefault("updated_at", timestamp)
            prepared.append(payload)
        return await self.client.bulk_index(
            index=self.index,
            documents=prepared,
            id_field="agent_id",
        )


@dataclass(frozen=True, slots=True)
class AuditSearchProjection:
    client: AsyncOpenSearchClient
    index: str = AUDIT_EVENTS_INDEX

    async def index_event(self, event: dict[str, Any]) -> str:
        payload = dict(event)
        payload.setdefault("indexed_at", datetime.now(UTC).isoformat())
        return await self.client.index_document(
            index=self.index,
            document=payload,
            document_id=str(payload.get("event_id") or payload.get("id")),
            refresh=False,
        )


def build_agent_query(
    query_text: str,
    workspace_id: str,
    capabilities: list[str] | None = None,
    maturity_level: int | None = None,
    lifecycle_state: str | None = None,
    certification_status: str | None = None,
) -> dict[str, Any]:
    filters: list[dict[str, Any]] = [{"term": {"workspace_id": workspace_id}}]
    if capabilities:
        filters.append({"terms": {"capabilities": capabilities}})
    if maturity_level is not None:
        filters.append({"term": {"maturity_level": maturity_level}})
    if lifecycle_state is not None:
        filters.append({"term": {"lifecycle_state": lifecycle_state}})
    if certification_status is not None:
        filters.append({"term": {"certification_status": certification_status}})

    must_query: dict[str, Any]
    if query_text.strip():
        must_query = {
            "multi_match": {
                "query": query_text,
                "fields": ["name^3", "purpose^2", "description", "tags"],
                "type": "best_fields",
                "analyzer": "agent_analyzer",
            }
        }
    else:
        must_query = {"match_all": {}}

    return {"bool": {"must": [must_query], "filter": filters}}


def build_agent_aggregations() -> dict[str, Any]:
    return {
        "by_capability": {"terms": {"field": "capabilities", "size": 20}},
        "by_maturity": {"terms": {"field": "maturity_level", "size": 5}},
        "by_lifecycle": {"terms": {"field": "lifecycle_state", "size": 5}},
        "by_cert": {"terms": {"field": "certification_status", "size": 5}},
        "trust_ranges": {
            "range": {
                "field": "trust_score",
                "ranges": [
                    {"to": 0.4, "key": "low"},
                    {"from": 0.4, "to": 0.7, "key": "medium"},
                    {"from": 0.7, "key": "high"},
                ],
            }
        },
    }


def build_audit_query(
    event_type: str | None,
    workspace_id: str,
    time_from: str | None,
    time_to: str | None,
    free_text: str | None = None,
) -> dict[str, Any]:
    filters: list[dict[str, Any]] = [{"term": {"workspace_id": workspace_id}}]
    if event_type is not None:
        filters.append({"term": {"event_type": event_type}})
    if time_from is not None or time_to is not None:
        range_filter: dict[str, str] = {}
        if time_from is not None:
            range_filter["gte"] = time_from
        if time_to is not None:
            range_filter["lte"] = time_to
        filters.append({"range": {"timestamp": range_filter}})

    if free_text:
        return {
            "bool": {
                "must": [{"match": {"details": free_text}}],
                "filter": filters,
            }
        }
    return {"bool": {"filter": filters}}
