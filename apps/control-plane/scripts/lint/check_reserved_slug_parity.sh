#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"

python - "$repo_root" <<'PY'
from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
python_source = repo_root / "apps/control-plane/src/platform/tenants/reserved_slugs.py"
migration_source = repo_root / "apps/control-plane/migrations/versions/096_tenant_table_and_seed.py"
frontend_source = repo_root / "apps/web/components/features/admin/TenantProvisionForm.tsx"


def digest(values: set[str]) -> str:
    payload = json.dumps(sorted(values), separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def literal_strings(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "frozenset":
        if not node.args:
            return set()
        return literal_strings(node.args[0])
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        result: set[str] = set()
        for item in node.elts:
            if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                raise SystemExit("reserved slug collection must contain only string literals")
            result.add(item.value)
        return result
    raise SystemExit("reserved slug source must be a literal collection")


def python_reserved_slugs() -> set[str]:
    module = ast.parse(python_source.read_text(encoding="utf-8"), filename=str(python_source))
    for statement in module.body:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name) and target.id == "RESERVED_SLUGS":
                    return literal_strings(statement.value)
        if isinstance(statement, ast.AnnAssign):
            target = statement.target
            if isinstance(target, ast.Name) and target.id == "RESERVED_SLUGS":
                if statement.value is None:
                    break
                return literal_strings(statement.value)
    raise SystemExit("RESERVED_SLUGS assignment not found")


def migration_reserved_slugs(expected: set[str]) -> set[str]:
    text = migration_source.read_text(encoding="utf-8")
    array_match = re.search(r"ARRAY\[(?P<body>[^\]]+)\]", text, flags=re.DOTALL)
    if array_match:
        slugs = set(re.findall(r"'([^']+)'", array_match.group("body")))
        if slugs:
            return slugs

    module = ast.parse(text, filename=str(migration_source))
    for statement in module.body:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name) and target.id == "RESERVED_SLUGS":
                    return literal_strings(statement.value)
        if isinstance(statement, ast.AnnAssign):
            target = statement.target
            if isinstance(target, ast.Name) and target.id == "RESERVED_SLUGS":
                if statement.value is None:
                    break
                return literal_strings(statement.value)

    required_snippets = [
        "sorted(RESERVED_SLUGS)",
        "tenants_reserved_slug_check",
        "NEW.slug = ANY",
    ]
    missing = [snippet for snippet in required_snippets if snippet not in text]
    if missing:
        raise SystemExit(
            "migration 096 does not expose a verifiable reserved-slug trigger path: "
            + ", ".join(missing)
        )
    return expected


def frontend_reserved_slugs() -> set[str]:
    text = frontend_source.read_text(encoding="utf-8")
    match = re.search(
        r"TENANT_RESERVED_SLUGS\s*=\s*\[(?P<body>.*?)\]\s+as\s+const",
        text,
        flags=re.DOTALL,
    )
    if not match:
        raise SystemExit("TENANT_RESERVED_SLUGS const array not found in TenantProvisionForm.tsx")
    return set(re.findall(r'"([^"]+)"', match.group("body")))


python_slugs = python_reserved_slugs()
sources = {
    "reserved_slugs.py": python_slugs,
    "096_tenant_table_and_seed.py": migration_reserved_slugs(python_slugs),
    "TenantProvisionForm.tsx": frontend_reserved_slugs(),
}
digests = {source: digest(values) for source, values in sources.items()}

if len(set(digests.values())) != 1:
    for source, values in sources.items():
        print(f"{source}: {digests[source]} {sorted(values)}", file=sys.stderr)
    raise SystemExit("reserved slug sources diverged")

print(f"reserved slug parity ok: {next(iter(digests.values()))}")
PY
