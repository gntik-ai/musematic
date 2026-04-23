from __future__ import annotations

from datetime import UTC, datetime
from platform.common.clients.redis import AsyncRedisClient
from platform.discovery.models import (
    DiscoveryExperiment,
    DiscoverySession,
    DiscoveryWorkspaceSettings,
    EloScore,
    GDECycle,
    Hypothesis,
    HypothesisCluster,
    HypothesisCritique,
    TournamentRound,
)
from typing import Any
from uuid import UUID

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession


class DiscoveryRepository:
    """Async persistence helpers for scientific discovery."""

    def __init__(self, session: AsyncSession, redis: AsyncRedisClient | None = None) -> None:
        self.session = session
        self.redis = redis

    async def create_session(self, item: DiscoverySession) -> DiscoverySession:
        self.session.add(item)
        await self.session.flush()
        return item

    async def get_session(self, session_id: UUID, workspace_id: UUID) -> DiscoverySession | None:
        result = await self.session.execute(
            select(DiscoverySession).where(
                DiscoverySession.id == session_id,
                DiscoverySession.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_sessions(
        self,
        workspace_id: UUID,
        *,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> tuple[list[DiscoverySession], str | None]:
        query = select(DiscoverySession).where(DiscoverySession.workspace_id == workspace_id)
        if status is not None:
            query = query.where(DiscoverySession.status == status)
        query = _apply_uuid_cursor(query, DiscoverySession.id, cursor)
        query = query.order_by(
            DiscoverySession.created_at.desc(), DiscoverySession.id.desc()
        ).limit(limit + 1)
        return _items_with_cursor(list((await self.session.execute(query)).scalars().all()), limit)

    async def update_session_status(
        self,
        session_id: UUID,
        workspace_id: UUID,
        status: str,
        *,
        current_cycle: int | None = None,
        convergence_metrics: dict[str, Any] | None = None,
    ) -> DiscoverySession | None:
        values: dict[str, Any] = {"status": status}
        if current_cycle is not None:
            values["current_cycle"] = current_cycle
        if convergence_metrics is not None:
            values["convergence_metrics"] = convergence_metrics
        await self.session.execute(
            update(DiscoverySession)
            .where(
                DiscoverySession.id == session_id,
                DiscoverySession.workspace_id == workspace_id,
            )
            .values(**values)
        )
        await self.session.flush()
        return await self.get_session(session_id, workspace_id)

    async def get_workspace_settings(
        self,
        workspace_id: UUID,
    ) -> DiscoveryWorkspaceSettings | None:
        result = await self.session.execute(
            select(DiscoveryWorkspaceSettings).where(
                DiscoveryWorkspaceSettings.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_workspace_settings(
        self,
        workspace_id: UUID,
        **fields: Any,
    ) -> DiscoveryWorkspaceSettings:
        values = {
            "workspace_id": workspace_id,
            **fields,
        }
        stmt = pg_insert(DiscoveryWorkspaceSettings).values(**values)
        await self.session.execute(
            stmt.on_conflict_do_update(
                index_elements=[DiscoveryWorkspaceSettings.workspace_id],
                set_=fields or {"workspace_id": workspace_id},
            )
        )
        await self.session.flush()
        result = await self.session.execute(
            select(DiscoveryWorkspaceSettings).where(
                DiscoveryWorkspaceSettings.workspace_id == workspace_id,
            )
        )
        return result.scalar_one()

    async def create_hypothesis(self, item: Hypothesis) -> Hypothesis:
        self.session.add(item)
        await self.session.flush()
        return item

    async def get_hypothesis(
        self,
        hypothesis_id: UUID,
        workspace_id: UUID,
    ) -> Hypothesis | None:
        result = await self.session.execute(
            select(Hypothesis).where(
                Hypothesis.id == hypothesis_id,
                Hypothesis.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_hypothesis_any(self, hypothesis_id: UUID) -> Hypothesis | None:
        result = await self.session.execute(
            select(Hypothesis).where(Hypothesis.id == hypothesis_id)
        )
        return result.scalar_one_or_none()

    async def list_hypotheses(
        self,
        session_id: UUID,
        workspace_id: UUID,
        *,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> tuple[list[Hypothesis], str | None]:
        query = select(Hypothesis).where(
            Hypothesis.session_id == session_id,
            Hypothesis.workspace_id == workspace_id,
        )
        if status is not None:
            query = query.where(Hypothesis.status == status)
        query = _apply_uuid_cursor(query, Hypothesis.id, cursor)
        query = query.order_by(Hypothesis.created_at.desc(), Hypothesis.id.desc()).limit(limit + 1)
        return _items_with_cursor(list((await self.session.execute(query)).scalars().all()), limit)

    async def list_active_hypotheses(
        self,
        session_id: UUID,
        workspace_id: UUID,
    ) -> list[Hypothesis]:
        result = await self.session.execute(
            select(Hypothesis)
            .where(
                Hypothesis.session_id == session_id,
                Hypothesis.workspace_id == workspace_id,
                Hypothesis.status == "active",
            )
            .order_by(Hypothesis.created_at.asc(), Hypothesis.id.asc())
        )
        return list(result.scalars().all())

    async def list_hypotheses_pending_embedding(
        self,
        workspace_id: UUID,
        limit: int = 100,
    ) -> list[Hypothesis]:
        result = await self.session.execute(
            select(Hypothesis)
            .where(
                Hypothesis.workspace_id == workspace_id,
                Hypothesis.status == "active",
                Hypothesis.embedding_status == "pending",
            )
            .order_by(Hypothesis.created_at.asc(), Hypothesis.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_hypotheses_for_workspace(
        self,
        workspace_id: UUID,
        session_id: UUID | None = None,
        embedding_status: str | list[str] | None = None,
    ) -> list[Hypothesis]:
        query = select(Hypothesis).where(
            Hypothesis.workspace_id == workspace_id,
            Hypothesis.status == "active",
        )
        if session_id is not None:
            query = query.where(Hypothesis.session_id == session_id)
        if isinstance(embedding_status, list):
            query = query.where(Hypothesis.embedding_status.in_(embedding_status))
        elif embedding_status is not None:
            query = query.where(Hypothesis.embedding_status == embedding_status)
        query = query.order_by(Hypothesis.created_at.asc(), Hypothesis.id.asc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_active_workspace_ids(self) -> list[UUID]:
        result = await self.session.execute(
            select(DiscoverySession.workspace_id)
            .where(DiscoverySession.status == "active")
            .distinct()
            .order_by(DiscoverySession.workspace_id.asc())
        )
        return [UUID(str(item)) for item in result.scalars().all()]

    async def update_hypothesis_cluster(
        self,
        hypothesis_id: UUID,
        workspace_id: UUID,
        cluster_id: str | None,
    ) -> None:
        await self.session.execute(
            update(Hypothesis)
            .where(Hypothesis.id == hypothesis_id, Hypothesis.workspace_id == workspace_id)
            .values(cluster_id=cluster_id)
        )
        await self.session.flush()

    async def mark_hypothesis_merged(
        self,
        hypothesis_id: UUID,
        workspace_id: UUID,
        merged_into_id: UUID,
    ) -> None:
        await self.session.execute(
            update(Hypothesis)
            .where(Hypothesis.id == hypothesis_id, Hypothesis.workspace_id == workspace_id)
            .values(status="merged", merged_into_id=merged_into_id)
        )
        await self.session.flush()

    async def create_critique(self, item: HypothesisCritique) -> HypothesisCritique:
        self.session.add(item)
        await self.session.flush()
        return item

    async def list_critiques(
        self,
        hypothesis_id: UUID,
        workspace_id: UUID,
    ) -> list[HypothesisCritique]:
        result = await self.session.execute(
            select(HypothesisCritique)
            .where(
                HypothesisCritique.hypothesis_id == hypothesis_id,
                HypothesisCritique.workspace_id == workspace_id,
            )
            .order_by(HypothesisCritique.is_aggregated.asc(), HypothesisCritique.created_at.asc())
        )
        return list(result.scalars().all())

    async def create_tournament_round(self, item: TournamentRound) -> TournamentRound:
        self.session.add(item)
        await self.session.flush()
        return item

    async def next_round_number(self, session_id: UUID) -> int:
        max_round = await self.session.scalar(
            select(func.max(TournamentRound.round_number)).where(
                TournamentRound.session_id == session_id
            )
        )
        return int(max_round or 0) + 1

    async def list_tournament_rounds(
        self,
        session_id: UUID,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> tuple[list[TournamentRound], str | None]:
        query = select(TournamentRound).where(
            TournamentRound.session_id == session_id,
            TournamentRound.workspace_id == workspace_id,
        )
        query = _apply_uuid_cursor(query, TournamentRound.id, cursor)
        query = query.order_by(
            TournamentRound.round_number.desc(), TournamentRound.id.desc()
        ).limit(limit + 1)
        return _items_with_cursor(list((await self.session.execute(query)).scalars().all()), limit)

    async def upsert_elo_score(
        self,
        *,
        hypothesis_id: UUID,
        session_id: UUID,
        workspace_id: UUID,
        current_score: float,
        result: str | None = None,
        round_number: int | None = None,
    ) -> EloScore:
        values: dict[str, Any] = {
            "hypothesis_id": hypothesis_id,
            "session_id": session_id,
            "workspace_id": workspace_id,
            "current_score": current_score,
            "wins": 1 if result == "win" else 0,
            "losses": 1 if result == "loss" else 0,
            "draws": 1 if result == "draw" else 0,
            "score_history": [
                {
                    "round_number": round_number,
                    "score": current_score,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            ],
        }
        insert_stmt = pg_insert(EloScore).values(**values)
        update_values = {
            "current_score": current_score,
            "wins": EloScore.wins + values["wins"],
            "losses": EloScore.losses + values["losses"],
            "draws": EloScore.draws + values["draws"],
            "score_history": EloScore.score_history + values["score_history"],
        }
        await self.session.execute(
            insert_stmt.on_conflict_do_update(
                constraint="uq_elo_hypothesis_session",
                set_=update_values,
            )
        )
        await self.session.flush()
        result_obj = await self.session.execute(
            select(EloScore).where(
                EloScore.hypothesis_id == hypothesis_id,
                EloScore.session_id == session_id,
            )
        )
        return result_obj.scalar_one()

    async def get_elo_score(self, hypothesis_id: UUID, session_id: UUID) -> EloScore | None:
        result = await self.session.execute(
            select(EloScore).where(
                EloScore.hypothesis_id == hypothesis_id,
                EloScore.session_id == session_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_elo_scores(self, session_id: UUID) -> dict[UUID, EloScore]:
        result = await self.session.execute(
            select(EloScore).where(EloScore.session_id == session_id)
        )
        return {item.hypothesis_id: item for item in result.scalars().all()}

    async def zadd_elo(self, session_id: UUID, hypothesis_id: UUID, score: float) -> None:
        if self.redis is None:
            return
        await self.redis.leaderboard_add(str(session_id), str(hypothesis_id), score)

    async def zrevrange_leaderboard(self, session_id: UUID, limit: int) -> list[tuple[str, float]]:
        if self.redis is None:
            return []
        return await self.redis.leaderboard_top(str(session_id), limit)

    async def zscore_hypothesis(self, session_id: UUID, hypothesis_id: UUID) -> float | None:
        if self.redis is None:
            return None
        return await self.redis.leaderboard_score(str(session_id), str(hypothesis_id))

    async def zrem_hypothesis(self, session_id: UUID, hypothesis_id: UUID) -> bool:
        if self.redis is None:
            return False
        return await self.redis.leaderboard_remove(str(session_id), str(hypothesis_id))

    async def create_cycle(self, item: GDECycle) -> GDECycle:
        self.session.add(item)
        await self.session.flush()
        return item

    async def get_cycle(self, cycle_id: UUID, workspace_id: UUID) -> GDECycle | None:
        result = await self.session.execute(
            select(GDECycle).where(GDECycle.id == cycle_id, GDECycle.workspace_id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def get_running_cycle(self, session_id: UUID, workspace_id: UUID) -> GDECycle | None:
        result = await self.session.execute(
            select(GDECycle).where(
                GDECycle.session_id == session_id,
                GDECycle.workspace_id == workspace_id,
                GDECycle.status == "running",
            )
        )
        return result.scalar_one_or_none()

    async def complete_cycle(
        self,
        cycle: GDECycle,
        *,
        status: str,
        generation_count: int,
        refinement_count: int,
        debate_record: dict[str, Any],
        convergence_metric: float | None,
        converged: bool,
    ) -> GDECycle:
        cycle.status = status
        cycle.generation_count = generation_count
        cycle.refinement_count = refinement_count
        cycle.debate_record = debate_record
        cycle.convergence_metric = convergence_metric
        cycle.converged = converged
        await self.session.flush()
        return cycle

    async def create_experiment(self, item: DiscoveryExperiment) -> DiscoveryExperiment:
        self.session.add(item)
        await self.session.flush()
        return item

    async def get_experiment(
        self,
        experiment_id: UUID,
        workspace_id: UUID,
    ) -> DiscoveryExperiment | None:
        result = await self.session.execute(
            select(DiscoveryExperiment).where(
                DiscoveryExperiment.id == experiment_id,
                DiscoveryExperiment.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_experiment(
        self,
        experiment: DiscoveryExperiment,
        **values: Any,
    ) -> DiscoveryExperiment:
        for key, value in values.items():
            setattr(experiment, key, value)
        await self.session.flush()
        return experiment

    async def replace_clusters(
        self,
        session_id: UUID,
        workspace_id: UUID,
        clusters: list[HypothesisCluster],
    ) -> list[HypothesisCluster]:
        await self.session.execute(
            delete(HypothesisCluster).where(
                HypothesisCluster.session_id == session_id,
                HypothesisCluster.workspace_id == workspace_id,
            )
        )
        self.session.add_all(clusters)
        await self.session.flush()
        return clusters

    async def replace_workspace_clusters(
        self,
        workspace_id: UUID,
        cluster_entries: list[HypothesisCluster],
    ) -> list[HypothesisCluster]:
        await self.session.execute(
            delete(HypothesisCluster).where(
                HypothesisCluster.workspace_id == workspace_id,
                HypothesisCluster.session_id.is_(None),
            )
        )
        self.session.add_all(cluster_entries)
        await self.session.flush()
        return cluster_entries

    async def list_clusters(self, session_id: UUID, workspace_id: UUID) -> list[HypothesisCluster]:
        result = await self.session.execute(
            select(HypothesisCluster)
            .where(
                HypothesisCluster.session_id == session_id,
                HypothesisCluster.workspace_id == workspace_id,
            )
            .order_by(HypothesisCluster.cluster_label.asc())
        )
        return list(result.scalars().all())

    async def list_workspace_clusters(self, workspace_id: UUID) -> list[HypothesisCluster]:
        result = await self.session.execute(
            select(HypothesisCluster)
            .where(
                HypothesisCluster.workspace_id == workspace_id,
                HypothesisCluster.session_id.is_(None),
            )
            .order_by(HypothesisCluster.cluster_label.asc())
        )
        return list(result.scalars().all())


def _apply_uuid_cursor(
    query: Select[tuple[Any]],
    column: Any,
    cursor: str | None,
) -> Select[tuple[Any]]:
    if cursor is None:
        return query
    return query.where(column < UUID(cursor))


def _items_with_cursor(items: list[Any], limit: int) -> tuple[list[Any], str | None]:
    next_cursor = None
    if len(items) > limit:
        next_cursor = str(items[limit - 1].id)
        items = items[:limit]
    return items, next_cursor
