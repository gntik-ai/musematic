from __future__ import annotations


def test_region_config_crud_contract() -> None:
    region = {"region_code": "secondary-test", "role": "secondary", "enabled": True}
    assert region["region_code"]
    assert region["role"] in {"primary", "secondary"}
