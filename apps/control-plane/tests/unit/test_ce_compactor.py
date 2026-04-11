from __future__ import annotations

from platform.context_engineering.compactor import ContextCompactor
from platform.context_engineering.exceptions import BudgetExceededMinimumError
from platform.context_engineering.models import CompactionStrategyType, ContextSourceType
from platform.context_engineering.schemas import BudgetEnvelope
from uuid import uuid4

import pytest

from tests.context_engineering_support import build_element


@pytest.mark.asyncio
async def test_compactor_relevance_truncation_preserves_minimum_viable_context() -> None:
    compactor = ContextCompactor()
    elements = [
        build_element(
            source_type=ContextSourceType.system_instructions,
            token_count=10,
            metadata={"relevance_score": 1.0},
        ),
        build_element(
            source_type=ContextSourceType.conversation_history,
            token_count=8,
            metadata={"relevance_score": 0.9},
        ),
        build_element(
            source_type=ContextSourceType.tool_outputs,
            token_count=30,
            metadata={"relevance_score": 0.1},
        ),
    ]

    compacted, actions = await compactor.compact(
        elements,
        BudgetEnvelope(max_tokens_step=20),
        [CompactionStrategyType.relevance_truncation],
    )

    assert sum(item.token_count for item in compacted) <= 20
    assert any(item.source_type is ContextSourceType.system_instructions for item in compacted)
    assert any(action["strategy"] == "relevance_truncation" for action in actions)


@pytest.mark.asyncio
async def test_compactor_priority_and_deduplication_reduce_payload() -> None:
    compactor = ContextCompactor()
    duplicate = build_element(content="same content", token_count=12)
    elements = [
        build_element(
            source_type=ContextSourceType.system_instructions,
            token_count=8,
            priority=100,
        ),
        duplicate,
        duplicate.model_copy(update={"id": __import__("uuid").uuid4(), "priority": 10}),
        build_element(content="low priority", token_count=15, priority=5),
    ]

    compacted, actions = await compactor.compact(
        elements,
        BudgetEnvelope(max_tokens_step=25),
        [
            CompactionStrategyType.semantic_deduplication,
            CompactionStrategyType.priority_eviction,
        ],
    )

    assert sum(item.token_count for item in compacted) <= 25
    assert {action["strategy"] for action in actions} >= {
        "semantic_deduplication",
        "priority_eviction",
    }


@pytest.mark.asyncio
async def test_compactor_raises_when_minimum_viable_context_exceeds_budget() -> None:
    compactor = ContextCompactor()
    elements = [
        build_element(source_type=ContextSourceType.system_instructions, token_count=30),
        build_element(source_type=ContextSourceType.conversation_history, token_count=25),
    ]

    with pytest.raises(BudgetExceededMinimumError):
        await compactor.compact(
            elements,
            BudgetEnvelope(max_tokens_step=10),
            [CompactionStrategyType.priority_eviction],
        )


@pytest.mark.asyncio
async def test_compactor_hierarchical_compression_and_default_compressor() -> None:
    compactor = ContextCompactor()
    original = build_element(
        source_type=ContextSourceType.tool_outputs,
        content="long content " * 8,
        token_count=16,
    )
    elements = [
        build_element(source_type=ContextSourceType.system_instructions, token_count=5),
        original,
    ]

    unchanged, no_actions = await compactor.compact(
        [build_element(token_count=1)],
        BudgetEnvelope(max_tokens_step=10),
        [CompactionStrategyType.hierarchical_compression],
    )
    compacted, actions = await compactor.compact(
        elements,
        BudgetEnvelope(max_tokens_step=13),
        [CompactionStrategyType.hierarchical_compression],
    )

    assert unchanged[0].token_count == 1
    assert no_actions == []
    assert compactor.minimum_viable_elements([]) == []
    assert sum(item.token_count for item in compacted) <= 13
    assert any(action["strategy"] == "hierarchical_compression" for action in actions)
    assert any(item.metadata.get("compressed") for item in compacted if item.id == original.id)


@pytest.mark.asyncio
async def test_compactor_respects_budget_after_priority_eviction_breaks() -> None:
    async def _compress(element):
        return element.model_copy(update={"token_count": 2, "metadata": {"custom": True}})

    compactor = ContextCompactor(compressor=_compress)
    duplicate = build_element(content="same content", token_count=12)
    elements = [
        build_element(source_type=ContextSourceType.system_instructions, token_count=4),
        build_element(source_type=ContextSourceType.conversation_history, token_count=4),
        duplicate.model_copy(update={"id": uuid4(), "priority": 1}),
        duplicate.model_copy(update={"id": uuid4(), "priority": 2}),
    ]

    compacted, actions = await compactor.compact(
        elements,
        BudgetEnvelope(max_tokens_step=10),
        [
            CompactionStrategyType.priority_eviction,
            CompactionStrategyType.hierarchical_compression,
        ],
    )

    assert sum(item.token_count for item in compacted) <= 10
    assert any(action["strategy"] == "priority_eviction" for action in actions)
