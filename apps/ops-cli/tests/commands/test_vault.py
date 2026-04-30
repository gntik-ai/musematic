from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from platform_cli.commands.vault import vault_app
from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.main import app
from platform_cli.secrets.manifest import ManifestEntry, new_manifest, write_manifest
from platform_cli.secrets.migration import (
    KubernetesSecretValue,
    migrate_from_k8s,
    vault_path_from_k8s_secret_name,
    verify_migration,
)


class FakeReader:
    def __init__(self, values: list[KubernetesSecretValue]) -> None:
        self.values = values

    def iter_values(self, namespaces: list[str]) -> list[KubernetesSecretValue]:
        self.namespaces = namespaces
        return self.values


class FakeVault:
    def __init__(self, values: dict[tuple[str, str], bytes] | None = None) -> None:
        self.values = values or {}
        self.writes: list[tuple[str, str, bytes]] = []

    def get(self, path: str, key: str) -> bytes | None:
        return self.values.get((path, key))

    def put(self, path: str, key: str, value: bytes) -> None:
        self.writes.append((path, key, value))
        self.values[(path, key)] = value


def _config(tmp_path: Path) -> InstallerConfig:
    return InstallerConfig(
        data_dir=tmp_path,
        deployment_mode=DeploymentMode.LOCAL,
        api_base_url="http://api.local",
        auth_token="token",
    )


def test_vault_path_from_k8s_secret_name_round_trip() -> None:
    assert (
        vault_path_from_k8s_secret_name("musematic-production-oauth-google")
        == "secret/data/musematic/production/oauth/google"
    )
    assert (
        vault_path_from_k8s_secret_name("musematic-dev-connectors-slack__bot-token")
        == "secret/data/musematic/dev/connectors/slack/bot-token"
    )


def test_migrate_from_k8s_dry_run_writes_manifest_without_plaintext(tmp_path: Path) -> None:
    reader = FakeReader(
        [
            KubernetesSecretValue(
                "platform", "musematic-production-oauth-google", "value", b"secret"
            ),
            KubernetesSecretValue("platform", "musematic-prod-oauth-google", "value", b"bad"),
        ]
    )
    vault = FakeVault()

    manifest, manifest_path = migrate_from_k8s(
        namespaces=["platform"],
        output_dir=tmp_path,
        reader=reader,
        vault=vault,
    )

    assert manifest.success_count == 1
    assert manifest.failure_count == 1
    assert vault.writes == []
    payload = manifest_path.read_text(encoding="utf-8")
    assert '"value": "secret"' not in payload
    assert "bad" not in payload


def test_migrate_from_k8s_apply_is_idempotent(tmp_path: Path) -> None:
    path = "secret/data/musematic/production/oauth/google"
    reader = FakeReader(
        [KubernetesSecretValue("platform", "musematic-production-oauth-google", "value", b"secret")]
    )
    vault = FakeVault({(path, "value"): b"secret"})

    manifest, _ = migrate_from_k8s(apply=True, output_dir=tmp_path, reader=reader, vault=vault)

    assert manifest.already_migrated_count == 1
    assert vault.writes == []


def test_migrate_from_k8s_apply_writes_new_values(tmp_path: Path) -> None:
    reader = FakeReader(
        [KubernetesSecretValue("platform", "musematic-production-oauth-google", "value", b"secret")]
    )
    vault = FakeVault()

    manifest, _ = migrate_from_k8s(apply=True, output_dir=tmp_path, reader=reader, vault=vault)

    assert manifest.new_count == 1
    assert vault.writes == [
        ("secret/data/musematic/production/oauth/google", "value", b"secret")
    ]


def test_verify_migration_reports_mismatch(tmp_path: Path) -> None:
    manifest = new_manifest(
        "production",
        [
            ManifestEntry(
                "platform",
                "musematic-production-oauth-google",
                "value",
                "secret/data/musematic/production/oauth/google",
                "0" * 64,
                True,
            )
        ],
    )
    manifest_path = write_manifest(manifest, tmp_path)

    verified = verify_migration(
        manifest_path,
        vault=FakeVault({(manifest.entries[0].vault_path, "value"): b"secret"}),
    )

    assert verified.failure_count == 1
    assert verified.entries[0].reason == "sha256_mismatch"


def test_vault_command_group_lists_commands() -> None:
    result = CliRunner().invoke(vault_app, ["--help"])
    assert result.exit_code == 0
    assert "migrate-from-k8s" in result.output
    assert "verify-migration" in result.output
    assert "flush-cache" in result.output


def test_vault_migrate_command_uses_manifest(monkeypatch, tmp_path: Path) -> None:
    manifest = new_manifest("production", [])
    manifest_path = tmp_path / "vault-migration-test.json"
    manifest_path.write_text(json.dumps(manifest.to_dict()), encoding="utf-8")
    monkeypatch.setattr(
        "platform_cli.commands.vault.migrate_from_k8s",
        lambda **kwargs: (manifest, manifest_path),
    )

    result = CliRunner().invoke(app, ["vault", "migrate-from-k8s", "--output-dir", str(tmp_path)])

    assert result.exit_code == 0
    assert "vault-migration" in result.output
    assert "test.json" in result.output


def test_vault_admin_commands_call_expected_endpoints(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    async def fake_request(method: str, url: str, **kwargs):
        calls.append((method, url, kwargs.get("json")))
        return SimpleNamespace(json=lambda: {"ok": True})

    monkeypatch.setattr(
        "platform_cli.commands.vault.load_runtime_config", lambda ctx: _config(tmp_path)
    )
    monkeypatch.setattr("platform_cli.commands.vault._request", fake_request)

    runner = CliRunner()
    assert runner.invoke(app, ["vault", "status"]).exit_code == 0
    assert runner.invoke(app, ["vault", "flush-cache", "--pod", "control-plane-0"]).exit_code == 0
    assert runner.invoke(app, ["vault", "rotate-token"]).exit_code == 0

    assert calls[0][0] == "GET"
    assert calls[0][1].endswith("/api/v1/admin/vault/status")
    assert calls[1][2] == {"pod": "control-plane-0", "all_pods": False}
    assert calls[2][1].endswith("/api/v1/admin/vault/rotate-token")
