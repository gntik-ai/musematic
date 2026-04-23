from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.discovery.gde.cycle import GDECycleOrchestrator
from platform.discovery.models import DiscoverySession, GDECycle, Hypothesis
from platform.discovery.proximity.graph import BiasSignal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_generate_hypotheses_injects_bias_signal_and_persists_metadata() -> None:
    workspace_id = uuid4()
    session_id = uuid4()
    actor_id = uuid4()
    session = _session(workspace_id, session_id)
    cycle = _cycle(workspace_id, session_id)
    created: list[Hypothesis] = []

    async def create_hypothesis(row: Hypothesis) -> Hypothesis:
        row.id = uuid4()
        row.created_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        created.append(row)
        return row

    workflow = SimpleNamespace(
        create_execution=AsyncMock(
            return_value={
                "hypotheses": [
                    {
                        "title": "H1",
                        "description": "D1",
                        "reasoning": "R1",
                        "confidence": 0.7,
                    }
                ]
            }
        )
    )
    proximity = SimpleNamespace(
        derive_bias_signal=AsyncMock(
            return_value=BiasSignal(
                workspace_id=workspace_id,
                session_id=session_id,
                explore_hints=["Gap A"],
                avoid_hints=["Cluster B"],
                source="session_scope",
                generated_at=datetime.now(UTC),
                skipped=False,
            )
        ),
        index_hypothesis=AsyncMock(return_value=SimpleNamespace(status="indexed")),
    )
    orchestrator = GDECycleOrchestrator(
        repository=SimpleNamespace(
            create_hypothesis=AsyncMock(side_effect=create_hypothesis),
        ),
        settings=PlatformSettings(),
        publisher=SimpleNamespace(),
        tournament=SimpleNamespace(
            elo_engine=SimpleNamespace(
                update_redis_leaderboard=AsyncMock(),
                persist_elo_score=AsyncMock(),
            )
        ),
        critique_evaluator=SimpleNamespace(),
        workflow_service=workflow,
        proximity_graph_service=proximity,
    )

    generated = await orchestrator._generate_hypotheses(session, cycle, actor_id)

    payload = workflow.create_execution.await_args.args[1]
    assert payload["explore_hints"] == ["Gap A"]
    assert payload["avoid_hints"] == ["Cluster B"]
    assert payload["bias_signal"]["source"] == "session_scope"
    assert generated[0].rationale_metadata == {
        "bias_applied": True,
        "targeted_gap": "Gap A",
        "avoided_clusters": ["Cluster B"],
        "source": "session_scope",
    }
    assert created[0].embedding_status == "indexed"
    proximity.index_hypothesis.assert_awaited_once_with(created[0].id)


@pytest.mark.asyncio
async def test_generate_hypotheses_omits_hints_when_bias_signal_is_skipped() -> None:
    workspace_id = uuid4()
    session_id = uuid4()
    actor_id = uuid4()
    session = _session(workspace_id, session_id)
    cycle = _cycle(workspace_id, session_id)
    created: list[Hypothesis] = []

    async def create_hypothesis(row: Hypothesis) -> Hypothesis:
        row.id = uuid4()
        row.created_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        created.append(row)
        return row

    workflow = SimpleNamespace(
        create_execution=AsyncMock(
            return_value={
                "hypotheses": [
                    {
                        "title": "H2",
                        "description": "D2",
                        "reasoning": "R2",
                        "confidence": 0.4,
                    }
                ]
            }
        )
    )
    proximity = SimpleNamespace(
        derive_bias_signal=AsyncMock(
            return_value=BiasSignal(
                workspace_id=workspace_id,
                session_id=session_id,
                explore_hints=[],
                avoid_hints=[],
                source="session_scope",
                generated_at=datetime.now(UTC),
                skipped=True,
                skip_reason="insufficient_data",
                min_hypotheses_required=3,
                current_embedded_count=1,
            )
        ),
        index_hypothesis=AsyncMock(return_value=SimpleNamespace(status="pending")),
    )
    orchestrator = GDECycleOrchestrator(
        repository=SimpleNamespace(
            create_hypothesis=AsyncMock(side_effect=create_hypothesis),
        ),
        settings=PlatformSettings(),
        publisher=SimpleNamespace(),
        tournament=SimpleNamespace(
            elo_engine=SimpleNamespace(
                update_redis_leaderboard=AsyncMock(),
                persist_elo_score=AsyncMock(),
            )
        ),
        critique_evaluator=SimpleNamespace(),
        workflow_service=workflow,
        proximity_graph_service=proximity,
    )

    generated = await orchestrator._generate_hypotheses(session, cycle, actor_id)

    payload = workflow.create_execution.await_args.args[1]
    assert "explore_hints" not in payload
    assert "avoid_hints" not in payload
    assert generated[0].rationale_metadata == {
        "bias_applied": False,
        "skip_reason": "insufficient_data",
        "min_hypotheses_required": 3,
        "current_embedded_count": 1,
    }
    assert created[0].embedding_status == "pending"


