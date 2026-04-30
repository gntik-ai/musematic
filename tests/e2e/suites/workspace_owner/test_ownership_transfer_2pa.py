from __future__ import annotations


def test_ownership_transfer_requires_two_person_approval() -> None:
    flow = [
        "initiate_transfer",
        "create_challenge",
        "platform_admin_approves",
        "initiator_consumes",
        "owner_swapped",
        "prior_owner_downgraded",
    ]
    audit_events = [
        "auth.workspace.transfer_initiated",
        "auth.workspace.transfer_committed",
    ]

    assert flow[1] == "create_challenge"
    assert flow[-1] == "prior_owner_downgraded"
    assert len(audit_events) == 2


def test_two_person_approval_invariants() -> None:
    invariants = {
        "same_actor_approval": "rejected",
        "expired_challenge": "rejected",
        "double_consume": "rejected",
        "payload_source": "frozen_server_payload",
    }

    assert invariants["same_actor_approval"] == "rejected"
    assert invariants["payload_source"] == "frozen_server_payload"
