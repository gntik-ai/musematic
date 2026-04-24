from __future__ import annotations

import json

from ci import normalize_govulncheck


def test_normalize_jsonl_skips_non_json_lines(tmp_path) -> None:
    raw = tmp_path / "govulncheck.jsonl"
    raw.write_text(
        "\n".join(
            [
                '{"config":{"protocol_version":"1.0.0"}}',
                "govulncheck: loading packages",
                '{"finding":{"osv":"GO-2024-0001","fixed_version":"v1.2.3"}}',
                '{"osv":{"id":"GO-2024-0002","details":"affected package"}}',
            ]
        ),
        encoding="utf-8",
    )

    payload, invalid_lines = normalize_govulncheck.normalize_jsonl(raw)

    assert invalid_lines == ["2: govulncheck: loading packages"]
    assert payload == {
        "vulns": [
            {"fixed_version": "v1.2.3", "id": "GO-2024-0001", "osv": "GO-2024-0001"},
            {"details": "affected package", "id": "GO-2024-0002"},
        ]
    }


def test_main_writes_normalized_json_and_invalid_log(tmp_path, capsys) -> None:
    raw = tmp_path / "govulncheck.jsonl"
    output = tmp_path / "govulncheck.json"
    invalid = tmp_path / "invalid.log"
    raw.write_text('not json\n{"finding":{"osv":"GO-2024-0001"}}\n', encoding="utf-8")

    result = normalize_govulncheck.main(
        [str(raw), "--output", str(output), "--invalid-output", str(invalid)]
    )

    assert result == 0
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "vulns": [{"id": "GO-2024-0001", "osv": "GO-2024-0001"}]
    }
    assert invalid.read_text(encoding="utf-8") == "1: not json\n"
    assert "skipped 1 non-JSON" in capsys.readouterr().err
