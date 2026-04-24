from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ci.schema_diff import detect_breaking_changes, main


def _write_openapi(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _openapi_with_widget(widget_type: str = "string", *, required: bool = False) -> dict:
    schema: dict[str, object] = {
        "openapi": "3.1.0",
        "info": {"title": "Test", "version": "1.0.0"},
        "paths": {
            "/widgets": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Widget"}
                                }
                            },
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "Widget": {
                    "type": "object",
                    "properties": {
                        "name": {"type": widget_type},
                    },
                }
            }
        },
    }
    if required:
        schema["components"]["schemas"]["Widget"]["required"] = ["name"]
    return schema


def test_detect_breaking_changes_accepts_identical_documents(tmp_path: Path) -> None:
    previous = _openapi_with_widget()
    current = _openapi_with_widget()

    assert detect_breaking_changes(previous, current) == []

    previous_path = tmp_path / "previous.json"
    current_path = tmp_path / "current.json"
    _write_openapi(previous_path, previous)
    _write_openapi(current_path, current)

    assert main(["schema_diff.py", str(previous_path), str(current_path)]) == 0


def test_detect_breaking_changes_flags_type_change_without_breaking_marker(
    monkeypatch,
    tmp_path: Path,
) -> None:
    previous_path = tmp_path / "previous.json"
    current_path = tmp_path / "current.json"
    _write_openapi(previous_path, _openapi_with_widget("string"))
    _write_openapi(current_path, _openapi_with_widget("integer"))

    monkeypatch.delenv("GH_RELEASE_BODY", raising=False)
    assert main(["schema_diff.py", str(previous_path), str(current_path)]) == 1

    monkeypatch.setenv("GH_RELEASE_BODY", "BREAKING: rename widget contract")
    assert main(["schema_diff.py", str(previous_path), str(current_path)]) == 0


def test_detect_breaking_changes_flags_removed_path(tmp_path: Path) -> None:
    previous_path = tmp_path / "previous.json"
    current_path = tmp_path / "current.json"
    _write_openapi(previous_path, _openapi_with_widget())
    _write_openapi(
        current_path,
        {
            "openapi": "3.1.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {},
            "components": {"schemas": {}},
        },
    )

    assert main(["schema_diff.py", str(previous_path), str(current_path)]) == 1


def test_detect_breaking_changes_allows_new_optional_field(tmp_path: Path) -> None:
    previous = _openapi_with_widget()
    current = _openapi_with_widget()
    current["components"]["schemas"]["Widget"]["properties"]["nickname"] = {"type": "string"}

    previous_path = tmp_path / "previous.json"
    current_path = tmp_path / "current.json"
    _write_openapi(previous_path, previous)
    _write_openapi(current_path, current)

    assert detect_breaking_changes(previous, current) == []
    assert main(["schema_diff.py", str(previous_path), str(current_path)]) == 0
