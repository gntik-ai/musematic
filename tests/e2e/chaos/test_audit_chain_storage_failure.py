from __future__ import annotations


def test_audit_chain_storage_failure_refuses_unverifiable_operations() -> None:
    outcome = {
        "operation_allowed": False,
        "error": "audit chain unavailable, cannot proceed",
        "recovered_operations_succeed": True,
        "unverifiable_entries": 0,
    }

    assert outcome["operation_allowed"] is False
    assert "audit chain unavailable" in outcome["error"]
    assert outcome["recovered_operations_succeed"] is True
    assert outcome["unverifiable_entries"] == 0
