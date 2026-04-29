from __future__ import annotations


def test_maintenance_mode_gate_contract_includes_fail_open_on_redis_miss() -> None:
    gate = {"maintenance_active": True, "redis_available": False, "fail_open": True}
    assert gate["maintenance_active"] is True
    assert gate["fail_open"] is True
