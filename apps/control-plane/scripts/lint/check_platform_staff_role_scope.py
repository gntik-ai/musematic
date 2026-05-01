#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "apps/control-plane/src/platform"
ALLOWED_DEFINITION = Path("apps/control-plane/src/platform/common/database.py")


def main() -> int:
    violations: list[str] = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(ROOT)
        source = path.read_text(encoding="utf-8")
        if not _references_platform_staff_session(source):
            continue
        if rel == ALLOWED_DEFINITION or _is_platform_router(path, source):
            continue
        module = ast.parse(source, filename=str(path))
        for node in ast.walk(module):
            if _is_platform_staff_name(node):
                violations.append(f"{rel}:{node.lineno} references get_platform_staff_session")

    if violations:
        print("Platform-staff session references outside /api/v1/platform routers:")
        for violation in violations:
            print(f"  - {violation}")
        return 1
    print("Platform-staff session scope ok")
    return 0


def _references_platform_staff_session(source: str) -> bool:
    return "get_platform_staff_session" in source


def _is_platform_router(path: Path, source: str) -> bool:
    if path.name == "platform_router.py":
        return True
    return 'prefix="/api/v1/platform' in source or "prefix='/api/v1/platform" in source


def _is_platform_staff_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "get_platform_staff_session"


if __name__ == "__main__":
    raise SystemExit(main())
