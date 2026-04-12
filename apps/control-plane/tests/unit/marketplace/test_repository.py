from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.marketplace.models import MarketplaceAgentRating, MarketplaceQualityAggregate
from platform.marketplace.repository import MarketplaceRepository
from uuid import uuid4

import pytest
from tests.marketplace_support import build_quality_aggregate, build_rating, build_trending_snapshot


class ScalarResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class ScalarsResult:
    def __init__(self, values) -> None:
        self.values = list(values)

    def scalars(self):
        return self

    def all(self):
        return list(self.values)


class RowsResult:
    def __init__(self, rows) -> None:
        self.rows = list(rows)

    def all(self):
        return list(self.rows)

    def one(self):
        return self.rows[0]


class SessionStub:
    def __init__(self, *, execute_results=None, scalar_results=None) -> None:
        self.execute_results = list(execute_results or [])
        self.scalar_results = list(scalar_results or [])
        self.added: list[object] = []
        self.added_all: list[list[object]] = []
        self.flush_calls = 0

    def add(self, item: object) -> None:
        self.added.append(item)

    def add_all(self, items: list[object]) -> None:
        self.added_all.append(list(items))

    async def flush(self) -> None:
        self.flush_calls += 1

    async def execute(self, statement):
        del statement
        return self.execute_results.pop(0)

    async def scalar(self, statement):
        del statement
        return self.scalar_results.pop(0)


@pytest.mark.asyncio
async def test_repository_writes_create_and_update_models() -> None:
    existing_rating = build_rating(score=2)
    session = SessionStub(
        execute_results=[
            ScalarResult(None),
            ScalarResult(existing_rating),
            ScalarResult(None),
            ScalarResult(build_quality_aggregate()),
        ]
    )
    repository = MarketplaceRepository(session)  # type: ignore[arg-type]
    user_id = uuid4()
    agent_id = uuid4()

    created, created_flag = await repository.upsert_rating(
        user_id=user_id,
        agent_id=agent_id,
        score=5,
        review_text="great",
    )
    updated, updated_flag = await repository.upsert_rating(
        user_id=existing_rating.user_id,
        agent_id=existing_rating.agent_id,
        score=4,
        review_text="updated",
    )
    aggregate = await repository.get_or_create_quality_aggregate(agent_id)
    preserved = await repository.get_or_create_quality_aggregate(aggregate.agent_id)
    touched = await repository.update_quality_aggregate(preserved, has_data=True)

    assert created_flag is True
    assert created.user_id == user_id
    assert created.agent_id == agent_id
    assert updated_flag is False
    assert updated.score == 4
    assert updated.review_text == "updated"
    assert isinstance(aggregate, MarketplaceQualityAggregate)
    assert touched.has_data is True
    assert len(session.added) == 2
    assert session.flush_calls == 4


@pytest.mark.asyncio
async def test_repository_bulk_replace_and_trending_snapshot_writes() -> None:
    session = SessionStub(execute_results=[RowsResult([]), RowsResult([])])
    repository = MarketplaceRepository(session)  # type: ignore[arg-type]
    user_id = uuid4()
    agent_id = uuid4()
    snapshot_day = datetime.now(UTC).date()

    recommendations = await repository.bulk_replace_recommendations(
        user_id=user_id,
        recommendations=[
            {
                "agent_id": agent_id,
                "agent_fqn": "finance-ops:agent",
                "recommendation_type": "collaborative",
                "score": 1.2,
                "reasoning": "similar users",
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
            }
        ],
    )
    snapshots = await repository.insert_trending_snapshot(
        snapshot_date=snapshot_day,
        entries=[
            {
                "agent_id": agent_id,
                "agent_fqn": "finance-ops:agent",
                "trending_score": 10.0,
                "growth_rate": 10.0,
                "invocations_this_week": 10,
                "invocations_last_week": 1,
                "trending_reason": "10x more invocations this week",
                "satisfaction_delta": 0.4,
                "rank": 1,
            }
        ],
    )

    assert len(recommendations) == 1
    assert recommendations[0].agent_fqn == "finance-ops:agent"
    assert len(snapshots) == 1
    assert snapshots[0].snapshot_date == snapshot_day
    assert session.flush_calls == 2
    assert len(session.added_all) == 2


@pytest.mark.asyncio
async def test_repository_read_helpers_return_expected_summaries() -> None:
    agent_id = uuid4()
    other_agent_id = uuid4()
    rating_one = build_rating(agent_id=agent_id, score=5)
    rating_two = build_rating(agent_id=agent_id, score=3)
    snapshot = datetime.now(UTC).date()
    trending_row = build_trending_snapshot(snapshot_date=snapshot, agent_id=agent_id)
    session = SessionStub(
        execute_results=[
            ScalarResult(build_quality_aggregate(agent_id=agent_id)),
            ScalarsResult(
                [
                    build_quality_aggregate(agent_id=agent_id),
                    build_quality_aggregate(agent_id=other_agent_id),
                ]
            ),
            ScalarsResult([trending_row]),
            ScalarsResult([rating_one, rating_two]),
            RowsResult([(agent_id, 4.0, 2), (other_agent_id, 5.0, 1)]),
            RowsResult([(8, 2)]),
            ScalarsResult([]),
            ScalarResult(rating_one),
        ],
        scalar_results=[snapshot, 2, 4.0, 4.0, 2],
    )
    repository = MarketplaceRepository(session)  # type: ignore[arg-type]

    quality = await repository.get_quality_aggregate(agent_id)
    qualities = await repository.get_quality_aggregates([agent_id, other_agent_id])
    latest_snapshot, rows = await repository.get_latest_trending_snapshot(limit=10)
    _ratings, total, avg_score = await repository.get_ratings_for_agent(
        agent_id,
        page=1,
        page_size=10,
    )
    rating_summary = await repository.get_rating_summary(agent_id)
    rating_summaries = await repository.get_rating_summaries([agent_id, other_agent_id])
    rating_totals = await repository.get_rating_totals(agent_id)
    recommendations = await repository.get_recommendations_for_user(uuid4(), now=datetime.now(UTC))
    raw_rating = await repository._get_rating(user_id=rating_one.user_id, agent_id=agent_id)

    assert quality is not None
    assert set(qualities) == {agent_id, other_agent_id}
    assert latest_snapshot == snapshot
    assert rows == [trending_row]
    assert total == 2
    assert avg_score == 4.0
    assert rating_summary == {"avg_score": 4.0, "review_count": 2}
    assert rating_summaries[other_agent_id]["review_count"] == 1
    assert rating_totals == (8.0, 2)
    assert recommendations == []
    assert isinstance(raw_rating, MarketplaceAgentRating)
