from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ASTNode(Protocol):
    def evaluate(self, labels: dict[str, str]) -> bool: ...

    def to_dict(self) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class EqualNode:
    key: str
    value: str

    def evaluate(self, labels: dict[str, str]) -> bool:
        return labels.get(self.key) == self.value

    def to_dict(self) -> dict[str, Any]:
        return {"type": "eq", "key": self.key, "value": self.value}


@dataclass(frozen=True, slots=True)
class NotEqualNode:
    key: str
    value: str

    def evaluate(self, labels: dict[str, str]) -> bool:
        return labels.get(self.key) != self.value

    def to_dict(self) -> dict[str, Any]:
        return {"type": "ne", "key": self.key, "value": self.value}


@dataclass(frozen=True, slots=True)
class HasKeyNode:
    key: str

    def evaluate(self, labels: dict[str, str]) -> bool:
        return self.key in labels

    def to_dict(self) -> dict[str, Any]:
        return {"type": "has", "key": self.key}


@dataclass(frozen=True, slots=True)
class AndNode:
    left: ASTNode
    right: ASTNode

    def evaluate(self, labels: dict[str, str]) -> bool:
        return self.left.evaluate(labels) and self.right.evaluate(labels)

    def to_dict(self) -> dict[str, Any]:
        return {"type": "and", "left": self.left.to_dict(), "right": self.right.to_dict()}


@dataclass(frozen=True, slots=True)
class OrNode:
    left: ASTNode
    right: ASTNode

    def evaluate(self, labels: dict[str, str]) -> bool:
        return self.left.evaluate(labels) or self.right.evaluate(labels)

    def to_dict(self) -> dict[str, Any]:
        return {"type": "or", "left": self.left.to_dict(), "right": self.right.to_dict()}


@dataclass(frozen=True, slots=True)
class NotNode:
    child: ASTNode

    def evaluate(self, labels: dict[str, str]) -> bool:
        return not self.child.evaluate(labels)

    def to_dict(self) -> dict[str, Any]:
        return {"type": "not", "child": self.child.to_dict()}


@dataclass(frozen=True, slots=True)
class GroupNode:
    child: ASTNode

    def evaluate(self, labels: dict[str, str]) -> bool:
        return self.child.evaluate(labels)

    def to_dict(self) -> dict[str, Any]:
        return {"type": "group", "child": self.child.to_dict()}


def node_from_dict(payload: dict[str, Any]) -> ASTNode:
    node_type = payload.get("type")
    if node_type == "eq":
        return EqualNode(key=str(payload["key"]), value=str(payload["value"]))
    if node_type == "ne":
        return NotEqualNode(key=str(payload["key"]), value=str(payload["value"]))
    if node_type == "has":
        return HasKeyNode(key=str(payload["key"]))
    if node_type == "and":
        return AndNode(
            left=node_from_dict(dict(payload["left"])),
            right=node_from_dict(dict(payload["right"])),
        )
    if node_type == "or":
        return OrNode(
            left=node_from_dict(dict(payload["left"])),
            right=node_from_dict(dict(payload["right"])),
        )
    if node_type == "not":
        return NotNode(child=node_from_dict(dict(payload["child"])))
    if node_type == "group":
        return GroupNode(child=node_from_dict(dict(payload["child"])))
    raise ValueError(f"unknown label-expression AST node type: {node_type}")
