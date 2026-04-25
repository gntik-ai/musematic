from __future__ import annotations

import json

from ci import normalize_sbom


def test_canonicalize_sbom_is_stable() -> None:
    left = '{"b": 2, "a": {"z": 1, "x": 0}}'
    right = json.dumps({"a": {"x": 0, "z": 1}, "b": 2}, indent=2)

    canonical = normalize_sbom.canonicalize_sbom(left)

    assert canonical == normalize_sbom.canonicalize_sbom(right)
    assert canonical == '{"a":{"x":0,"z":1},"b":2}'
    assert normalize_sbom.content_sha256(canonical) == normalize_sbom.content_sha256(
        normalize_sbom.canonicalize_sbom(right)
    )


def test_normalize_file_returns_canonical_content_and_hash(tmp_path) -> None:
    path = tmp_path / "sbom.json"
    path.write_text(
        '{"packages":[{"name":"a"}],"bomFormat":"CycloneDX"}', encoding="utf-8"
    )

    result = normalize_sbom.normalize_file(path)

    assert result["content"] == '{"bomFormat":"CycloneDX","packages":[{"name":"a"}]}'
    assert len(result["content_sha256"]) == 64
