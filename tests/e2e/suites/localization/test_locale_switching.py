from __future__ import annotations

from pathlib import Path


def test_locale_catalogues_cover_supported_launch_locales() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    messages_dir = repo_root / "apps" / "web" / "messages"

    for locale in ("en", "es", "fr", "de", "ja", "zh-CN"):
        assert (messages_dir / f"{locale}.json").is_file()
