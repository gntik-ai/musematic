#!/usr/bin/env python3
from __future__ import annotations

import ast
import sys
from pathlib import Path

SENSITIVE_TOKENS = ("password", "secret", "password_file")


def _is_logger_call(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id in {"LOGGER", "logger"}
    )


def _references_sensitive_value(node: ast.AST) -> bool:
    for child in ast.walk(node):
        name_is_sensitive = isinstance(child, ast.Name) and any(
            token in child.id.lower() for token in SENSITIVE_TOKENS
        )
        if name_is_sensitive:
            return True
        if isinstance(child, ast.Attribute) and any(
            token in child.attr.lower() for token in SENSITIVE_TOKENS
        ):
            return True
    return False


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    path = root / "src" / "platform" / "admin" / "bootstrap.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    failures: list[str] = []

    for node in ast.walk(tree):
        sensitive_logger_call = (
            isinstance(node, ast.Call)
            and _is_logger_call(node)
            and _references_sensitive_value(node)
        )
        if sensitive_logger_call:
            failures.append(
                f"{path.relative_to(root)}:{node.lineno}: "
                "logger call references password/secret data"
            )

    if failures:
        print("Bootstrap secret-log lint failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
