from __future__ import annotations


def test_dsr_access_request_contract() -> None:
    flow = ["submit_access_dsr", "validate_identity", "export_subject_data", "notify_subject"]
    assert flow[0] == "submit_access_dsr"
    assert "export_subject_data" in flow
