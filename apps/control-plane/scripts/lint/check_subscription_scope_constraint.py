#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "apps/control-plane/src/platform"
ALLOWED = {
    Path("apps/control-plane/src/platform/billing/subscriptions/repository.py"),
}


def main() -> int:
    violations: list[str] = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if rel in ALLOWED:
            continue
        source = path.read_text(encoding="utf-8")
        if "subscriptions" not in source and "Subscription" not in source:
            continue
        module = ast.parse(source, filename=str(path))
        imports_billing_subscription = "billing.subscriptions.models import Subscription" in source
        for node in ast.walk(module):
            if imports_billing_subscription and _is_direct_subscription_mutation(node):
                line = getattr(node, "lineno", "?")
                violations.append(f"{rel}:{line} direct subscriptions write")
        if "INSERT INTO subscriptions" in source or "UPDATE subscriptions" in source:
            violations.append(f"{rel}: direct subscriptions SQL")
    if violations:
        print("Subscription scope guard violations:")
        for violation in violations:
            print(f"  - {violation}")
        return 1
    print("Subscription scope guard ok")
    return 0


def _is_direct_subscription_mutation(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name) and node.func.id in {"insert", "update"}:
        return any(_name(arg) == "Subscription" for arg in node.args)
    if isinstance(node.func, ast.Name) and node.func.id == "Subscription":
        return True
    return False


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


if __name__ == "__main__":
    raise SystemExit(main())
