from __future__ import annotations

from platform.common.tagging.exceptions import LabelExpressionSyntaxError
from platform.common.tagging.label_expression.ast import AndNode, EqualNode, GroupNode, NotNode
from platform.common.tagging.label_expression.parser import parse, tokenize

import pytest


def test_tokenize_tracks_basic_tokens() -> None:
    tokens = tokenize("env=production AND NOT HAS deprecated")

    assert [(token.type, token.value, token.line, token.col) for token in tokens[:-1]] == [
        ("IDENT", "env", 1, 1),
        ("EQ", "=", 1, 4),
        ("IDENT", "production", 1, 5),
        ("AND", "AND", 1, 16),
        ("NOT", "NOT", 1, 20),
        ("HAS", "HAS", 1, 24),
        ("IDENT", "deprecated", 1, 28),
    ]


def test_parser_supports_precedence_and_grouping() -> None:
    node = parse("(env=production OR env=staging) AND NOT lifecycle=experimental")

    assert node.evaluate({"env": "production", "lifecycle": "stable"}) is True
    assert node.evaluate({"env": "staging"}) is True
    assert node.evaluate({"env": "production", "lifecycle": "experimental"}) is False
    assert node.evaluate({"env": "dev"}) is False


def test_parser_builds_expected_simple_ast_shape() -> None:
    node = parse("NOT (env=production AND HAS tier)")

    assert isinstance(node, NotNode)
    assert isinstance(node.child, GroupNode)
    assert isinstance(node.child.child, AndNode)
    assert isinstance(node.child.child.left, EqualNode)


@pytest.mark.parametrize(
    ("expression", "token"),
    [
        ("", "<end>"),
        ("env=production AND", "<end>"),
        ("env", "<end>"),
        ("1env=production", "1env"),
        ("env!production", "!"),
        ("HAS", "<end>"),
    ],
)
def test_parser_reports_structured_syntax_errors(expression: str, token: str) -> None:
    with pytest.raises(LabelExpressionSyntaxError) as exc_info:
        parse(expression)

    assert exc_info.value.line >= 1
    assert exc_info.value.col >= 1
    assert exc_info.value.token == token
    assert exc_info.value.message
