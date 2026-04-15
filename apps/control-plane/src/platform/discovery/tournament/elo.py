from __future__ import annotations

from dataclasses import dataclass
from platform.common.clients.redis import AsyncRedisClient
from platform.discovery.repository import DiscoveryRepository
from typing import Literal
from uuid import UUID

Outcome = Literal["a_wins", "b_wins", "draw"]


@dataclass(frozen=True, slots=True)
class LeaderboardEntry:
    hypothesis_id: UUID
    elo_score: float
    rank: int


class EloRatingEngine:
    """Compute and persist Elo scores for pairwise hypothesis tournaments."""

    def __init__(
        self,
        *,
        redis: AsyncRedisClient | None,
        repository: DiscoveryRepository | None,
        default_score: float = 1000.0,
        k_factor: int = 32,
    ) -> None:
        self.redis = redis
        self.repository = repository
        self.default_score = default_score
        self.k_factor = k_factor

    @staticmethod
    def compute_new_ratings(
        elo_a: float,
        elo_b: float,
        outcome: Outcome,
        k_factor: int = 32,
    ) -> tuple[float, float]:
        """Return new Elo ratings using the standard expected-score formula."""
        expected_a = 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0))
        expected_b = 1.0 - expected_a
        if outcome == "a_wins":
            actual_a, actual_b = 1.0, 0.0
        elif outcome == "b_wins":
            actual_a, actual_b = 0.0, 1.0
        else:
            actual_a, actual_b = 0.5, 0.5
        return (
            elo_a + k_factor * (actual_a - expected_a),
            elo_b + k_factor * (actual_b - expected_b),
        )

    async def update_redis_leaderboard(
        self,
        session_id: UUID,
        hypothesis_id: UUID,
        new_score: float,
    ) -> None:
        if self.redis is None:
            if self.repository is not None:
                await self.repository.zadd_elo(session_id, hypothesis_id, new_score)
            return
        lock = await self.redis.acquire_lock("discovery:elo", str(session_id), ttl_seconds=10)
        if not lock.success or lock.token is None:
            raise RuntimeError(f"Unable to acquire Elo lock for discovery session {session_id}")
        try:
            await self.redis.leaderboard_add(str(session_id), str(hypothesis_id), new_score)
        finally:
            await self.redis.release_lock("discovery:elo", str(session_id), lock.token)

    async def batch_update_redis_leaderboard(
        self,
        session_id: UUID,
        updates: dict[UUID, float],
    ) -> None:
        if self.redis is None:
            if self.repository is None:
                return
            for hypothesis_id, new_score in updates.items():
                await self.repository.zadd_elo(session_id, hypothesis_id, new_score)
            return
        lock = await self.redis.acquire_lock("discovery:elo", str(session_id), ttl_seconds=10)
        if not lock.success or lock.token is None:
            raise RuntimeError(f"Unable to acquire Elo lock for discovery session {session_id}")
        try:
            for hypothesis_id, new_score in updates.items():
                await self.redis.leaderboard_add(str(session_id), str(hypothesis_id), new_score)
        finally:
            await self.redis.release_lock("discovery:elo", str(session_id), lock.token)

    async def get_leaderboard(self, session_id: UUID, limit: int = 10) -> list[LeaderboardEntry]:
        if self.redis is not None:
            entries = await self.redis.leaderboard_top(str(session_id), limit)
        elif self.repository is not None:
            entries = await self.repository.zrevrange_leaderboard(session_id, limit)
        else:
            entries = []
        return [
            LeaderboardEntry(
                hypothesis_id=UUID(str(hypothesis_id)),
                elo_score=float(score),
                rank=rank,
            )
            for rank, (hypothesis_id, score) in enumerate(entries, start=1)
        ]

    async def current_score(self, session_id: UUID, hypothesis_id: UUID) -> float:
        score = None
        if self.redis is not None:
            score = await self.redis.leaderboard_score(str(session_id), str(hypothesis_id))
        elif self.repository is not None:
            score = await self.repository.zscore_hypothesis(session_id, hypothesis_id)
        if score is not None:
            return float(score)
        if self.repository is not None:
            row = await self.repository.get_elo_score(hypothesis_id, session_id)
            if row is not None:
                return float(row.current_score)
        return self.default_score

    async def persist_elo_score(
        self,
        *,
        hypothesis_id: UUID,
        session_id: UUID,
        workspace_id: UUID,
        new_score: float,
        result: Literal["win", "loss", "draw"] | None = None,
        round_number: int | None = None,
    ) -> None:
        if self.repository is None:
            return
        await self.repository.upsert_elo_score(
            hypothesis_id=hypothesis_id,
            session_id=session_id,
            workspace_id=workspace_id,
            current_score=new_score,
            result=result,
            round_number=round_number,
        )

    async def apply_evidence_bonus(
        self,
        *,
        session_id: UUID,
        hypothesis_id: UUID,
        workspace_id: UUID,
        bonus: float = 12.0,
    ) -> float:
        new_score = await self.current_score(session_id, hypothesis_id) + bonus
        await self.update_redis_leaderboard(session_id, hypothesis_id, new_score)
        await self.persist_elo_score(
            hypothesis_id=hypothesis_id,
            session_id=session_id,
            workspace_id=workspace_id,
            new_score=new_score,
            result=None,
        )
        return new_score
