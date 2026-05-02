from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CONTROL_PLANE = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (CONTROL_PLANE / relative).read_text(encoding="utf-8")


def test_signup_gate_has_no_audit_chain_or_special_blocked_logging_side_effect() -> None:
    source = _read("src/platform/accounts/router.py")
    gate = source.split("def _signup_tenant_gate", maxsplit=1)[1].split(
        "@router.post", maxsplit=1
    )[0]

    assert "audit" not in gate.lower()
    assert "logger" not in gate.lower()
    assert "log" not in gate.lower()
    assert "blocked" not in gate.lower()
    assert "_build_opaque_404_response()" in gate
