from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CONTROL_PLANE = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (CONTROL_PLANE / relative).read_text(encoding="utf-8")


def test_signup_adjacent_handlers_gate_before_business_logic() -> None:
    source = _read("src/platform/accounts/router.py")
    tree = ast.parse(source)
    handlers = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name in {"register", "verify_email", "resend_verification"}
    }

    assert set(handlers) == {"register", "verify_email", "resend_verification"}
    for handler in handlers.values():
        first_statements = "\n".join(ast.unparse(item) for item in handler.body[:2])
        assert "_signup_tenant_gate(request)" in first_statements
        assert "return gated" in first_statements
        assert first_statements.index("_signup_tenant_gate(request)") < first_statements.index(
            "return gated"
        )


def test_signup_gate_reuses_canonical_opaque_404_helper_for_all_non_default_tenants() -> None:
    source = _read("src/platform/accounts/router.py")
    gate = source.split("def _signup_tenant_gate", maxsplit=1)[1].split(
        "@router.post", maxsplit=1
    )[0]

    assert 'getattr(tenant, "kind", "default") == "default"' in gate
    assert "return _build_opaque_404_response()" in gate
