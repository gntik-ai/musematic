from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.discovery.dependencies import build_discovery_service
from platform.discovery.events import (
    DiscoveryEventPublisher,
    DiscoveryEventType,
    register_discovery_event_types,
)
from platform.discovery.models import (
    DiscoveryExperiment,
    DiscoverySession,
    EloScore,
    GDECycle,
    Hypothesis,
    HypothesisCluster,
    HypothesisCritique,
    TournamentRound,
)
from platform.discovery.repository import DiscoveryRepository
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_event_publisher_registers_and_publishes_all_event_types() -> None:
    producer = SimpleNamespace(publish=AsyncMock())
    publisher = DiscoveryEventPublisher(producer)
    session_id = uuid4()
    workspace_id = uuid4()
    actor_id = uuid4()

    register_discovery_event_types()
    await publisher.session_started(session_id, workspace_id, actor_id)
    await publisher.hypothesis_generated(session_id, workspace_id, uuid4())
    await publisher.critique_completed(session_id, workspace_id, uuid4())
    await publisher.tournament_round_completed(session_id, workspace_id, uuid4())
    await publisher.cycle_completed(session_id, workspace_id, uuid4(), False)
    await publisher.session_converged(session_id, workspace_id, uuid4())
    await publisher.session_halted(session_id, workspace_id, actor_id, "stop")
    await publisher.experiment_designed(session_id, workspace_id, uuid4())
    await publisher.experiment_completed(session_id, workspace_id, uuid4())
    await publisher.proximity_computed(session_id, workspace_id, 2)
    await publisher.publish(
        DiscoveryEventType.session_started,
        session_id=session_id,
        workspace_id=workspace_id,
    )

    assert producer.publish.await_count == 11
    assert producer.publish.await_args.kwargs["topic"] == "discovery.events"


def test_build_discovery_service_wires_components() -> None:
    service = build_discovery_service(
        session=SimpleNamespace(),
        settings=PlatformSettings(),
        producer=None,
        redis_client=SimpleNamespace(),
        qdrant=None,
        neo4j=None,
        sandbox_client=None,
    )

    assert service.repository.redis is not None
    assert service.gde_orchestrator is not None
    assert service.experiment_designer is not None


