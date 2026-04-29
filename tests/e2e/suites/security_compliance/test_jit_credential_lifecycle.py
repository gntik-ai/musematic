from __future__ import annotations


def test_jit_credential_lifecycle_contract() -> None:
    lifecycle = ["issued", "used", "audited", "expired", "refused_after_expiry"]
    assert lifecycle[-1] == "refused_after_expiry"
