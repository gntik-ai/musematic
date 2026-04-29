from __future__ import annotations

from pathlib import Path


def test_pwa_manifest_declares_installability_metadata() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    manifest = (repo_root / "apps" / "web" / "app" / "manifest.ts").read_text(
        encoding="utf-8",
    )

    assert "display: \"standalone\"" in manifest
    assert "start_url: \"/home\"" in manifest
    assert "musematic-maskable-512.png" in manifest
