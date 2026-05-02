from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CONTROL_PLANE = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (CONTROL_PLANE / relative).read_text(encoding="utf-8")


def test_setup_steps_after_credentials_require_verified_mfa() -> None:
    source = _read("src/platform/accounts/setup_router.py")
    tree = ast.parse(source)
    handlers = {
        node.name: ast.unparse(node)
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name in {"step_workspace", "step_invitations", "complete_setup"}
    }

    assert set(handlers) == {"step_workspace", "step_invitations", "complete_setup"}
    for body in handlers.values():
        assert "await _require_setup_mfa(user, auth_service)" in body

    guard = source.split("async def _require_setup_mfa", maxsplit=1)[1]
    assert 'assert_role_mfa_requirement("tenant_admin", user, auth_service.repository)' in guard
    assert "accounts_setup_mfa_skip_attempt_total.inc()" in guard
