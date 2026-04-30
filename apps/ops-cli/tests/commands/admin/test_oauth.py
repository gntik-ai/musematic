from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from platform_cli.commands import admin as admin_commands
from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.main import app


def _config(tmp_path: Path) -> InstallerConfig:
    return InstallerConfig(
        data_dir=tmp_path,
        deployment_mode=DeploymentMode.LOCAL,
        api_base_url="http://api.local",
        auth_token="token",
    )


def _provider(**overrides: Any) -> dict[str, Any]:
    provider = {
        "id": "1c88e0f7-0d0c-48fa-9ed5-72ea269f73b1",
        "provider_type": "google",
        "display_name": "Google",
        "enabled": True,
        "client_id": "google-client.apps.googleusercontent.com",
        "client_secret_ref": "secret/data/musematic/staging/oauth/google/client-secret",
        "redirect_uri": "https://app.example.com/oauth/google/callback",
        "scopes": ["profile", "email"],
        "domain_restrictions": ["example.com"],
        "org_restrictions": [],
        "group_role_mapping": {"admins@example.com": "admin"},
        "default_role": "member",
        "require_mfa": True,
        "source": "env_var",
        "client_secret": "plaintext-should-never-export",
    }
    provider.update(overrides)
    return provider


def _write_manifest(path: Path, providers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    manifest = admin_commands._build_oauth_manifest("staging", providers or [_provider()])
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return manifest


def test_oauth_command_group_lists_export_and_import() -> None:
    result = CliRunner().invoke(app, ["admin", "oauth", "--help"])

    assert result.exit_code == 0
    assert "export" in result.output
    assert "import" in result.output


def test_export_produces_valid_yaml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "staging-oauth.yaml"

    async def fake_request(method: str, url: str, **kwargs: Any) -> SimpleNamespace:
        assert method == "GET"
        assert url.endswith("/api/v1/admin/oauth/providers")
        assert kwargs["headers"] == {"Authorization": "Bearer token"}
        return SimpleNamespace(json=lambda: {"providers": [_provider()]})

    monkeypatch.setattr(admin_commands, "load_runtime_config", lambda ctx: _config(tmp_path))
    monkeypatch.setattr(admin_commands, "_request", fake_request)

    result = CliRunner().invoke(
        app,
        ["admin", "oauth", "export", "--env", "staging", "--output", str(output)],
    )

    assert result.exit_code == 0, result.output
    payload = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert payload["environment"] == "staging"
    assert payload["schema_version"] == 1
    assert len(payload["sha256"]) == 64
    assert payload["providers"][0]["provider_type"] == "google"


def test_export_omits_secret_values(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "oauth.yaml"

    async def fake_request(method: str, url: str, **kwargs: Any) -> SimpleNamespace:
        del method, url, kwargs
        return SimpleNamespace(json=lambda: {"providers": [_provider()]})

    monkeypatch.setattr(admin_commands, "load_runtime_config", lambda ctx: _config(tmp_path))
    monkeypatch.setattr(admin_commands, "_request", fake_request)

    result = CliRunner().invoke(
        app,
        ["admin", "oauth", "export", "--env", "staging", "--output", str(output)],
    )

    assert result.exit_code == 0, result.output
    text = output.read_text(encoding="utf-8")
    assert "plaintext-should-never-export" not in text
    assert "client_secret:" not in text
    assert "client_secret_vault_path:" in text


def test_export_is_idempotent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"

    async def fake_request(method: str, url: str, **kwargs: Any) -> SimpleNamespace:
        del method, url, kwargs
        return SimpleNamespace(json=lambda: {"providers": [_provider()]})

    monkeypatch.setattr(admin_commands, "load_runtime_config", lambda ctx: _config(tmp_path))
    monkeypatch.setattr(admin_commands, "_request", fake_request)
    runner = CliRunner()

    assert (
        runner.invoke(
            app,
            ["admin", "oauth", "export", "--env", "staging", "--output", str(first)],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            ["admin", "oauth", "export", "--env", "staging", "--output", str(second)],
        ).exit_code
        == 0
    )

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


def test_export_includes_source_field(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "oauth.yaml"

    async def fake_request(method: str, url: str, **kwargs: Any) -> SimpleNamespace:
        del method, url, kwargs
        return SimpleNamespace(json=lambda: {"providers": [_provider(source="imported")]})

    monkeypatch.setattr(admin_commands, "load_runtime_config", lambda ctx: _config(tmp_path))
    monkeypatch.setattr(admin_commands, "_request", fake_request)

    result = CliRunner().invoke(
        app,
        ["admin", "oauth", "export", "--env", "staging", "--output", str(output)],
    )

    assert result.exit_code == 0, result.output
    exported = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert exported["providers"][0]["source"] == "imported"


def test_import_dry_run_validates_vault_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "oauth.yaml"
    _write_manifest(manifest_path)
    calls: list[tuple[str, str, dict[str, Any] | None]] = []
    vault_paths: list[str] = []

    async def fake_request(method: str, url: str, **kwargs: Any) -> SimpleNamespace:
        calls.append((method, url, kwargs.get("json")))
        return SimpleNamespace(json=lambda: {"providers": []})

    def fake_list_versions(path: str) -> list[int]:
        vault_paths.append(path)
        return [1]

    monkeypatch.setattr(admin_commands, "load_runtime_config", lambda ctx: _config(tmp_path))
    monkeypatch.setattr(admin_commands, "_request", fake_request)
    monkeypatch.setattr(admin_commands, "_list_vault_versions", fake_list_versions)

    result = CliRunner().invoke(
        app,
        ["admin", "oauth", "import", "--input", str(manifest_path)],
    )

    assert result.exit_code == 0, result.output
    assert vault_paths == ["secret/data/musematic/staging/oauth/google/client-secret"]
    assert [call[0] for call in calls] == ["GET"]


def test_import_fails_on_missing_vault_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "oauth.yaml"
    _write_manifest(manifest_path)
    monkeypatch.setattr(admin_commands, "load_runtime_config", lambda ctx: _config(tmp_path))
    monkeypatch.setattr(admin_commands, "_list_vault_versions", lambda path: [])

    result = CliRunner().invoke(
        app,
        ["admin", "oauth", "import", "--input", str(manifest_path)],
    )

    assert result.exit_code != 0
    assert "Missing OAuth client secret Vault path" in result.output


def test_import_apply_requires_dry_run_first(tmp_path: Path) -> None:
    manifest_path = tmp_path / "oauth.yaml"
    _write_manifest(manifest_path)

    result = CliRunner().invoke(
        app,
        ["admin", "oauth", "import", "--input", str(manifest_path), "--apply"],
    )

    assert result.exit_code != 0
    assert "--apply requires --dry-run-first" in result.output


def test_import_apply_sends_imported_source_and_no_secret_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "oauth.yaml"
    _write_manifest(manifest_path)
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    async def fake_request(method: str, url: str, **kwargs: Any) -> SimpleNamespace:
        calls.append((method, url, kwargs.get("json")))
        return SimpleNamespace(json=lambda: {"providers": []})

    monkeypatch.setattr(admin_commands, "load_runtime_config", lambda ctx: _config(tmp_path))
    monkeypatch.setattr(admin_commands, "_request", fake_request)
    monkeypatch.setattr(admin_commands, "_list_vault_versions", lambda path: [1])

    result = CliRunner().invoke(
        app,
        [
            "admin",
            "oauth",
            "import",
            "--input",
            str(manifest_path),
            "--apply",
            "--dry-run-first",
        ],
    )

    assert result.exit_code == 0, result.output
    put_call = calls[-1]
    assert put_call[0] == "PUT"
    assert put_call[1].endswith("/api/v1/admin/oauth/providers/google")
    assert put_call[2] is not None
    assert put_call[2]["source"] == "imported"
    assert (
        put_call[2]["client_secret_ref"]
        == "secret/data/musematic/staging/oauth/google/client-secret"
    )
    assert "client_secret" not in put_call[2]


def test_round_trip_export_then_import_with_mock_vault(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "oauth.yaml"
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    async def export_request(method: str, url: str, **kwargs: Any) -> SimpleNamespace:
        del method, url, kwargs
        return SimpleNamespace(json=lambda: {"providers": [_provider()]})

    monkeypatch.setattr(admin_commands, "load_runtime_config", lambda ctx: _config(tmp_path))
    monkeypatch.setattr(admin_commands, "_request", export_request)
    runner = CliRunner()
    assert (
        runner.invoke(
            app,
            ["admin", "oauth", "export", "--env", "staging", "--output", str(manifest_path)],
        ).exit_code
        == 0
    )

    async def import_request(method: str, url: str, **kwargs: Any) -> SimpleNamespace:
        calls.append((method, url, kwargs.get("json")))
        return SimpleNamespace(json=lambda: {"providers": []})

    monkeypatch.setattr(admin_commands, "_request", import_request)
    monkeypatch.setattr(admin_commands, "_list_vault_versions", lambda path: [1, 2])

    result = runner.invoke(
        app,
        [
            "admin",
            "oauth",
            "import",
            "--input",
            str(manifest_path),
            "--apply",
            "--dry-run-first",
        ],
    )

    assert result.exit_code == 0, result.output
    assert any(call[0] == "PUT" for call in calls)


def test_import_rejects_digest_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest_path = tmp_path / "oauth.yaml"
    manifest = _write_manifest(manifest_path)
    manifest["providers"][0]["enabled"] = False
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(admin_commands, "load_runtime_config", lambda ctx: _config(tmp_path))

    result = CliRunner().invoke(app, ["admin", "oauth", "import", "--input", str(manifest_path)])

    assert result.exit_code != 0
    assert "sha256 does not match" in result.output


def test_import_rejects_non_oauth_vault_path(tmp_path: Path) -> None:
    manifest_path = tmp_path / "oauth.yaml"
    _write_manifest(
        manifest_path,
        [
            _provider(
                client_secret_ref="secret/data/musematic/staging/connectors/google/client-secret",
            )
        ],
    )

    result = CliRunner().invoke(app, ["admin", "oauth", "import", "--input", str(manifest_path)])

    assert result.exit_code != 0
    assert "OAuth provider secret must use an oauth Vault path" in result.output


def test_import_rejects_empty_provider_manifest(tmp_path: Path) -> None:
    manifest = admin_commands._build_oauth_manifest("staging", [])
    manifest_path = tmp_path / "empty.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    result = CliRunner().invoke(app, ["admin", "oauth", "import", "--input", str(manifest_path)])

    assert result.exit_code != 0
    assert "contains no providers" in result.output


def test_import_dry_run_reports_unchanged_diff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "oauth.yaml"
    _write_manifest(manifest_path)

    async def fake_request(method: str, url: str, **kwargs: Any) -> SimpleNamespace:
        del method, url, kwargs
        return SimpleNamespace(json=lambda: {"providers": [_provider()]})

    monkeypatch.setattr(admin_commands, "load_runtime_config", lambda ctx: _config(tmp_path))
    monkeypatch.setattr(admin_commands, "_request", fake_request)
    monkeypatch.setattr(admin_commands, "_list_vault_versions", lambda path: [1])

    result = CliRunner().invoke(app, ["admin", "oauth", "import", "--input", str(manifest_path)])

    assert result.exit_code == 0, result.output
    assert "unchanged" in result.output
