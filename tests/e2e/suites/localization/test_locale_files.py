from __future__ import annotations

import json
from pathlib import Path


def _flatten(payload: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in payload.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            keys.update(_flatten(value, name))
        else:
            keys.add(name)
    return keys


def test_locale_files_match_english_catalog_keys() -> None:
    messages = Path(__file__).resolve().parents[4] / "apps/web/messages"
    english = _flatten(json.loads((messages / "en.json").read_text(encoding="utf-8")))

    for locale_file in sorted(messages.glob("*.json")):
        keys = _flatten(json.loads(locale_file.read_text(encoding="utf-8")))
        assert english - keys == set(), locale_file.name
