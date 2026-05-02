#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

CHECKS = [
    (
        "apps/control-plane/src/platform/execution/service.py",
        "create_execution",
        "check_execution",
        "repository.create_execution(",
    ),
    (
        "apps/control-plane/src/platform/workspaces/service.py",
        "create_workspace",
        "check_workspace_create",
        "repo.create_workspace(",
    ),
    (
        "apps/control-plane/src/platform/registry/service.py",
        "transition_lifecycle",
        "check_agent_publish",
        "profile.status = request.target_status",
    ),
    (
        "apps/control-plane/src/platform/accounts/service.py",
        "accept_invitation",
        "check_user_invite",
        "create_user(",
    ),
    (
        "apps/control-plane/src/platform/common/clients/model_router.py",
        "complete",
        "check_model_tier",
        "_call_primary(",
    ),
]


def main() -> int:
    violations: list[str] = []
    for rel_path, function_name, quota_call, mutation_call in CHECKS:
        path = ROOT / rel_path
        source = path.read_text(encoding="utf-8")
        function_source = _function_source(path, source, function_name)
        quota_index = function_source.find(quota_call)
        mutation_index = function_source.find(mutation_call)
        if quota_index < 0:
            violations.append(f"{rel_path}:{function_name} missing {quota_call}")
            continue
        if mutation_index < 0:
            violations.append(f"{rel_path}:{function_name} missing mutation marker {mutation_call}")
            continue
        if quota_index > mutation_index:
            violations.append(f"{rel_path}:{function_name} calls {quota_call} after mutation")
    if violations:
        print("Quota enforcer coverage violations:")
        for violation in violations:
            print(f"  - {violation}")
        return 1
    print("Quota enforcer coverage ok")
    return 0


def _function_source(path: Path, source: str, function_name: str) -> str:
    module = ast.parse(source, filename=str(path))
    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            segment = ast.get_source_segment(source, node)
            if segment is None:
                break
            return segment
    raise RuntimeError(f"{path} has no function {function_name}")


if __name__ == "__main__":
    raise SystemExit(main())
