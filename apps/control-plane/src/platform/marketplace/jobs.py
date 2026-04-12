from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.marketplace.events import emit_trending_updated
from platform.marketplace.models import RecommendationType
from platform.marketplace.recommendation_service import MarketplaceRecommendationService
from platform.marketplace.repository import MarketplaceRepository
from typing import Any
from uuid import UUID, uuid4


async def run_cf_recommendations(
    *,
    service: MarketplaceRecommendationService,
    repository: MarketplaceRepository,
) -> None:
    rows = await service.clickhouse.execute_query(
        """
        SELECT
            user_id,
            agent_id,
            any(agent_fqn) AS agent_fqn,
            count() AS invocation_count
        FROM usage_events
        WHERE timestamp >= now() - INTERVAL 30 DAY
        GROUP BY user_id, agent_id
        """,
    )
    user_vectors: dict[UUID, dict[UUID, float]] = defaultdict(dict)
    agent_fqns: dict[UUID, str] = {}
    for row in rows:
        user_id = UUID(str(row["user_id"]))
        agent_id = UUID(str(row["agent_id"]))
        user_vectors[user_id][agent_id] = float(row.get("invocation_count") or 0.0)
        agent_fqns[agent_id] = str(row.get("agent_fqn") or "")

    for user_id, vector in user_vectors.items():
        candidate_scores: dict[UUID, float] = defaultdict(float)
        for other_user, other_vector in user_vectors.items():
            if other_user == user_id:
                continue
            similarity = _cosine_similarity(vector, other_vector)
            if similarity <= 0:
                continue
            for agent_id, count in other_vector.items():
                if agent_id in vector:
                    continue
                candidate_scores[agent_id] += similarity * count
        ranked = sorted(candidate_scores.items(), key=lambda item: (-item[1], str(item[0])))[:50]
        expires_at = datetime.now(UTC) + timedelta(hours=24)
        await repository.bulk_replace_recommendations(
            user_id=user_id,
            recommendations=[
                {
                    "agent_id": agent_id,
                    "agent_fqn": agent_fqns.get(agent_id, ""),
                    "recommendation_type": RecommendationType.collaborative.value,
                    "score": score,
                    "reasoning": "Users with similar usage patterns also invoked this agent.",
                    "expires_at": expires_at,
                }
                for agent_id, score in ranked
            ],
        )


async def run_trending_computation(
    *,
    repository: MarketplaceRepository,
    clickhouse: Any,
    redis_client: Any,
    producer: EventProducer | None,
) -> None:
    rows = await clickhouse.execute_query(
        """
        SELECT
            agent_id,
            any(agent_fqn) AS agent_fqn,
            countIf(timestamp >= now() - INTERVAL 7 DAY) AS invocations_this_week,
            countIf(
                timestamp >= now() - INTERVAL 14 DAY
                AND timestamp < now() - INTERVAL 7 DAY
            ) AS invocations_last_week
        FROM usage_events
        GROUP BY agent_id
        """
    )
    ranked: list[dict[str, Any]] = []
    for row in rows:
        this_week = int(row.get("invocations_this_week") or 0)
        last_week = int(row.get("invocations_last_week") or 0)
        if this_week < 5:
            continue
        growth_rate = this_week / max(last_week, 1)
        ranked.append(
            {
                "agent_id": UUID(str(row["agent_id"])),
                "agent_fqn": str(row.get("agent_fqn") or ""),
                "trending_score": growth_rate,
                "growth_rate": growth_rate,
                "invocations_this_week": this_week,
                "invocations_last_week": last_week,
                "trending_reason": f"{round(growth_rate)}x more invocations this week",
                "satisfaction_delta": _maybe_float(row.get("satisfaction_delta")),
            }
        )
    ranked.sort(key=lambda item: (-float(item["growth_rate"]), item["agent_fqn"]))
    ranked = ranked[:20]
    snapshot_date = datetime.now(UTC).date()
    snapshot_entries = [
        dict(entry, rank=index)
        for index, entry in enumerate(ranked, start=1)
    ]
    await repository.insert_trending_snapshot(snapshot_date=snapshot_date, entries=snapshot_entries)
    await redis_client.set(
        "marketplace:trending:latest",
        json.dumps(
            {
                "snapshot_date": snapshot_date.isoformat(),
                "agents": [
                    {
                        "rank": entry["rank"],
                        "agent_id": str(entry["agent_id"]),
                        "agent_fqn": entry["agent_fqn"],
                        "trending_score": entry["trending_score"],
                        "growth_rate": entry["growth_rate"],
                        "invocations_this_week": entry["invocations_this_week"],
                        "invocations_last_week": entry["invocations_last_week"],
                        "trending_reason": entry["trending_reason"],
                        "satisfaction_delta": entry.get("satisfaction_delta"),
                    }
                    for entry in snapshot_entries
                ],
            }
        ).encode("utf-8"),
        ttl=25 * 60 * 60,
    )
    await emit_trending_updated(
        producer,
        snapshot_date=snapshot_date,
        top_agent_fqns=[entry["agent_fqn"] for entry in snapshot_entries],
        correlation_ctx=CorrelationContext(correlation_id=uuid4()),
    )


def _cosine_similarity(left: dict[UUID, float], right: dict[UUID, float]) -> float:
    dot = sum(left.get(key, 0.0) * right.get(key, 0.0) for key in set(left) | set(right))
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
