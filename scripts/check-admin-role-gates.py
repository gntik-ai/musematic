#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
from pathlib import Path

HTTP_METHODS = {"delete", "get", "patch", "post", "put"}
ROLE_GATES = {"require_admin", "require_superadmin"}
ROUTER_ROOT = Path("apps/control-plane/src/platform/admin/routers")


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
        if _call_name(node.func) == "Depends" and node.args:
            return _contains_role_gate(node.args[0])
        return any(_contains_role_gate(child) for child in ast.iter_child_nodes(node))
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return any(_contains_role_gate(element) for element in node.elts)
    return any(_contains_role_gate(child) for child in ast.iter_child_nodes(node))


def _is_route_decorator(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _call_name(node.func) in HTTP_METHODS


def _decorator_has_gate(decorator: ast.Call) -> bool:
    return any(
        keyword.arg == "dependencies" and _contains_role_gate(keyword.value)
        for keyword in decorator.keywords
    )


def _signature_has_gate(function: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    defaults = [*function.args.defaults, *function.args.kw_defaults]
    return any(default is not None and _contains_role_gate(default) for default in defaults)


def missing_role_gates(path: Path) -> list[tuple[int, str]]:
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
        if _signature_has_gate(node):
            continue
        if any(
            _decorator_has_gate(decorator)
            for decorator in route_decorators
            if isinstance(decorator, ast.Call)
        ):
            continue
        missing.append((node.lineno, node.name))
    return missing


def router_files(root: Path) -> list[Path]:
    directory = root / ROUTER_ROOT
    if not directory.exists():
        return []
    return sorted(path for path in directory.glob("*.py") if path.name != "__init__.py")


def scan(root: Path) -> list[str]:
    failures: list[str] = []
    for path in router_files(root):
        for line, name in missing_role_gates(path):
            failures.append(f"{path.relative_to(root)}:{line}: {name} missing admin role gate")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check platform admin router endpoints have explicit role gates."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    failures = scan(args.root.resolve())
    for failure in failures:
        print(failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