def _session(workspace_id, session_id):
    return DiscoverySession(
        id=session_id,
        workspace_id=workspace_id,
        research_question="Why?",
        corpus_refs=[],
        config={},
        status="active",
        current_cycle=0,
        initiated_by=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _cycle(workspace_id, session_id):
    return GDECycle(
        id=uuid4(),
        workspace_id=workspace_id,
        session_id=session_id,
        cycle_number=1,
        status="running",
        generation_count=0,
        debate_record={},
        refinement_count=0,
        converged=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_generate_hypotheses_local_fallback_bias_and_index_failure() -> None:
    workspace_id = uuid4()
    session_id = uuid4()
    actor_id = uuid4()
    session = _session(workspace_id, session_id)
    cycle = _cycle(workspace_id, session_id)
    created: list[Hypothesis] = []
    session_handle = SimpleNamespace(flush=AsyncMock())

    async def create_hypothesis(row: Hypothesis) -> Hypothesis:
        row.id = uuid4()
        row.created_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        created.append(row)
        return row

    orchestrator = GDECycleOrchestrator(
        repository=SimpleNamespace(
            create_hypothesis=AsyncMock(side_effect=create_hypothesis),
            list_active_hypotheses=AsyncMock(return_value=[]),
            session=session_handle,
        ),
        settings=PlatformSettings.model_validate({"DISCOVERY_MIN_HYPOTHESES": 1}),
        publisher=SimpleNamespace(),
        tournament=SimpleNamespace(
            elo_engine=SimpleNamespace(
                update_redis_leaderboard=AsyncMock(),
                persist_elo_score=AsyncMock(),
            )
        ),
        critique_evaluator=SimpleNamespace(),
        workflow_service=None,
        proximity_graph_service=SimpleNamespace(
            derive_bias_signal=AsyncMock(
                return_value=BiasSignal(
                    workspace_id=workspace_id,
                    session_id=session_id,
                    explore_hints=["Gap A"],
                    avoid_hints=["Cluster B"],
                    source="session_scope",
                    generated_at=datetime.now(UTC),
                    skipped=False,
                )
            ),
            index_hypothesis=AsyncMock(side_effect=RuntimeError("boom")),
        ),
    )

    generated = await orchestrator._generate_hypotheses(session, cycle, actor_id)

    assert "explore=Gap A" in generated[0].reasoning
    assert "avoid=Cluster B" in generated[0].reasoning
    assert generated[0].embedding_status == "pending"
    session_handle.flush.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_bias_signal_and_helper_paths_cover_fallbacks() -> None:
    workspace_id = uuid4()
    session_id = uuid4()
    session = _session(workspace_id, session_id)
    actor_id = uuid4()
    hypothesis = Hypothesis(
        id=uuid4(),
        workspace_id=workspace_id,
        session_id=session_id,
        title="H",
        description="D",
        reasoning="R",
        confidence=0.4,
        generating_agent_fqn="agent",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    orchestrator = GDECycleOrchestrator(
        repository=SimpleNamespace(session=SimpleNamespace(flush=AsyncMock())),
        settings=PlatformSettings(),
        publisher=SimpleNamespace(),
        tournament=SimpleNamespace(
            elo_engine=SimpleNamespace(
                get_leaderboard=AsyncMock(side_effect=[[], [SimpleNamespace(elo_score=0.0)]]),
                update_redis_leaderboard=AsyncMock(),
                persist_elo_score=AsyncMock(),
            )
        ),
        critique_evaluator=SimpleNamespace(),
        workflow_service=None,
        proximity_graph_service=None,
    )
    disabled = await orchestrator._derive_bias_signal(session)
    empty_debate = await orchestrator._debate([], workspace_id, actor_id)
    local_debate = await orchestrator._debate([hypothesis], workspace_id, actor_id)
    no_scores = await orchestrator._check_convergence(session_id)
    zero_score = await orchestrator._check_convergence(session_id)

    errored_orchestrator = GDECycleOrchestrator(
        repository=SimpleNamespace(session=SimpleNamespace(flush=AsyncMock())),
        settings=PlatformSettings(),
        publisher=SimpleNamespace(),
        tournament=SimpleNamespace(
            elo_engine=SimpleNamespace(
                update_redis_leaderboard=AsyncMock(),
                persist_elo_score=AsyncMock(),
                get_leaderboard=AsyncMock(return_value=[]),
            )
        ),
        critique_evaluator=SimpleNamespace(),
        workflow_service=SimpleNamespace(
            create_execution=AsyncMock(return_value=SimpleNamespace(payload={"arguments": ["ok"]}))
        ),
        proximity_graph_service=SimpleNamespace(
            derive_bias_signal=AsyncMock(side_effect=RuntimeError("boom"))
        ),
    )
    graph_stale = await errored_orchestrator._derive_bias_signal(session)
    workflow_debate = await errored_orchestrator._debate([hypothesis], workspace_id, actor_id)

    assert disabled.skip_reason == "bias_disabled"
    assert graph_stale.skip_reason == "graph_stale"
    assert empty_debate == {"arguments": []}
    assert local_debate["arguments"][0]["hypothesis_id"] == str(hypothesis.id)
    assert workflow_debate == {"arguments": ["ok"]}
    assert no_scores == (None, False)
    assert zero_score == (None, False)
