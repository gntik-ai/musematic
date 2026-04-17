from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from platform_cli.config import SecretsConfig
from platform_cli.secrets.generator import (
    generate_secrets,
    store_secrets_env_file,
    store_secrets_kubernetes,
    store_secrets_local,
)


def test_generate_secrets_preserves_provided_values() -> None:
    secrets = generate_secrets(
        SecretsConfig(
            redis_password="redis-pass",
            jwt_private_key_pem=None,
        )
    )

    assert secrets.redis_password == "redis-pass"
    assert secrets.jwt_private_key_pem.startswith("-----BEGIN PRIVATE KEY-----")
    assert secrets.jwt_public_key_pem.startswith("-----BEGIN PUBLIC KEY-----")
    assert len(secrets.admin_password) == 32
    assert re.search(r"[A-Z]", secrets.admin_password)
    assert re.search(r"[a-z]", secrets.admin_password)
    assert re.search(r"\d", secrets.admin_password)
    assert re.search(r"[^A-Za-z0-9]", secrets.admin_password)


def test_secret_storage_helpers_write_expected_formats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = generate_secrets(SecretsConfig())
    env_path = store_secrets_env_file(bundle, tmp_path / ".env")
    json_path = store_secrets_local(bundle, tmp_path)

    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> None:
        calls.append(command)
        return None

    monkeypatch.setattr("subprocess.run", fake_run)
    store_secrets_kubernetes(bundle, "platform-control")

    assert "ADMIN_PASSWORD=" in env_path.read_text(encoding="utf-8")
    assert (
        json.loads(json_path.read_text(encoding="utf-8"))["admin_password"] == bundle.admin_password
    )
    assert calls[0][:3] == ["kubectl", "apply", "-f"]
