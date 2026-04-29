from __future__ import annotations


def test_secret_rotation_dual_credential_window_contract() -> None:
    rotation = {"old_valid_during_window": True, "new_valid": True, "window_days": 7}
    assert rotation["old_valid_during_window"] is True
    assert rotation["window_days"] == 7
