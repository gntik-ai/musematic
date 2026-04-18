from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from fnmatch import fnmatch
from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.config import PlatformSettings
from platform.interactions.models import WorkspaceGoalDecisionRationale
from platform.workspaces.models import WorkspaceAgentDecisionConfig
from typing import Any, Literal, Protocol
from uuid import UUID

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = logging.getLogger(__name__)


class DecisionResult(BaseModel):
    decision: Literal["respond", "skip"]
    strategy_name: str
    score: float | None = None
    matched_terms: list[str] = Field(default_factory=list)
    rationale: str = ""
    error: str | None = None


class ResponseDecisionStrategy(Protocol):
    async def decide(
        self,
        message: str,
        goal_context: str,
        config: dict[str, Any],
    ) -> DecisionResult: ...


@dataclass(slots=True)
class _FailSafeSkipStrategy:
    error: str = "Unknown strategy"

    async def decide(
        self,
        message: str,
        goal_context: str,
        config: dict[str, Any],
    ) -> DecisionResult:
        del message, goal_context, config
        return DecisionResult(
            decision="skip",
            strategy_name="fail_safe_skip",
            rationale="Strategy failed safe to skip",
            error=self.error,
        )


class LLMRelevanceDecision:
    def __init__(self, settings: PlatformSettings) -> None:
        self.settings = settings

    async def decide(
        self,
        message: str,
        goal_context: str,
        config: dict[str, Any],
    ) -> DecisionResult:
        threshold = float(config.get("threshold", 0.7))
        payload = {
            "goal_context": goal_context,
            "message": message,
            "response_format": {"type": "json_object"},
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.settings.composition.llm_api_url, json=payload)
                response.raise_for_status()
            score = _extract_score(response.json())
            decision = "respond" if score >= threshold else "skip"
            rationale = (
                f"Relevance score {score:.2f} meets threshold {threshold:.2f}"
                if decision == "respond"
                else f"Relevance score {score:.2f} below threshold {threshold:.2f}"
            )
            return DecisionResult(
                decision=decision,
                strategy_name="llm_relevance",
                score=score,
                rationale=rationale,
            )
        except Exception as exc:  # pragma: no cover
            return DecisionResult(
                decision="skip",
                strategy_name="llm_relevance",
                rationale="LLM relevance evaluation failed safe to skip",
                error=str(exc),
            )


class AllowBlocklistDecision:
    async def decide(
        self,
        message: str,
        goal_context: str,
        config: dict[str, Any],
    ) -> DecisionResult:
        del goal_context
        normalized_tokens = _message_tokens(message)
        blocklist = [str(item) for item in config.get("blocklist", [])]
        allowlist = [str(item) for item in config.get("allowlist", [])]
        for pattern in blocklist:
            matches = [token for token in normalized_tokens if fnmatch(token, pattern.lower())]
            if matches:
                return DecisionResult(
                    decision="skip",
                    strategy_name="allow_blocklist",
                    matched_terms=[matches[0]],
                    rationale=f"Blocklist pattern '{pattern}' matched",
                )
        for pattern in allowlist:
            matches = [token for token in normalized_tokens if fnmatch(token, pattern.lower())]
            if matches:
                return DecisionResult(
                    decision="respond",
                    strategy_name="allow_blocklist",
                    matched_terms=[matches[0]],
                    rationale=f"Allowlist pattern '{pattern}' matched",
                )
        default_decision = str(config.get("default", "skip"))
        return DecisionResult(
            decision="respond" if default_decision == "respond" else "skip",
            strategy_name="allow_blocklist",
            rationale=f"No allow/blocklist match; default decision is '{default_decision}'",
        )


class KeywordDecision:
    async def decide(
        self,
        message: str,
        goal_context: str,
        config: dict[str, Any],
    ) -> DecisionResult:
        del goal_context
        keywords = [str(item) for item in config.get("keywords", []) if str(item).strip()]
        if not keywords:
            return DecisionResult(
                decision="skip",
                strategy_name="keyword",
                rationale="Keyword strategy requires at least one keyword",
                error="keywords list is empty",
            )
        case_sensitive = bool(config.get("case_sensitive", False))
        haystack = message if case_sensitive else message.lower()
        normalized_keywords = keywords if case_sensitive else [item.lower() for item in keywords]
        matches = [kw for kw in normalized_keywords if kw in haystack]
        mode = str(config.get("mode", "any_of"))
        if mode == "all_of":
            decision = "respond" if len(matches) == len(normalized_keywords) else "skip"
        else:
            decision = "respond" if matches else "skip"
        rationale = (
            f"Keyword match in mode {mode}"
            if decision == "respond"
            else f"No keyword match in mode {mode}"
        )
        return DecisionResult(
            decision=decision,
            strategy_name="keyword",
            matched_terms=matches,
            rationale=rationale,
        )


