from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path("src/platform/accounts")

MUTATING_METHODS = {
    ROOT / "service.py": {"_complete_default_signup"},
    ROOT / "onboarding.py": {"advance_step", "dismiss", "relaunch"},
    ROOT / "first_admin_invite.py": {"issue", "consume", "resend", "record_step"},
    ROOT / "memberships.py": {"list_for_user"},
}


def main() -> None:
    failures: list[str] = []
    for path, method_names in MUTATING_METHODS.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        methods = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name in method_names
        }
        for method_name in sorted(method_names):
            method = methods.get(method_name)
            if method is None:
                failures.append(f"{path}:{method_name} missing")
                continue
            if not _calls_audit_append(method):
                failures.append(f"{path}:{method_name} missing audit append")
    if failures:
        raise SystemExit("UPD-048 audit coverage failed:\n" + "\n".join(failures))


def _calls_audit_append(node: ast.AsyncFunctionDef) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and child.attr == "append":
            return True
        if isinstance(child, ast.Attribute) and child.attr in {
            "_append_audit",
            "_append_setup_audit",
        }:
            return True
        if isinstance(child, ast.Name) and child.id in {"_append_audit", "_append_setup_audit"}:
            return True
    return False


if __name__ == "__main__":
    main()
