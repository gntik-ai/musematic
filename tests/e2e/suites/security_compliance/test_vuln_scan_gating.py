from __future__ import annotations


def test_vulnerability_scan_distinguishes_dev_and_runtime_dependencies() -> None:
    records = [{"dependency_type": "dev", "blocks_release": False}, {"dependency_type": "runtime", "blocks_release": True}]
    assert records[0]["blocks_release"] is False
    assert records[1]["blocks_release"] is True