class EmbeddingSimilarityDecision:
    def __init__(self, settings: PlatformSettings, qdrant: AsyncQdrantClient | None) -> None:
        self.settings = settings
        self.qdrant = qdrant

    async def decide(
        self,
        message: str,
        goal_context: str,
        config: dict[str, Any],
    ) -> DecisionResult:
        del goal_context
        threshold = float(config.get("threshold", 0.7))
        collection = str(config.get("collection", "platform_memory"))
        if self.qdrant is None:
            return DecisionResult(
                decision="skip",
                strategy_name="embedding_similarity",
                rationale="Qdrant client unavailable",
                error="qdrant client is unavailable",
            )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.settings.memory.embedding_api_url,
                    json={"model": self.settings.memory.embedding_model, "input": message},
                )
                response.raise_for_status()
            vector = _extract_embedding(response.json())
            results = await self.qdrant.search_vectors(
                collection=collection,
                query_vector=vector,
                limit=1,
            )
            score = float(results[0]["score"]) if results else 0.0
            decision = "respond" if score >= threshold else "skip"
            rationale = (
                f"Similarity score {score:.2f} meets threshold {threshold:.2f}"
                if decision == "respond"
                else f"Similarity score {score:.2f} below threshold {threshold:.2f}"
            )
            return DecisionResult(
                decision=decision,
                strategy_name="embedding_similarity",
                score=score,
                rationale=rationale,
            )
        except Exception as exc:  # pragma: no cover
            return DecisionResult(
                decision="skip",
                strategy_name="embedding_similarity",
                rationale="Embedding similarity evaluation failed safe to skip",
                error=str(exc),
            )


class BestMatchDecision:
    def __init__(self, engine: ResponseDecisionEngine) -> None:
        self.engine = engine

    async def decide(
        self,
        message: str,
        goal_context: str,
        config: dict[str, Any],
    ) -> DecisionResult:
        del message, goal_context, config
        return DecisionResult(
            decision="skip",
            strategy_name="best_match",
            rationale="best_match is orchestrated at engine level",
        )


