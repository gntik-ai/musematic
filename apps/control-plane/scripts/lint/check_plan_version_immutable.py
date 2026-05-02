#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "apps/control-plane/src/platform"
ALLOWED = {
    Path("apps/control-plane/src/platform/billing/plans/repository.py"),
}


def main() -> int:
    violations: list[str] = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if rel in ALLOWED:
            continue
        source = path.read_text(encoding="utf-8")
        if "PlanVersion" not in source and "plan_versions" not in source:
            continue
        module = ast.parse(source, filename=str(path))
        for node in ast.walk(module):
            if _is_plan_version_update(node):
                violations.append(f"{rel}:{getattr(node, 'lineno', '?')} mutates PlanVersion")
        if "UPDATE plan_versions" in source:
            violations.append(f"{rel}: direct plan_versions SQL update")
    if violations:
        print("Plan-version immutability violations:")
        for violation in violations:
            print(f"  - {violation}")
        return 1
    print("Plan-version immutability guard ok")
    return 0


def _is_plan_version_update(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    return (
        isinstance(node.func, ast.Name)
        and node.func.id == "update"
        and any(_name(arg) == "PlanVersion" for arg in node.args)
    )


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


if __name__ == "__main__":
    raise SystemExit(main())
