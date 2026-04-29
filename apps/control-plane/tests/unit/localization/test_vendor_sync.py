from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from platform.localization.tooling import vendor_sync

import pytest


class FakeResponse(io.BytesIO):
    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


async def test_vendor_sync_skips_when_token_is_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status = await vendor_sync.sync_lokalise_catalogues(
        project_id="project-1",
        token_ref=vendor_sync.DEFAULT_TOKEN_REF,
        messages_dir=tmp_path / "messages",
        secrets_file=str(tmp_path / "missing-secrets.json"),
    )

    assert status == 0
    assert "vendor API token is not configured" in capsys.readouterr().out


async def test_vendor_sync_skips_when_project_id_is_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secrets_file = tmp_path / "secrets.json"
    secrets_file.write_text(
        json.dumps({vendor_sync.DEFAULT_TOKEN_REF: "vendor-token"}),
        encoding="utf-8",
    )

    status = await vendor_sync.sync_lokalise_catalogues(
        project_id="",
        token_ref=vendor_sync.DEFAULT_TOKEN_REF,
        messages_dir=tmp_path / "messages",
        secrets_file=str(secrets_file),
    )

    assert status == 0
    assert "LOKALISE_PROJECT_ID is not configured" in capsys.readouterr().out


async def test_vendor_sync_downloads_and_copies_non_english_catalogues(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secrets_file = tmp_path / "secrets.json"
    secrets_file.write_text(
        json.dumps({vendor_sync.DEFAULT_TOKEN_REF: "vendor-token"}),
        encoding="utf-8",
    )
    calls: list[tuple[str, str]] = []

    def fake_request_bundle_url(project_id: str, token: str) -> str:
        calls.append((project_id, token))
        return "https://vendor.example/translations.zip"

    def fake_download_file(url: str, target: Path) -> None:
        assert url == "https://vendor.example/translations.zip"
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr("nested/es.json", '{"commands": {"open": "Abrir"}}')
            archive.writestr("fr.json", '{"commands": {"open": "Ouvrir"}}')

    monkeypatch.setattr(vendor_sync, "_request_lokalise_bundle_url", fake_request_bundle_url)
    monkeypatch.setattr(vendor_sync, "_download_file", fake_download_file)

    messages_dir = tmp_path / "messages"
    status = await vendor_sync.sync_lokalise_catalogues(
        project_id="project-1",
        token_ref=vendor_sync.DEFAULT_TOKEN_REF,
        messages_dir=messages_dir,
        secrets_file=str(secrets_file),
    )

    assert status == 0
    assert calls == [("project-1", "vendor-token")]
    assert (messages_dir / "es.json").read_text(encoding="utf-8") == '{"commands": {"open": "Abrir"}}'
    assert (messages_dir / "fr.json").read_text(encoding="utf-8") == '{"commands": {"open": "Ouvrir"}}'
    assert "no de.json in vendor bundle" in capsys.readouterr().out


def test_request_lokalise_bundle_url_posts_export_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(b'{"bundle_url":"https://vendor.example/bundle.zip"}')

    monkeypatch.setattr(vendor_sync.urllib.request, "urlopen", fake_urlopen)

    bundle_url = vendor_sync._request_lokalise_bundle_url("project-1", "token-1")

    assert bundle_url == "https://vendor.example/bundle.zip"
    assert captured["timeout"] == 60
    request = captured["request"]
    assert getattr(request, "method") == "POST"
    assert "project-1" in getattr(request, "full_url")


def test_request_lokalise_bundle_url_rejects_missing_bundle_url(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(_request: object, timeout: int) -> FakeResponse:
        assert timeout == 60
        return FakeResponse(b"{}")

    monkeypatch.setattr(vendor_sync.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="bundle_url"):
        vendor_sync._request_lokalise_bundle_url("project-1", "token-1")


def test_download_file_writes_response_body(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_urlopen(url: str, timeout: int) -> FakeResponse:
        assert url == "https://vendor.example/bundle.zip"
        assert timeout == 120
        return FakeResponse(b"zip-bytes")

    monkeypatch.setattr(vendor_sync.urllib.request, "urlopen", fake_urlopen)

    target = tmp_path / "bundle.zip"
    vendor_sync._download_file("https://vendor.example/bundle.zip", target)

    assert target.read_bytes() == b"zip-bytes"


async def test_vendor_sync_async_main_delegates_to_lokalise(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    async def fake_sync_lokalise_catalogues(**kwargs: object) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(vendor_sync, "sync_lokalise_catalogues", fake_sync_lokalise_catalogues)

    status = await vendor_sync.async_main(
        [
            "--project-id",
            "project-1",
            "--messages-dir",
            str(tmp_path / "messages"),
            "--secrets-file",
            str(tmp_path / "secrets.json"),
        ]
    )

    assert status == 0
    assert captured["project_id"] == "project-1"
    assert captured["messages_dir"] == tmp_path / "messages"


def test_vendor_sync_main_runs_async_main(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_async_main(argv: list[str] | None = None) -> int:
        assert argv == ["--project-id", "project-1"]
        return 0

    monkeypatch.setattr(vendor_sync, "async_main", fake_async_main)

    assert vendor_sync.main(["--project-id", "project-1"]) == 0
