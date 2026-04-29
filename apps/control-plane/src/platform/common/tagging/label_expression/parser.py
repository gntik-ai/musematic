from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from platform.common.tagging.constants import LABEL_KEY_PATTERN, MAX_LABEL_VALUE_LEN
from platform.common.tagging.exceptions import LabelExpressionSyntaxError
from platform.common.tagging.label_expression.ast import (
    AndNode,
    ASTNode,
    EqualNode,
    GroupNode,
    HasKeyNode,
    NotEqualNode,
    NotNode,
    OrNode,
)
from typing import NoReturn

KEYWORDS = {"AND", "OR", "NOT", "HAS"}


@dataclass(frozen=True, slots=True)
class Token:
    type: str
    value: str
    line: int
    col: int


def tokenize(expression: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0
    line = 1
    col = 1

    while index < len(expression):
        char = expression[index]
        if char in {" ", "\t", "\r"}:
            index += 1
            col += 1
            continue
        if char == "\n":
            index += 1
            line += 1
            col = 1
            continue
        if char == "(":
            tokens.append(Token("LPAREN", char, line, col))
            index += 1
            col += 1
            continue
        if char == ")":
            tokens.append(Token("RPAREN", char, line, col))
            index += 1
            col += 1
            continue
        if char == "=":
            tokens.append(Token("EQ", char, line, col))
            index += 1
            col += 1
            continue
        if char == "!":
            if index + 1 < len(expression) and expression[index + 1] == "=":
                tokens.append(Token("NE", "!=", line, col))
                index += 2
                col += 2
                continue
            raise LabelExpressionSyntaxError(line, col, char, "expected != operator")

        start_index = index
        start_col = col
        while index < len(expression):
            current = expression[index]
            if current.isspace() or current in {"(", ")", "=", "!"}:
                break
            index += 1
            col += 1
        value = expression[start_index:index]
        if not value:
            raise LabelExpressionSyntaxError(line, col, char, "unexpected character")
        keyword = value.upper()
        token_type = keyword if keyword in KEYWORDS else "IDENT"
        tokens.append(Token(token_type, value, line, start_col))

    tokens.append(Token("EOF", "<end>", line, col))
    return tokens


def parse(expression_or_tokens: str | Sequence[Token]) -> ASTNode:
    tokens = tokenize(expression_or_tokens) if isinstance(expression_or_tokens, str) else list(
        expression_or_tokens
    )
    parser = _Parser(tokens)
    return parser.parse()


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.position = 0

    def parse(self) -> ASTNode:
        if self._current().type == "EOF":
            self._fail(self._current(), "expression must be non-empty")
        node = self._parse_or()
        if self._current().type != "EOF":
            self._fail(self._current(), "unexpected token after expression")
        return node

    def _parse_or(self) -> ASTNode:
        node = self._parse_and()
        while self._match("OR"):
            node = OrNode(left=node, right=self._parse_and())
        return node

    def _parse_and(self) -> ASTNode:
        node = self._parse_unary()
        while self._match("AND"):
            node = AndNode(left=node, right=self._parse_unary())
        return node

    def _parse_unary(self) -> ASTNode:
        if self._match("NOT"):
            return NotNode(child=self._parse_unary())
        return self._parse_primary()

    def _parse_primary(self) -> ASTNode:
        if self._match("LPAREN"):
            node = self._parse_or()
            self._consume("RPAREN", "expected closing parenthesis")
            return GroupNode(child=node)

        if self._match("HAS"):
            key = self._consume("IDENT", "expected label key after HAS")
            self._validate_key(key)
            return HasKeyNode(key.value)

        key = self._consume("IDENT", "expected label key or HAS expression")
        self._validate_key(key)
        operator = self._current()
        if self._match("EQ"):
            value = self._consume("IDENT", "expected label value after =")
            self._validate_value(value)
            return EqualNode(key=key.value, value=value.value)
        if self._match("NE"):
            value = self._consume("IDENT", "expected label value after !=")
            self._validate_value(value)
            return NotEqualNode(key=key.value, value=value.value)
        self._fail(operator, "expected = or != after label key")

    def _match(self, token_type: str) -> bool:
        if self._current().type != token_type:
            return False
        self.position += 1
        return True

    def _consume(self, token_type: str, message: str) -> Token:
        token = self._current()
        if token.type != token_type:
            self._fail(token, message)
        self.position += 1
        return token

    def _current(self) -> Token:
        return self.tokens[self.position]

    @staticmethod
    def _validate_key(token: Token) -> None:
        if LABEL_KEY_PATTERN.fullmatch(token.value) is None:
            raise LabelExpressionSyntaxError(
                token.line,
                token.col,
                token.value,
                "label key must match ^[a-zA-Z][a-zA-Z0-9._-]*$",
            )

    @staticmethod
    def _validate_value(token: Token) -> None:
        if not token.value or len(token.value) > MAX_LABEL_VALUE_LEN:
            raise LabelExpressionSyntaxError(
                token.line,
                token.col,
                token.value,
                f"label value must be 1-{MAX_LABEL_VALUE_LEN} characters",
            )

    @staticmethod
    def _fail(token: Token, message: str) -> NoReturn:
        raise LabelExpressionSyntaxError(token.line, token.col, token.value, message)
