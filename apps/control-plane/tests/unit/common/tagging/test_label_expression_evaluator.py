from __future__ import annotations

import asyncio
from collections.abc import Sequence
from platform.common.tagging.label_expression.evaluator import evaluate
from platform.common.tagging.label_expression.parser import parse

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

type Expression = Sequence[object]

_KEYS = ("env", "tier", "lifecycle", "team")
_VALUES = ("production", "staging", "critical", "experimental", "finance-ops")


def _label_dicts() -> st.SearchStrategy[dict[str, str]]:
    return st.dictionaries(
        st.sampled_from(_KEYS),
        st.sampled_from(_VALUES),
        max_size=len(_KEYS),
    )


def _expressions() -> st.SearchStrategy[Expression]:
    terminals = st.one_of(
        st.tuples(st.just("eq"), st.sampled_from(_KEYS), st.sampled_from(_VALUES)),
        st.tuples(st.just("ne"), st.sampled_from(_KEYS), st.sampled_from(_VALUES)),
        st.tuples(st.just("has"), st.sampled_from(_KEYS)),
    )
    return st.recursive(
        terminals,
        lambda children: st.one_of(
            st.tuples(st.just("not"), children),
            st.tuples(st.just("and"), children, children),
            st.tuples(st.just("or"), children, children),
        ),
        max_leaves=8,
    )


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


@settings(max_examples=10_000)
@given(expression=_expressions(), labels=_label_dicts())
def test_evaluator_agrees_with_independent_oracle_property(
    expression: Expression,
    labels: dict[str, str],
) -> None:
    rendered = _render(expression)

    assert asyncio.run(evaluate(parse(rendered), labels)) is _oracle(expression, labels)


def _render(expression: Expression) -> str:
    operator = expression[0]
    if operator == "eq":
        return f"{expression[1]}={expression[2]}"
    if operator == "ne":
        return f"{expression[1]}!={expression[2]}"
    if operator == "has":
        return f"HAS {expression[1]}"
    if operator == "not":
        return f"NOT ({_render(expression[1])})"
    if operator == "and":
        return f"({_render(expression[1])}) AND ({_render(expression[2])})"
    if operator == "or":
        return f"({_render(expression[1])}) OR ({_render(expression[2])})"
    raise AssertionError(f"unknown expression operator: {operator}")


def _oracle(expression: Expression, labels: dict[str, str]) -> bool:
    operator = expression[0]
    if operator == "eq":
        return labels.get(str(expression[1])) == str(expression[2])
    if operator == "ne":
        return labels.get(str(expression[1])) != str(expression[2])
    if operator == "has":
        return str(expression[1]) in labels
    if operator == "not":
        return not _oracle(expression[1], labels)
    if operator == "and":
        return _oracle(expression[1], labels) and _oracle(expression[2], labels)
    if operator == "or":
        return _oracle(expression[1], labels) or _oracle(expression[2], labels)
    raise AssertionError(f"unknown expression operator: {operator}")
