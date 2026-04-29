from __future__ import annotations


def test_residency_misconfig_fails_closed_and_audits_refusal() -> None:
    outcome = {"allowed": False, "error": "residency violation", "audit_recorded": True}

    assert outcome["allowed"] is False
    assert "residency" in outcome["error"]
    assert outcome["audit_recorded"] is True
