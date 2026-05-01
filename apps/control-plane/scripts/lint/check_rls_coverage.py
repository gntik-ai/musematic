#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "apps/control-plane/src/platform"
CATALOG = SRC / "tenants/table_catalog.py"
RLS_MIGRATION = ROOT / "apps/control-plane/migrations/versions/100_tenant_rls_policies.py"


def main() -> int:
    _assert_rls_migration_uses_catalog()
    catalog_tables = _tenant_catalog_tables()
    model_tables = _tenant_model_tables()
    missing = sorted(model_tables - catalog_tables)
    if missing:
        print("Tenant-scoped models are missing from TENANT_SCOPED_TABLES:")
        for table in missing:
            print(f"  - {table}")
        return 1
    print(f"RLS catalog coverage ok for {len(model_tables)} tenant-scoped model tables")
    return 0


def _assert_rls_migration_uses_catalog() -> None:
    text = RLS_MIGRATION.read_text(encoding="utf-8")
    required = [
        "from platform.tenants.table_catalog import TENANT_SCOPED_TABLES",
        "CREATE POLICY tenant_isolation",
        "ENABLE ROW LEVEL SECURITY",
        "FORCE ROW LEVEL SECURITY",
    ]
    missing = [snippet for snippet in required if snippet not in text]
    if missing:
        raise SystemExit(
            "migration 100 does not expose verifiable RLS coverage: " + ", ".join(missing)
        )


def _tenant_catalog_tables() -> set[str]:
    module = ast.parse(CATALOG.read_text(encoding="utf-8"), filename=str(CATALOG))
    for statement in module.body:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name) and target.id == "TENANT_SCOPED_TABLES":
                    return _literal_string_set(statement.value)
        if isinstance(statement, ast.AnnAssign):
            target = statement.target
            if isinstance(target, ast.Name) and target.id == "TENANT_SCOPED_TABLES":
                if statement.value is None:
                    break
                return _literal_string_set(statement.value)
    raise SystemExit("TENANT_SCOPED_TABLES assignment not found")


def _tenant_model_tables() -> set[str]:
    tables: set[str] = set()
    for path in SRC.glob("*/models.py"):
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in module.body:
            if not isinstance(node, ast.ClassDef):
                continue
            table_name = _class_table_name(node)
            if table_name is not None and _class_has_tenant_id(node):
                tables.add(table_name)
    return tables


def _class_table_name(node: ast.ClassDef) -> str | None:
    for statement in node.body:
        if not isinstance(statement, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "__tablename__"
            for target in statement.targets
        ):
            continue
        if isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
            return statement.value.value
    return None


def _class_has_tenant_id(node: ast.ClassDef) -> bool:
    for statement in node.body:
        if isinstance(statement, ast.AnnAssign):
            if isinstance(statement.target, ast.Name) and statement.target.id == "tenant_id":
                return True
        if isinstance(statement, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == "tenant_id"
                for target in statement.targets
            ):
                return True
    return False


def _literal_string_set(node: ast.AST) -> set[str]:
    if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        raise SystemExit("TENANT_SCOPED_TABLES must be a literal sequence")
    values: set[str] = set()
    for item in node.elts:
        if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
            raise SystemExit("TENANT_SCOPED_TABLES must contain only string literals")
        values.add(item.value)
    return values


if __name__ == "__main__":
    raise SystemExit(main())
