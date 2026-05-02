#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "apps/control-plane/src/platform"
DATABASE = SRC / "common/database.py"
CATALOG = SRC / "tenants/table_catalog.py"


def main() -> int:
    violations: list[str] = []
    if not _database_installs_global_criteria():
        violations.append(
            "apps/control-plane/src/platform/common/database.py does not install "
            "with_loader_criteria(TenantScopedMixin, ...)"
        )

    catalog_tables = _tenant_catalog_tables()
    for path in SRC.rglob("*.py"):
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in module.body:
            if not isinstance(node, ast.ClassDef):
                continue
            table_name = _class_table_name(node)
            if table_name not in catalog_tables:
                continue
            if _class_has_tenant_id(node):
                continue
            rel = path.relative_to(ROOT)
            violations.append(
                f"{rel}:{node.lineno} maps tenant-scoped table {table_name!r} "
                "without TenantScopedMixin or an explicit tenant_id column"
            )

    for path in SRC.rglob("repository.py"):
        violations.extend(_tenant_filter_opt_out_violations(path))

    if violations:
        print("Tenant filter coverage violations:")
        for violation in violations:
            print(f"  - {violation}")
        return 1
    print("Tenant filter coverage ok")
    return 0


def _database_installs_global_criteria() -> bool:
    text = DATABASE.read_text(encoding="utf-8")
    required = [
        "with_loader_criteria",
        "TenantScopedMixin",
        "tenant_filter_enabled",
        "_apply_tenant_filter_criteria",
    ]
    return all(snippet in text for snippet in required)


def _tenant_catalog_tables() -> set[str]:
    module = ast.parse(CATALOG.read_text(encoding="utf-8"), filename=str(CATALOG))
    for statement in module.body:
        if isinstance(statement, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == "TENANT_SCOPED_TABLES"
                for target in statement.targets
            ):
                return _literal_string_set(statement.value)
        if isinstance(statement, ast.AnnAssign):
            if (
                isinstance(statement.target, ast.Name)
                and statement.target.id == "TENANT_SCOPED_TABLES"
            ):
                if statement.value is None:
                    break
                return _literal_string_set(statement.value)
    raise SystemExit("TENANT_SCOPED_TABLES assignment not found")


def _tenant_filter_opt_out_violations(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    if "skip_tenant_criteria" not in source:
        return []
    allowed = "platform_router.py" in path.name or "/platform/" in source
    if allowed:
        return []
    rel = path.relative_to(ROOT)
    return [f"{rel} uses skip_tenant_criteria outside a platform-staff router"]


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
    if any(_base_name(base) == "TenantScopedMixin" for base in node.bases):
        return True
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


def _base_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


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
