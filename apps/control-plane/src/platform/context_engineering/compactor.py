from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy
from platform.context_engineering.exceptions import BudgetExceededMinimumError
from platform.context_engineering.models import CompactionStrategyType, ContextSourceType
from platform.context_engineering.schemas import BudgetEnvelope, ContextElement
from typing import Any, ClassVar


class ContextCompactor:
    MINIMUM_VIABLE_SOURCES: ClassVar[set[ContextSourceType]] = {
        ContextSourceType.system_instructions,
    }

    def __init__(
        self,
        compressor: Callable[[ContextElement], Awaitable[ContextElement]] | None = None,
    ) -> None:
        self._compressor = compressor

    async def compact(
        self,
        elements: list[ContextElement],
        budget: BudgetEnvelope,
        strategies: list[CompactionStrategyType],
    ) -> tuple[list[ContextElement], list[dict[str, Any]]]:
        current = list(elements)
        if self._count_tokens(current) <= budget.max_tokens_step:
            return current, []

        minimum = self.minimum_viable_elements(current)
        minimum_tokens = self._count_tokens(minimum)
        if minimum_tokens > budget.max_tokens_step:
            raise BudgetExceededMinimumError(budget.max_tokens_step, minimum_tokens)

        actions: list[dict[str, Any]] = []
        for strategy in strategies:
            if self._count_tokens(current) <= budget.max_tokens_step:
                break
            if strategy is CompactionStrategyType.relevance_truncation:
                current, action = self._relevance_truncate(current, budget.max_tokens_step)
            elif strategy is CompactionStrategyType.priority_eviction:
                current, action = self._priority_evict(current, budget.max_tokens_step)
            elif strategy is CompactionStrategyType.semantic_deduplication:
                current, action = self._semantic_deduplicate(current)
            else:
                current, action = await self._hierarchical_compress(
                    current,
                    budget.max_tokens_step,
                )
            if action["tokens_saved"] > 0 or action["elements_removed"] > 0:
                actions.append(action)
        return current, actions

    def minimum_viable_elements(self, elements: list[ContextElement]) -> list[ContextElement]:
        if not elements:
            return []
        preserved = [
            element for element in elements if element.source_type in self.MINIMUM_VIABLE_SOURCES
        ]
        conversation_history = [
            element
            for element in elements
            if element.source_type is ContextSourceType.conversation_history
        ]
        if conversation_history:
            preserved.append(
                max(
                    conversation_history,
                    key=lambda element: (
                        element.provenance.timestamp,
                        str(element.id),
                    ),
                )
            )
        unique: dict[str, ContextElement] = {}
        for element in preserved:
            unique[str(element.id)] = element
        return list(unique.values())

    def _relevance_truncate(
        self,
        elements: list[ContextElement],
        target_tokens: int,
    ) -> tuple[list[ContextElement], dict[str, Any]]:
        preserved_ids = {str(element.id) for element in self.minimum_viable_elements(elements)}
        ordered = sorted(
            (element for element in elements if str(element.id) not in preserved_ids),
            key=lambda element: (
                float(element.metadata.get("relevance_score", 0.0)),
                element.priority,
                str(element.id),
            ),
        )
        current = list(elements)
        removed = 0
        saved = 0
        for candidate in ordered:
            if self._count_tokens(current) <= target_tokens:
                break
            current = [element for element in current if element.id != candidate.id]
            removed += 1
            saved += candidate.token_count
        return current, self._action(
            CompactionStrategyType.relevance_truncation,
            removed,
            saved,
        )

    def _priority_evict(
        self,
        elements: list[ContextElement],
        target_tokens: int,
    ) -> tuple[list[ContextElement], dict[str, Any]]:
        preserved_ids = {str(element.id) for element in self.minimum_viable_elements(elements)}
        ordered = sorted(
            (element for element in elements if str(element.id) not in preserved_ids),
            key=lambda element: (
                element.priority,
                -element.token_count,
                str(element.id),
            ),
        )
        current = list(elements)
        removed = 0
        saved = 0
        for candidate in ordered:
            if self._count_tokens(current) <= target_tokens:
                break
            current = [element for element in current if element.id != candidate.id]
            removed += 1
            saved += candidate.token_count
        return current, self._action(
            CompactionStrategyType.priority_eviction,
            removed,
            saved,
        )

    def _semantic_deduplicate(
        self,
        elements: list[ContextElement],
    ) -> tuple[list[ContextElement], dict[str, Any]]:
        seen: dict[str, ContextElement] = {}
        deduplicated: list[ContextElement] = []
        removed = 0
        saved = 0
        for element in elements:
            key = " ".join(element.content.lower().split())
            existing = seen.get(key)
            if existing is None:
                seen[key] = element
                deduplicated.append(element)
                continue
            removed += 1
            saved += element.token_count
            merged = list(existing.metadata.get("merged_origins", []))
            merged.append(element.provenance.origin)
            existing.metadata["merged_origins"] = merged
        return deduplicated, self._action(
            CompactionStrategyType.semantic_deduplication,
            removed,
            saved,
        )

    async def _hierarchical_compress(
        self,
        elements: list[ContextElement],
        target_tokens: int,
    ) -> tuple[list[ContextElement], dict[str, Any]]:
        current = list(elements)
        preserved_ids = {str(element.id) for element in self.minimum_viable_elements(elements)}
        saved = 0
        compressed = 0
        ordered = sorted(
            (
                element
                for element in current
                if str(element.id) not in preserved_ids and element.token_count > 1
            ),
            key=lambda element: (-element.token_count, element.priority, str(element.id)),
        )
        for element in ordered:
            if self._count_tokens(current) <= target_tokens:
                break
            replacement = await self._compress_element(element)
            saved += max(element.token_count - replacement.token_count, 0)
            compressed += 1
            current = [
                replacement if candidate.id == element.id else candidate for candidate in current
            ]
        return current, self._action(
            CompactionStrategyType.hierarchical_compression,
            compressed,
            saved,
        )

    async def _compress_element(self, element: ContextElement) -> ContextElement:
        if self._compressor is not None:
            return await self._compressor(element)
        shortened = max(1, element.token_count // 2)
        return element.model_copy(
            update={
                "content": element.content[: max(16, len(element.content) // 2)],
                "token_count": shortened,
                "metadata": {
                    **deepcopy(element.metadata),
                    "compressed": True,
                },
            }
        )

    def _count_tokens(self, elements: list[ContextElement]) -> int:
        return sum(element.token_count for element in elements)

    def _action(
        self,
        strategy: CompactionStrategyType,
        elements_removed: int,
        tokens_saved: int,
    ) -> dict[str, Any]:
        return {
            "strategy": strategy.value,
            "elements_removed": elements_removed,
            "tokens_saved": tokens_saved,
        }
