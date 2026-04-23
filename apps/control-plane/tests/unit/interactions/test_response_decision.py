from __future__ import annotations

import platform.interactions.response_decision as decision_module
from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.interactions.response_decision import (
    AllowBlocklistDecision,
    DecisionResult,
    EmbeddingSimilarityDecision,
    KeywordDecision,
    LLMRelevanceDecision,
    ResponseDecisionEngine,
    _FailSafeSkipStrategy,
)
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from tests.interactions_support import build_agent_decision_config


class _HTTPResponseStub:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class _AsyncClientStub:
    def __init__(self, *, payload: object | None = None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error

    async def __aenter__(self) -> _AsyncClientStub:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, json: dict[str, object]) -> _HTTPResponseStub:
        del url, json
        if self.error is not None:
            raise self.error
        return _HTTPResponseStub(self.payload)


class _AsyncClientFactory:
    def __init__(self, *, payload: object | None = None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error

    def __call__(self, *args, **kwargs) -> _AsyncClientStub:
        del args, kwargs
        return _AsyncClientStub(payload=self.payload, error=self.error)


class _QdrantStub:
    def __init__(
        self, *, results: list[dict[str, object]] | None = None, error: Exception | None = None
    ) -> None:
        self.results = results or []
        self.error = error

    async def search_vectors(
        self,
        *,
        collection: str,
        query_vector: list[float],
        limit: int,
    ) -> list[dict[str, object]]:
        del collection, query_vector, limit
        if self.error is not None:
            raise self.error
        return list(self.results)


class _PersistedResult:
    def __init__(self, values: list[SimpleNamespace]) -> None:
        self.values = values

    def scalars(self) -> _PersistedResult:
        return self

    def all(self) -> list[SimpleNamespace]:
        return list(self.values)


class _SessionStub:
    def __init__(self) -> None:
        self.persisted: list[SimpleNamespace] = []

    async def execute(self, statement: object) -> _PersistedResult:
        del statement
        return _PersistedResult(self.persisted)


class _ScoreStrategy:
    async def decide(
        self,
        message: str,
        goal_context: str,
        config: dict[str, object],
    ) -> DecisionResult:
        del message, goal_context
        if "fail" in config:
            return DecisionResult(
                decision="skip",
                strategy_name="llm_relevance",
                rationale="strategy failed",
                error=str(config["fail"]),
            )
        score = float(config["mock_score"])
        return DecisionResult(
            decision="respond" if score > 0 else "skip",
            strategy_name="llm_relevance",
            score=score,
            rationale=f"score {score:.2f}",
        )


def _settings() -> PlatformSettings:
    return PlatformSettings()


def _materialize(records: list[dict[str, object]]) -> list[SimpleNamespace]:
    created_at = datetime.now(UTC)
    return [SimpleNamespace(id=uuid4(), created_at=created_at, **record) for record in records]


@pytest.mark.asyncio
async def test_llm_relevance_threshold_and_fail_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        decision_module.httpx,
        "AsyncClient",
        _AsyncClientFactory(payload={"score": 0.82}),
    )
    strategy = LLMRelevanceDecision(_settings())

    respond = await strategy.decide(
        "deploy this",
        "Goal context",
        {"threshold": 0.7},
    )

    monkeypatch.setattr(
        decision_module.httpx,
        "AsyncClient",
        _AsyncClientFactory(payload={"score": 0.42}),
    )
    skip = await strategy.decide(
        "deploy this",
        "Goal context",
        {"threshold": 0.7},
    )

    monkeypatch.setattr(
        decision_module.httpx,
        "AsyncClient",
        _AsyncClientFactory(error=httpx.ConnectError("down")),
    )
    failed = await strategy.decide(
        "deploy this",
        "Goal context",
        {"threshold": 0.7},
    )

    assert respond.decision == "respond"
    assert respond.score == pytest.approx(0.82)
    assert skip.decision == "skip"
    assert skip.score == pytest.approx(0.42)
    assert failed.decision == "skip"
    assert failed.error == "down"


@pytest.mark.asyncio
async def test_allow_blocklist_blocks_before_allow_and_defaults() -> None:
    strategy = AllowBlocklistDecision()

    blocked = await strategy.decide(
        "deploy but never expose pii",
        "Goal context",
        {"blocklist": ["pii"], "allowlist": ["deploy"], "default": "respond"},
    )
    allowed = await strategy.decide(
        "please deploy now",
        "Goal context",
        {"allowlist": ["deploy"], "default": "skip"},
    )
    fallback = await strategy.decide(
        "hello team",
        "Goal context",
        {"allowlist": ["deploy"], "default": "respond"},
    )

    assert blocked.decision == "skip"
    assert blocked.matched_terms == ["pii"]
    assert allowed.decision == "respond"
    assert allowed.matched_terms == ["deploy"]
    assert fallback.decision == "respond"


