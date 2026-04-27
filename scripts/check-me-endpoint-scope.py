#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

SCAN_ROOT = Path("apps/control-plane/src/platform")
HTTP_METHODS = {"get", "put", "post", "patch", "delete", "options", "head"}


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    message: str


class ParseFailure(Exception):
    def __init__(self, path: Path, error: SyntaxError) -> None:
        super().__init__(f"{path}:{error.lineno}: {error.msg}")
        self.path = path
        self.error = error


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _has_me_segment(path: str) -> bool:
    parts = [part for part in path.split("/") if part]
    return "me" in parts


def _router_prefix_from_apirouter(node: ast.Call) -> str | None:
    if _call_name(node.func) != "APIRouter":
        return None
    for keyword in node.keywords:
        if keyword.arg == "prefix":
            return _literal_string(keyword.value)
    return ""


def _decorated_route_path(decorator: ast.AST) -> tuple[str, str] | None:
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    if not isinstance(func, ast.Attribute) or func.attr not in HTTP_METHODS:
        return None
    router_name = _call_name(func.value)
    path = _literal_string(decorator.args[0]) if decorator.args else ""
    return router_name, path or ""


def _argument_names(node: ast.AsyncFunctionDef | ast.FunctionDef) -> set[str]:
    return {
        arg.arg
        for arg in (
            list(node.args.posonlyargs)
            + list(node.args.args)
            + list(node.args.kwonlyargs)
        )
    }


def scan_python_file(path: Path) -> list[Violation]:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise ParseFailure(path, exc) from exc

    router_prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            prefix = _router_prefix_from_apirouter(node.value)
            if prefix is None:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    router_prefixes[target.id] = prefix

    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for decorator in node.decorator_list:
            route = _decorated_route_path(decorator)
            if route is None:
                continue
            router_name, route_path = route
            router_prefix = router_prefixes.get(router_name, "")
            full_path = f"{router_prefix.rstrip('/')}/{route_path.lstrip('/')}"
            if not (_has_me_segment(router_prefix) or _has_me_segment(route_path) or _has_me_segment(full_path)):
                continue
            if "user_id" in _argument_names(node):
                violations.append(
                    Violation(
                        path=path,
                        line=node.lineno,
                        message=(
                            f"/me endpoint handler '{node.name}' declares forbidden "
                            "user_id parameter"
                        ),
                    )
                )
    return violations


def scan(root: Path) -> list[Violation]:
    base = root.resolve() / SCAN_ROOT
    if not base.exists():
        return []
    violations: list[Violation] = []
    for path in base.rglob("*.py"):
        if path.is_file():
            violations.extend(scan_python_file(path))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reject /me endpoint handlers that accept user_id request parameters."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    try:
        violations = scan(args.root)
    except ParseFailure as exc:
        print(exc, file=sys.stderr)
        return 2

    for violation in violations:
        print(f"{violation.path}:{violation.line}: {violation.message}")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
