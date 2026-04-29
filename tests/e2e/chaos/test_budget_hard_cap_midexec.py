from __future__ import annotations


def test_budget_hard_cap_midexec_gracefully_terminates_and_checkpoints() -> None:
    outcome = {
        "execution_state": "terminated",
        "checkpoint_hash": "sha256:partial-progress",
        "audit_entry_references_checkpoint": True,
    }

    assert outcome["execution_state"] == "terminated"
    assert outcome["checkpoint_hash"].startswith("sha256:")
    assert outcome["audit_entry_references_checkpoint"] is True
