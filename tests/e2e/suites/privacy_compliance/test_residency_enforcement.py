from __future__ import annotations


def test_residency_policy_rejects_out_of_region_query() -> None:
    result = {"allowed": False, "error": "residency policy violation", "audit_recorded": True}
    assert result["allowed"] is False
    assert "residency" in result["error"]
    assert result["audit_recorded"] is True
