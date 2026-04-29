from __future__ import annotations

from platform.common.tagging.label_expression.evaluator import evaluate
from platform.common.tagging.label_expression.parser import parse

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("expression", "labels", "expected"),
    [
        ("env=production", {"env": "production"}, True),
        ("env=production", {"env": "staging"}, False),
        ("env=production", {}, False),
        ("env!=production", {}, True),
        ("HAS env", {}, False),
        ("NOT HAS env", {}, True),
        ("env=production AND tier=critical", {"env": "production", "tier": "critical"}, True),
        ("env=production AND tier=critical", {"env": "production"}, False),
        ("env=production OR tier=critical", {"tier": "critical"}, True),
        ("NOT lifecycle=experimental", {}, True),
    ],
)
async def test_evaluator_applies_documented_semantics(
    expression: str,
    labels: dict[str, str],
    expected: bool,
) -> None:
    assert await evaluate(parse(expression), labels) is expected


@pytest.mark.asyncio
async def test_evaluator_agrees_with_node_oracle_for_representative_inputs() -> None:
    expressions = [
        "env=production",
        "env!=production",
        "HAS env",
        "NOT HAS env",
        "env=production AND tier=critical",
        "(env=production OR env=staging) AND NOT lifecycle=experimental",
    ]
    label_sets = [
        {},
        {"env": "production"},
        {"env": "staging"},
        {"env": "production", "tier": "critical"},
        {"env": "staging", "lifecycle": "experimental"},
    ]

    for expression in expressions:
        node = parse(expression)
        for labels in label_sets:
            assert await evaluate(node, labels) is node.evaluate(labels)
