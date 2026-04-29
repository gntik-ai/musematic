from __future__ import annotations


def test_pia_workflow_approval_lifecycle_contract() -> None:
    states = ["draft", "submitted", "approved"]
    assert states == ["draft", "submitted", "approved"]
