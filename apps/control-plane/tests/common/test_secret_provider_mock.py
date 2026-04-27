from __future__ import annotations

import json
from platform.common.secret_provider import (
    CredentialUnavailableError,
    InvalidVaultPathError,
    MockSecretProvider,
)
from types import SimpleNamespace

import pytest


def _settings(path: str) -> SimpleNamespace:
    return SimpleNamespace(connectors=SimpleNamespace(vault_mock_secrets_file=path))


@pytest.mark.asyncio
async def test_mock_provider_reads_string_value_from_file(tmp_path) -> None:
    secrets_file = tmp_path / ".vault-secrets.json"
    path = "secret/data/musematic/dev/oauth/google"
    secrets_file.write_text(json.dumps({path: "google-secret"}), encoding="utf-8")

    provider = MockSecretProvider(_settings(str(secrets_file)))

    assert await provider.get(path) == "google-secret"


@pytest.mark.asyncio
async def test_mock_provider_reads_keyed_value_from_file(tmp_path) -> None:
    secrets_file = tmp_path / ".vault-secrets.json"
    path = "secret/data/musematic/dev/notifications/webhook-secrets/hook-1"
    secrets_file.write_text(json.dumps({path: {"hmac_secret": "signed"}}), encoding="utf-8")

    provider = MockSecretProvider(_settings(str(secrets_file)))

    assert await provider.get(path, key="hmac_secret") == "signed"


@pytest.mark.asyncio
async def test_mock_provider_uses_connector_env_fallback(monkeypatch, tmp_path) -> None:
    path = "secret/data/musematic/dev/oauth/github"
    monkeypatch.setenv(
        "CONNECTOR_SECRET_VALUE_SECRET_DATA_MUSEMATIC_DEV_OAUTH_GITHUB",
        "env-secret",
    )

    provider = MockSecretProvider(_settings(str(tmp_path / "missing.json")))

    assert await provider.get(path) == "env-secret"


@pytest.mark.asyncio
async def test_mock_provider_missing_secret_raises(tmp_path) -> None:
    provider = MockSecretProvider(_settings(str(tmp_path / "missing.json")))

    with pytest.raises(CredentialUnavailableError):
        await provider.get("secret/data/musematic/dev/oauth/missing")


@pytest.mark.asyncio
async def test_mock_provider_enforces_canonical_paths(tmp_path) -> None:
    provider = MockSecretProvider(_settings(str(tmp_path / "missing.json")))

    with pytest.raises(InvalidVaultPathError):
        await provider.get("vault/google")


@pytest.mark.asyncio
async def test_mock_provider_can_disable_path_validation_for_compatibility(tmp_path) -> None:
    secrets_file = tmp_path / ".vault-secrets.json"
    secrets_file.write_text(json.dumps({"vault/google": "legacy"}), encoding="utf-8")
    provider = MockSecretProvider(_settings(str(secrets_file)), validate_paths=False)

    assert await provider.get("vault/google") == "legacy"


@pytest.mark.asyncio
async def test_mock_provider_put_persists_values(tmp_path) -> None:
    secrets_file = tmp_path / ".vault-secrets.json"
    path = "secret/data/musematic/dev/oauth/google"
    provider = MockSecretProvider(_settings(str(secrets_file)))

    await provider.put(path, {"value": "persisted"})

    assert await provider.get(path) == "persisted"


@pytest.mark.asyncio
async def test_mock_provider_health_check_reports_file_state(tmp_path) -> None:
    secrets_file = tmp_path / ".vault-secrets.json"
    provider = MockSecretProvider(_settings(str(secrets_file)))

    assert (await provider.health_check()).status == "red"

    secrets_file.write_text("{}", encoding="utf-8")

    assert (await provider.health_check()).status == "green"
