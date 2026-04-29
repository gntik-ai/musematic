#!/usr/bin/env python3
from __future__ import annotations

import ast
import sys
from pathlib import Path

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
ROLE_GATES = {"require_admin", "require_superadmin"}


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return None


def _contains_role_gate(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id in ROLE_GATES
    if isinstance(node, ast.Call):
        callee = _call_name(node.func)
        if callee == "Depends" and node.args:
            return _contains_role_gate(node.args[0])
        return any(_contains_role_gate(child) for child in ast.iter_child_nodes(node))
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return any(_contains_role_gate(element) for element in node.elts)
    return any(_contains_role_gate(child) for child in ast.iter_child_nodes(node))


def _is_route_decorator(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    method = _call_name(node.func)
    return method in HTTP_METHODS


def _decorator_has_gate(decorator: ast.Call) -> bool:
    for keyword in decorator.keywords:
        if keyword.arg == "dependencies" and _contains_role_gate(keyword.value):
            return True
    return False


def _signature_has_gate(function: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    defaults = [*function.args.defaults, *function.args.kw_defaults]
    return any(default is not None and _contains_role_gate(default) for default in defaults)


def _missing_role_gates(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    missing: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue

        route_decorators = [
            decorator for decorator in node.decorator_list if _is_route_decorator(decorator)
        ]
        if not route_decorators:
            continue

        decorator_has_gate = any(
            _decorator_has_gate(decorator)
            for decorator in route_decorators
            if isinstance(decorator, ast.Call)
        )
        if _signature_has_gate(node) or decorator_has_gate:
            continue

        missing.append((node.lineno, node.name))

    return missing


def _router_files(root: Path) -> list[Path]:
    platform_root = root / "src" / "platform"
    files = list(platform_root.glob("*/admin_router.py"))
    files.extend((platform_root / "admin").glob("*_router.py"))
    return sorted(set(files))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    failures: list[str] = []

    for path in _router_files(root):
        for line, name in _missing_role_gates(path):
            failures.append(f"{path.relative_to(root)}:{line}: {name} missing admin role gate")

    if failures:
        print("Admin role-gate lint failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