class ResponseDecisionEngine:
    def __init__(
        self, *, settings: PlatformSettings, qdrant: AsyncQdrantClient | None = None
    ) -> None:
        self.settings = settings
        self.qdrant = qdrant
        self.strategy_registry: dict[str, ResponseDecisionStrategy] = {
            "llm_relevance": LLMRelevanceDecision(settings),
            "allow_blocklist": AllowBlocklistDecision(),
            "keyword": KeywordDecision(),
            "embedding_similarity": EmbeddingSimilarityDecision(settings, qdrant),
        }
        self.strategy_registry["best_match"] = BestMatchDecision(self)

    async def evaluate_for_message(
        self,
        *,
        message_id: UUID,
        goal_id: UUID,
        workspace_id: UUID,
        message_content: str,
        goal_context: str,
        subscriptions: list[WorkspaceAgentDecisionConfig],
        session: AsyncSession,
    ) -> list[WorkspaceGoalDecisionRationale]:
        if not subscriptions:
            return []
        if any(item.response_decision_strategy == "best_match" for item in subscriptions):
            await self._evaluate_best_match(
                message_id=message_id,
                goal_id=goal_id,
                workspace_id=workspace_id,
                message_content=message_content,
                goal_context=goal_context,
                subscriptions=subscriptions,
                session=session,
            )
        else:
            records = []
            for subscription in subscriptions:
                strategy_name = subscription.response_decision_strategy
                strategy = self.get_strategy(strategy_name)
                config = dict(subscription.response_decision_config or {})
                result = await strategy.decide(message_content, goal_context, config)
                records.append(
                    {
                        "workspace_id": workspace_id,
                        "goal_id": goal_id,
                        "message_id": message_id,
                        "agent_fqn": subscription.agent_fqn,
                        "strategy_name": strategy_name,
                        "decision": result.decision,
                        "score": result.score,
                        "matched_terms": list(result.matched_terms),
                        "rationale": result.rationale,
                        "error": result.error,
                    }
                )
            await self._persist_records(session, records)
        query_result = await session.execute(
            select(WorkspaceGoalDecisionRationale)
            .where(
                WorkspaceGoalDecisionRationale.workspace_id == workspace_id,
                WorkspaceGoalDecisionRationale.message_id == message_id,
            )
            .order_by(
                WorkspaceGoalDecisionRationale.created_at.asc(),
                WorkspaceGoalDecisionRationale.agent_fqn.asc(),
            )
        )
        return list(query_result.scalars().all())

    def get_strategy(self, name: str) -> ResponseDecisionStrategy:
        strategy = self.strategy_registry.get(name)
        if strategy is None:
            return _FailSafeSkipStrategy(error=f"Unknown strategy: {name!r}")
        return strategy

    def is_known_strategy(self, name: str) -> bool:
        return name in self.strategy_registry

    async def _evaluate_best_match(
        self,
        *,
        message_id: UUID,
        goal_id: UUID,
        workspace_id: UUID,
        message_content: str,
        goal_context: str,
        subscriptions: list[WorkspaceAgentDecisionConfig],
        session: AsyncSession,
    ) -> list[dict[str, Any]]:
        candidates: list[tuple[WorkspaceAgentDecisionConfig, DecisionResult, float]] = []
        for subscription in subscriptions:
            config = dict(subscription.response_decision_config or {})
            score_strategy_name = str(
                config.get(
                    "score_strategy",
                    "llm_relevance"
                    if subscription.response_decision_strategy == "best_match"
                    else subscription.response_decision_strategy,
                )
            )
            if score_strategy_name == "best_match":
                score_strategy_name = "llm_relevance"
            strategy = self.get_strategy(score_strategy_name)
            result = await strategy.decide(message_content, goal_context, config)
            score = (
                float(result.score)
                if result.score is not None
                else (1.0 if result.decision == "respond" else 0.0)
            )
            candidates.append((subscription, result, score))
        all_failed = all(result.error is not None for _, result, _score in candidates)
        winner: WorkspaceAgentDecisionConfig | None = None
        if not all_failed and candidates:
            ordered = sorted(
                candidates,
                key=lambda item: (-item[2], item[0].subscribed_at, item[0].agent_fqn),
            )
            winner = ordered[0][0]
        records: list[dict[str, Any]] = []
        for subscription, result, score in candidates:
            selected = winner is not None and subscription.id == winner.id
            rationale = result.rationale
            if selected:
                rationale = rationale or "Selected by best-match"
            elif winner is not None:
                rationale = f"not selected in best-match; winner was {winner.agent_fqn}"
            records.append(
                {
                    "workspace_id": workspace_id,
                    "goal_id": goal_id,
                    "message_id": message_id,
                    "agent_fqn": subscription.agent_fqn,
                    "strategy_name": "best_match",
                    "decision": "respond" if selected else "skip",
                    "score": score,
                    "matched_terms": list(result.matched_terms),
                    "rationale": rationale,
                    "error": result.error,
                }
            )
        await self._persist_records(session, records)
        return records

    async def _persist_records(self, session: AsyncSession, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        stmt = pg_insert(WorkspaceGoalDecisionRationale).values(records)
        stmt = stmt.on_conflict_do_nothing(index_elements=["message_id", "agent_fqn"])
        await session.execute(stmt)
        await session.flush()


def _message_tokens(message: str) -> list[str]:
    normalized = message.lower()
    tokens = re.findall(r"[a-z0-9_.*:-]+", normalized)
    return [normalized, *tokens]


def _extract_score(payload: Any) -> float:
    if isinstance(payload, dict):
        if "score" in payload:
            return float(payload["score"])
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            content = choices[0].get("message", {}).get("content")
            if isinstance(content, str):
                return _extract_score(json.loads(content))
    raise ValueError("score not present in LLM response")


def _extract_embedding(payload: Any) -> list[float]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list) and data:
            embedding = data[0].get("embedding")
            if isinstance(embedding, list):
                return [float(item) for item in embedding]
        embedding = payload.get("embedding")
        if isinstance(embedding, list):
            return [float(item) for item in embedding]
    raise ValueError("embedding not present in response")
