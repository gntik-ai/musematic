from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import UTC, datetime
from platform.context_engineering.models import ContextSourceType
from platform.context_engineering.schemas import ContextElement, ContextQualityScore
from typing import Final

DEFAULT_QUALITY_WEIGHTS: Final[dict[str, float]] = {
    "relevance": 1.0,
    "freshness": 1.0,
    "authority": 1.0,
    "contradiction_density": 1.0,
    "token_efficiency": 1.0,
    "task_brief_coverage": 1.0,
}


class QualityScorer:
    CONTRADICTION_TOKEN_GROUPS: Final[tuple[frozenset[str], ...]] = (
        frozenset({"approved", "denied"}),
        frozenset({"allow", "deny"}),
        frozenset({"allowed", "denied"}),
        frozenset({"success", "failed"}),
        frozenset({"resolved", "unresolved"}),
        frozenset({"open", "closed"}),
        frozenset({"active", "inactive"}),
        frozenset({"enabled", "disabled"}),
        frozenset({"yes", "no"}),
        frozenset({"true", "false"}),
    )

    SOURCE_AUTHORITY: Final[dict[ContextSourceType, float]] = {
        ContextSourceType.system_instructions: 1.0,
        ContextSourceType.tool_outputs: 0.9,
        ContextSourceType.workflow_state: 0.85,
        ContextSourceType.conversation_history: 0.8,
        ContextSourceType.reasoning_traces: 0.75,
        ContextSourceType.workspace_goal_history: 0.75,
        ContextSourceType.long_term_memory: 0.7,
        ContextSourceType.connector_payloads: 0.6,
        ContextSourceType.workspace_metadata: 0.5,
    }

    async def score(
        self,
        elements: list[ContextElement],
        task_brief: str,
        weights: dict[str, float] | None = None,
    ) -> ContextQualityScore:
        relevance = self._score_relevance(elements, task_brief)
        freshness = self._score_freshness(elements)
        authority = self._score_authority(elements)
        contradiction_density = self._score_contradiction_density(elements)
        token_efficiency = self._score_token_efficiency(elements)
        task_brief_coverage = self._score_task_brief_coverage(elements, task_brief)
        resolved_weights = dict(DEFAULT_QUALITY_WEIGHTS)
        resolved_weights.update(weights or {})
        total_weight = sum(max(value, 0.0) for value in resolved_weights.values()) or 1.0
        aggregate = (
            relevance * resolved_weights["relevance"]
            + freshness * resolved_weights["freshness"]
            + authority * resolved_weights["authority"]
            + contradiction_density * resolved_weights["contradiction_density"]
            + token_efficiency * resolved_weights["token_efficiency"]
            + task_brief_coverage * resolved_weights["task_brief_coverage"]
        ) / total_weight
        return ContextQualityScore(
            relevance=relevance,
            freshness=freshness,
            authority=authority,
            contradiction_density=contradiction_density,
            token_efficiency=token_efficiency,
            task_brief_coverage=task_brief_coverage,
            aggregate=max(0.0, min(1.0, aggregate)),
        )

    def score_element_relevance(self, element: ContextElement, task_brief: str) -> float:
        return self._overlap_ratio(self._keywords(task_brief), self._keywords(element.content))

    def _score_relevance(self, elements: list[ContextElement], task_brief: str) -> float:
        if not elements:
            return 0.0
        brief_keywords = self._keywords(task_brief)
        if not brief_keywords:
            return 1.0
        scores = [
            self._overlap_ratio(brief_keywords, self._keywords(element.content))
            for element in elements
        ]
        return sum(scores) / len(scores)

    def _score_freshness(self, elements: list[ContextElement]) -> float:
        if not elements:
            return 0.0
        now = datetime.now(UTC)
        scores = []
        for element in elements:
            age_seconds = max((now - element.provenance.timestamp).total_seconds(), 0.0)
            scores.append(math.exp(-(age_seconds / 86400.0)))
        return sum(scores) / len(scores)

    def _score_authority(self, elements: list[ContextElement]) -> float:
        if not elements:
            return 0.0
        scores = [self.SOURCE_AUTHORITY.get(element.source_type, 0.5) for element in elements]
        return sum(scores) / len(scores)

    def _score_contradiction_density(self, elements: list[ContextElement]) -> float:
        if not elements:
            return 0.0
        claims: dict[str, set[str]] = defaultdict(set)
        for element in elements:
            claim_key = str(element.metadata.get("claim_key") or self._claim_key(element.content))
            claims[claim_key].add(self._normalize_content(element.content))
        contradictory = sum(1 for values in claims.values() if self._claims_contradict(values))
        if not claims:
            return 1.0
        return max(0.0, 1.0 - (contradictory / len(claims)))

    def _score_token_efficiency(self, elements: list[ContextElement]) -> float:
        if not elements:
            return 0.0
        unique_units = {self._normalize_content(element.content) for element in elements}
        total_tokens = max(sum(element.token_count for element in elements), 1)
        score = len(unique_units) / max(total_tokens / 100.0, 1.0)
        return max(0.0, min(1.0, score))

    def _score_task_brief_coverage(
        self,
        elements: list[ContextElement],
        task_brief: str,
    ) -> float:
        brief_keywords = self._keywords(task_brief)
        if not brief_keywords:
            return 1.0
        covered = set()
        for element in elements:
            covered |= brief_keywords & self._keywords(element.content)
        return len(covered) / len(brief_keywords)

    def _keywords(self, value: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]{3,}", value.lower()))

    def _overlap_ratio(self, left: set[str], right: set[str]) -> float:
        if not left:
            return 1.0
        if not right:
            return 0.0
        return len(left & right) / len(left)

    def _claim_key(self, content: str) -> str:
        normalized = self._normalize_content(content)
        if ":" in normalized:
            return normalized.split(":", 1)[0]
        return normalized.split(" ", 1)[0]

    def _normalize_content(self, value: str) -> str:
        return " ".join(value.lower().split())

    def _claims_contradict(self, values: set[str]) -> bool:
        if len(values) <= 1:
            return False
        token_sets = [self._keywords(value) for value in values]
        for tokens in token_sets:
            for group in self.CONTRADICTION_TOKEN_GROUPS:
                if tokens & group and any(
                    (other & group) - (tokens & group) for other in token_sets
                ):
                    return True
        stripped = {self._strip_negation(value) for value in values}
        return len(stripped) == 1 and len(values) > 1

    def _strip_negation(self, value: str) -> str:
        tokens = [token for token in self._keywords(value) if token not in {"not", "no", "never"}]
        return " ".join(tokens)