@pytest.mark.asyncio
async def test_keyword_strategy_modes_and_empty_keywords() -> None:
    strategy = KeywordDecision()

    any_match = await strategy.decide(
        "Deploy and rollback the release",
        "Goal context",
        {"keywords": ["deploy", "rollback"], "mode": "any_of"},
    )
    all_match = await strategy.decide(
        "Deploy and rollback the release",
        "Goal context",
        {"keywords": ["deploy", "rollback"], "mode": "all_of"},
    )
    partial = await strategy.decide(
        "Deploy only",
        "Goal context",
        {"keywords": ["deploy", "rollback"], "mode": "all_of"},
    )
    empty = await strategy.decide(
        "Deploy only",
        "Goal context",
        {"keywords": []},
    )

    assert any_match.decision == "respond"
    assert any_match.matched_terms == ["deploy", "rollback"]
    assert all_match.decision == "respond"
    assert partial.decision == "skip"
    assert empty.decision == "skip"
    assert empty.error == "keywords list is empty"


@pytest.mark.asyncio
async def test_keyword_strategy_matches_terms_from_goal_context() -> None:
    strategy = KeywordDecision()

    result = await strategy.decide(
        "Focus the recommendation and hedge downside scenarios.",
        "Coordinate market and portfolio perspectives for the next client review.",
        {"keywords": ["market", "portfolio"], "mode": "any_of"},
    )

    assert result.decision == "respond"
    assert result.matched_terms == ["market", "portfolio"]


@pytest.mark.asyncio
async def test_embedding_similarity_threshold_and_fail_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        decision_module.httpx,
        "AsyncClient",
        _AsyncClientFactory(payload={"data": [{"embedding": [0.1, 0.2, 0.3]}]}),
    )
    strategy = EmbeddingSimilarityDecision(
        _settings(),
        _QdrantStub(results=[{"score": 0.91}]),
    )
    respond = await strategy.decide(
        "deploy this",
        "Goal context",
        {"threshold": 0.8, "collection": "platform_memory"},
    )

    low_strategy = EmbeddingSimilarityDecision(
        _settings(),
        _QdrantStub(results=[{"score": 0.22}]),
    )
    skip = await low_strategy.decide(
        "deploy this",
        "Goal context",
        {"threshold": 0.8},
    )

    monkeypatch.setattr(
        decision_module.httpx,
        "AsyncClient",
        _AsyncClientFactory(error=httpx.ConnectError("offline")),
    )
    failed = await strategy.decide(
        "deploy this",
        "Goal context",
        {"threshold": 0.8},
    )

    assert respond.decision == "respond"
    assert respond.score == pytest.approx(0.91)
    assert skip.decision == "skip"
    assert skip.score == pytest.approx(0.22)
    assert failed.decision == "skip"
    assert failed.error == "offline"


def test_get_strategy_returns_fail_safe_for_unknown_names() -> None:
    engine = ResponseDecisionEngine(settings=_settings())

    strategy = engine.get_strategy("unknown_xyz")

    assert isinstance(strategy, _FailSafeSkipStrategy)
    assert engine.is_known_strategy("best_match") is True
    assert engine.is_known_strategy("unknown_xyz") is False


@pytest.mark.asyncio
async def test_best_match_selects_highest_score_and_breaks_ties() -> None:
    engine = ResponseDecisionEngine(settings=_settings())
    engine.strategy_registry["llm_relevance"] = _ScoreStrategy()
    session = _SessionStub()

    async def _persist_records(session_obj: _SessionStub, records: list[dict[str, object]]) -> None:
        session_obj.persisted = _materialize(records)

    engine._persist_records = _persist_records  # type: ignore[method-assign]

    base = datetime.now(UTC)
    subscriptions = [
        build_agent_decision_config(
            agent_fqn="ops:alpha",
            response_decision_strategy="best_match",
            response_decision_config={"score_strategy": "llm_relevance", "mock_score": 0.20},
            subscribed_at=base,
        ),
        build_agent_decision_config(
            agent_fqn="ops:bravo",
            response_decision_strategy="best_match",
            response_decision_config={"score_strategy": "llm_relevance", "mock_score": 0.91},
            subscribed_at=base + timedelta(seconds=5),
        ),
        build_agent_decision_config(
            agent_fqn="ops:charlie",
            response_decision_strategy="best_match",
            response_decision_config={"score_strategy": "llm_relevance", "mock_score": 0.91},
            subscribed_at=base + timedelta(seconds=10),
        ),
    ]

    results = await engine.evaluate_for_message(
        message_id=uuid4(),
        goal_id=uuid4(),
        workspace_id=uuid4(),
        message_content="deploy this now",
        goal_context="Goal context",
        subscriptions=subscriptions,
        session=session,
    )

    responders = [item.agent_fqn for item in results if item.decision == "respond"]
    skipped = {item.agent_fqn: item.rationale for item in results if item.decision == "skip"}

    assert responders == ["ops:bravo"]
    assert "winner was ops:bravo" in skipped["ops:charlie"]


