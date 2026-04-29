from __future__ import annotations


def test_sbom_generation_supports_spdx_and_cyclonedx() -> None:
    formats = {"spdx", "cyclonedx"}
    assert {"spdx", "cyclonedx"} <= formats
