#!/usr/bin/env python3
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLATFORM_DIR = ROOT / "apps/control-plane/src/platform"
ADAPTER = (
    PLATFORM_DIR
    / "privacy_compliance/cascade_adapters/postgresql_adapter.py"
)


def main() -> int:
    declared = _declared_tables()
    discovered = _discover_user_fk_tables()
    missing = sorted(discovered - declared)
    if missing:
        print("Missing privacy cascade coverage for tables:", file=sys.stderr)
        for table in missing:
            print(f"  - {table}", file=sys.stderr)
        return 1
    return 0


def _declared_tables() -> set[str]:
    module = ast.parse(ADAPTER.read_text())
    for node in module.body:
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == "USER_IDENTITY_COLUMNS"
                for target in node.targets
            ):
                value = ast.literal_eval(node.value)
                return set(value)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "USER_IDENTITY_COLUMNS"
        ):
            value = ast.literal_eval(node.value)
            return set(value)
    raise RuntimeError("USER_IDENTITY_COLUMNS not found")


def _discover_user_fk_tables() -> set[str]:
    tables: set[str] = set()
    for path in PLATFORM_DIR.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text()
        if 'ForeignKey("users.id' not in text and "ForeignKey('users.id" not in text:
            continue
        tables.update(_extract_user_fk_table_names(text))
    return tables


def _extract_user_fk_table_names(text: str) -> set[str]:
    module = ast.parse(text)
    tables: set[str] = set()
    for node in module.body:
        if not isinstance(node, ast.ClassDef):
            continue
        table_name = _class_table_name(node)
        if table_name is None:
            continue
        class_source = ast.get_source_segment(text, node) or ""
        if 'ForeignKey("users.id' in class_source or "ForeignKey('users.id" in class_source:
            tables.add(table_name)
    return tables


def _class_table_name(node: ast.ClassDef) -> str | None:
    for statement in node.body:
        value: ast.expr | None = None
        if isinstance(statement, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == "__tablename__"
                for target in statement.targets
            ):
                value = statement.value
        elif (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == "__tablename__"
        ):
            value = statement.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
    return None


if __name__ == "__main__":
    raise SystemExit(main())