@pytest.mark.asyncio
async def test_best_match_with_all_errors_skips_every_candidate() -> None:
    engine = ResponseDecisionEngine(settings=_settings())
    engine.strategy_registry["llm_relevance"] = _ScoreStrategy()
    session = _SessionStub()

    async def _persist_records(session_obj: _SessionStub, records: list[dict[str, object]]) -> None:
        session_obj.persisted = _materialize(records)

    engine._persist_records = _persist_records  # type: ignore[method-assign]

    subscriptions = [
        build_agent_decision_config(
            agent_fqn="ops:alpha",
            response_decision_strategy="best_match",
            response_decision_config={"score_strategy": "llm_relevance", "fail": "down"},
        ),
        build_agent_decision_config(
            agent_fqn="ops:bravo",
            response_decision_strategy="best_match",
            response_decision_config={"score_strategy": "llm_relevance", "fail": "down"},
        ),
    ]

    results = await engine.evaluate_for_message(
        message_id=uuid4(),
        goal_id=uuid4(),
        workspace_id=uuid4(),
        message_content="deploy this now",
        goal_context="Goal context",
        subscriptions=subscriptions,
        session=session,
    )

    assert all(item.decision == "skip" for item in results)
    assert all(item.error == "down" for item in results)



@pytest.mark.asyncio
async def test_response_decision_helpers_and_non_best_match_paths() -> None:
    engine = ResponseDecisionEngine(settings=_settings(), qdrant=None)
    session = _SessionStub()

    empty = await engine.evaluate_for_message(
        message_id=uuid4(),
        goal_id=uuid4(),
        workspace_id=uuid4(),
        message_content="hello",
        goal_context="Goal context",
        subscriptions=[],
        session=session,
    )

    async def _persist_records(session_obj: _SessionStub, records: list[dict[str, object]]) -> None:
        session_obj.persisted = _materialize(records)

    engine._persist_records = _persist_records  # type: ignore[method-assign]

    single = await engine.evaluate_for_message(
        message_id=uuid4(),
        goal_id=uuid4(),
        workspace_id=uuid4(),
        message_content="hello",
        goal_context="Goal context",
        subscriptions=[
            build_agent_decision_config(
                agent_fqn="ops:unknown",
                response_decision_strategy="unknown_strategy",
                response_decision_config={},
            )
        ],
        session=session,
    )

    assert empty == []
    assert len(single) == 1
    assert single[0].strategy_name == "unknown_strategy"
    assert single[0].decision == "skip"
    assert single[0].error == "Unknown strategy: 'unknown_strategy'"

    qdrant_missing = EmbeddingSimilarityDecision(_settings(), None)
    missing = await qdrant_missing.decide("deploy", "Goal context", {"threshold": 0.5})
    assert missing.decision == "skip"
    assert missing.error == "qdrant client is unavailable"

    wrapped = await decision_module.BestMatchDecision(engine).decide("msg", "goal", {})
    assert wrapped.strategy_name == "best_match"
    assert wrapped.decision == "skip"

    assert decision_module._extract_score(
        {"choices": [{"message": {"content": '{"score": 0.77}'}}]}
    ) == pytest.approx(0.77)
    with pytest.raises(ValueError, match="score not present in LLM response"):
        decision_module._extract_score({"choices": []})
    assert decision_module._extract_embedding({"embedding": [1, 2, 3]}) == [1.0, 2.0, 3.0]
    with pytest.raises(ValueError, match="embedding not present in response"):
        decision_module._extract_embedding({"embedding": None})


@pytest.mark.asyncio
async def test_response_decision_persist_records_handles_empty_and_execute_paths() -> None:
    engine = ResponseDecisionEngine(settings=_settings())

    class PersistSession:
        def __init__(self) -> None:
            self.executed: list[object] = []
            self.flush_count = 0

        async def execute(self, statement: object):
            self.executed.append(statement)
            return None

        async def flush(self) -> None:
            self.flush_count += 1

    session = PersistSession()
    await engine._persist_records(session, [])
    assert session.executed == []
    assert session.flush_count == 0

    await engine._persist_records(
        session,
        [
            {
                "workspace_id": uuid4(),
                "goal_id": uuid4(),
                "message_id": uuid4(),
                "agent_fqn": "ops:alpha",
                "strategy_name": "keyword",
                "decision": "respond",
                "score": 1.0,
                "matched_terms": ["deploy"],
                "rationale": "matched",
                "error": None,
            }
        ],
    )
    assert len(session.executed) == 1
    assert session.flush_count == 1
