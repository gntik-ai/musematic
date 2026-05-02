from __future__ import annotations

import ast
from pathlib import Path

ROUTER = Path("src/platform/accounts/router.py")
SIGNUP_HANDLERS = {"register", "verify_email", "resend_verification"}


def main() -> None:
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    handlers = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name in SIGNUP_HANDLERS
    }
    missing = SIGNUP_HANDLERS - handlers.keys()
    if missing:
        raise SystemExit(f"missing signup handlers: {', '.join(sorted(missing))}")

    failures = [name for name, node in handlers.items() if not _has_initial_gate(node)]
    if failures:
        raise SystemExit(
            "signup handlers must call _signup_tenant_gate(request) before business logic: "
            + ", ".join(sorted(failures))
        )


def _has_initial_gate(node: ast.AsyncFunctionDef) -> bool:
    body = list(node.body)
    if not body:
        return False
    first = body[0]
    second = body[1] if len(body) > 1 else None
    if not (
        isinstance(first, ast.Assign)
        and len(first.targets) == 1
        and isinstance(first.targets[0], ast.Name)
        and first.targets[0].id == "gated"
        and isinstance(first.value, ast.Call)
        and isinstance(first.value.func, ast.Name)
        and first.value.func.id == "_signup_tenant_gate"
    ):
        return False
    if not first.value.args or not isinstance(first.value.args[0], ast.Name):
        return False
    if first.value.args[0].id != "request":
        return False
    return isinstance(second, ast.If) and isinstance(second.test, ast.Compare)


if __name__ == "__main__":
    main()