@pytest.mark.asyncio
async def test_repository_crud_and_redis_wrappers_cover_query_paths() -> None:
    workspace_id = uuid4()
    session_id = uuid4()
    hypothesis_id = uuid4()
    now = datetime.now(UTC)
    session_row = DiscoverySession(
        id=session_id,
        workspace_id=workspace_id,
        research_question="rq",
        corpus_refs=[],
        config={},
        status="active",
        current_cycle=0,
        initiated_by=uuid4(),
        created_at=now,
        updated_at=now,
    )
    hypothesis = Hypothesis(
        id=hypothesis_id,
        workspace_id=workspace_id,
        session_id=session_id,
        title="h",
        description="d",
        reasoning="r",
        confidence=0.7,
        generating_agent_fqn="agent",
        status="active",
        created_at=now,
        updated_at=now,
    )
    elo = EloScore(
        id=uuid4(),
        workspace_id=workspace_id,
        hypothesis_id=hypothesis_id,
        session_id=session_id,
        current_score=1000.0,
        wins=0,
        losses=0,
        draws=0,
        score_history=[],
        created_at=now,
        updated_at=now,
    )
    result_queue = [
        _result(session_row),
        _result([session_row]),
        _result(session_row),
        _result(hypothesis),
        _result([hypothesis]),
        _result([hypothesis]),
        _result(
            [
                HypothesisCritique(
                    id=uuid4(),
                    workspace_id=workspace_id,
                    hypothesis_id=hypothesis_id,
                    session_id=session_id,
                    reviewer_agent_fqn="r",
                    scores={},
                    is_aggregated=False,
                    created_at=now,
                    updated_at=now,
                )
            ]
        ),
        _result(
            [
                TournamentRound(
                    id=uuid4(),
                    workspace_id=workspace_id,
                    session_id=session_id,
                    round_number=1,
                    pairwise_results=[],
                    elo_changes=[],
                    status="completed",
                    created_at=now,
                    updated_at=now,
                )
            ]
        ),
        _result(elo),
        _result([elo]),
        _result(
            GDECycle(
                id=uuid4(),
                workspace_id=workspace_id,
                session_id=session_id,
                cycle_number=1,
                status="running",
                generation_count=0,
                debate_record={},
                refinement_count=0,
                converged=False,
                created_at=now,
                updated_at=now,
            )
        ),
        _result(
            GDECycle(
                id=uuid4(),
                workspace_id=workspace_id,
                session_id=session_id,
                cycle_number=1,
                status="running",
                generation_count=0,
                debate_record={},
                refinement_count=0,
                converged=False,
                created_at=now,
                updated_at=now,
            )
        ),
        _result(
            DiscoveryExperiment(
                id=uuid4(),
                workspace_id=workspace_id,
                hypothesis_id=hypothesis_id,
                session_id=session_id,
                plan={},
                governance_status="approved",
                governance_violations=[],
                execution_status="not_started",
                designed_by_agent_fqn="designer",
                created_at=now,
                updated_at=now,
            )
        ),
        _result(
            [
                HypothesisCluster(
                    id=uuid4(),
                    workspace_id=workspace_id,
                    session_id=session_id,
                    cluster_label="cluster_1",
                    centroid_description="c",
                    hypothesis_count=1,
                    density_metric=1.0,
                    classification="normal",
                    hypothesis_ids=[str(hypothesis_id)],
                    computed_at=now,
                    created_at=now,
                    updated_at=now,
                )
            ]
        ),
    ]
    session = FakeSession(result_queue)
    redis = SimpleNamespace(
        leaderboard_add=AsyncMock(),
        leaderboard_top=AsyncMock(return_value=[(str(hypothesis_id), 1000.0)]),
        leaderboard_score=AsyncMock(return_value=1000.0),
        leaderboard_remove=AsyncMock(return_value=True),
    )
    repo = DiscoveryRepository(session, redis)

    await repo.create_session(session_row)
    assert await repo.get_session(session_id, workspace_id) is session_row
    assert (await repo.list_sessions(workspace_id, limit=1))[0] == [session_row]
    assert await repo.update_session_status(session_id, workspace_id, "halted") is session_row
    await repo.create_hypothesis(hypothesis)
    assert await repo.get_hypothesis(hypothesis_id, workspace_id) is hypothesis
    assert (await repo.list_hypotheses(session_id, workspace_id))[0] == [hypothesis]
    assert await repo.list_active_hypotheses(session_id, workspace_id) == [hypothesis]
    await repo.update_hypothesis_cluster(hypothesis_id, workspace_id, "cluster_1")
    await repo.mark_hypothesis_merged(hypothesis_id, workspace_id, uuid4())
    await repo.create_critique(
        HypothesisCritique(
            workspace_id=workspace_id,
            hypothesis_id=hypothesis_id,
            session_id=session_id,
            reviewer_agent_fqn="r",
            scores={},
            is_aggregated=False,
        )
    )
    assert len(await repo.list_critiques(hypothesis_id, workspace_id)) == 1
    await repo.create_tournament_round(
        TournamentRound(
            workspace_id=workspace_id,
            session_id=session_id,
            round_number=1,
            pairwise_results=[],
            elo_changes=[],
            status="completed",
        )
    )
    assert await repo.next_round_number(session_id) == 1
    assert (await repo.list_tournament_rounds(session_id, workspace_id))[0]
    await repo.zadd_elo(session_id, hypothesis_id, 1000.0)
    assert await repo.zrevrange_leaderboard(session_id, 5)
    assert await repo.zscore_hypothesis(session_id, hypothesis_id) == 1000.0
    assert await repo.zrem_hypothesis(session_id, hypothesis_id) is True
    assert await repo.get_elo_score(hypothesis_id, session_id) is elo
    assert await repo.list_elo_scores(session_id) == {hypothesis_id: elo}
    upsert_repo = DiscoveryRepository(FakeSession([_result(elo)]), redis)
    assert (
        await upsert_repo.upsert_elo_score(
            hypothesis_id=hypothesis_id,
            session_id=session_id,
            workspace_id=workspace_id,
            current_score=1005.0,
            result="win",
            round_number=2,
        )
        is elo
    )
    no_redis_repo = DiscoveryRepository(FakeSession([]), None)
    await no_redis_repo.zadd_elo(session_id, hypothesis_id, 1.0)
    assert await no_redis_repo.zrevrange_leaderboard(session_id, 5) == []
    assert await no_redis_repo.zscore_hypothesis(session_id, hypothesis_id) is None
    assert await no_redis_repo.zrem_hypothesis(session_id, hypothesis_id) is False
    cycle = await repo.create_cycle(
        GDECycle(
            workspace_id=workspace_id,
            session_id=session_id,
            cycle_number=1,
            status="running",
            generation_count=0,
            debate_record={},
            refinement_count=0,
            converged=False,
        )
    )
    assert await repo.get_cycle(cycle.id, workspace_id)
    assert await repo.get_running_cycle(session_id, workspace_id)
    await repo.complete_cycle(
        cycle,
        status="completed",
        generation_count=1,
        refinement_count=0,
        debate_record={},
        convergence_metric=0.1,
        converged=False,
    )
    await repo.create_experiment(
        DiscoveryExperiment(
            workspace_id=workspace_id,
            hypothesis_id=hypothesis_id,
            session_id=session_id,
            plan={},
            governance_status="approved",
            governance_violations=[],
            execution_status="not_started",
            designed_by_agent_fqn="designer",
        )
    )
    experiment = await repo.get_experiment(uuid4(), workspace_id)
    assert experiment is not None
    await repo.update_experiment(experiment, execution_status="completed")
    await repo.replace_clusters(session_id, workspace_id, [])
    assert await repo.list_clusters(session_id, workspace_id)


class FakeSession:
    def __init__(self, results):
        self.results = list(results)
        self.added = []
        self.flushed = 0

    def add(self, item):
        self.added.append(item)

    def add_all(self, items):
        self.added.extend(items)

    async def flush(self):
        self.flushed += 1

    async def execute(self, *args, **_kwargs):
        statement_name = args[0].__class__.__name__ if args else ""
        if statement_name in {"Update", "Delete", "Insert"}:
            return _result(None)
        if self.results:
            return self.results.pop(0)
        return _result(None)

    async def scalar(self, *_args, **_kwargs):
        return 0


class _ScalarResult:
    def __init__(self, payload):
        self.payload = payload

    def all(self):
        return self.payload if isinstance(self.payload, list) else [self.payload]


class _Result:
    def __init__(self, payload):
        self.payload = payload

    def scalar_one_or_none(self):
        return None if isinstance(self.payload, list) else self.payload

    def scalar_one(self):
        return self.payload[0] if isinstance(self.payload, list) else self.payload

    def scalars(self):
        return _ScalarResult(self.payload)


def _result(payload):
    return _Result(payload)
