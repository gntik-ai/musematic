from __future__ import annotations

import hashlib
from pathlib import Path

from typer.testing import CliRunner

from platform_cli.main import app


def test_superadmin_recover_requires_expected_hash(tmp_path: Path) -> None:
    key_path = tmp_path / "emergency-key.bin"
    key_path.write_bytes(b"sealed-key")

    result = CliRunner().invoke(
        app,
        [
            "superadmin",
            "recover",
            "--username",
            "eve",
            "--email",
            "eve@example.com",
            "--emergency-key-path",
            str(key_path),
        ],
    )

    assert result.exit_code == 2
    assert "recover requires --expected-hash" in result.output


def test_superadmin_recover_rejects_hash_mismatch(tmp_path: Path) -> None:
    key_path = tmp_path / "emergency-key.bin"
    key_path.write_bytes(b"sealed-key")

    result = CliRunner().invoke(
        app,
        [
            "superadmin",
            "recover",
            "--username",
            "eve",
            "--email",
            "eve@example.com",
            "--emergency-key-path",
            str(key_path),
            "--expected-hash",
            "0" * 64,
        ],
    )

    assert result.exit_code == 2
    assert "emergency key hash mismatch" in result.output


def test_superadmin_recover_invokes_bootstrap_with_recovery_env(
    tmp_path: Path,
    mock_subprocess: list[dict[str, object]],
) -> None:
    key_path = tmp_path / "emergency-key.bin"
    key_path.write_bytes(b"sealed-key")
    expected_hash = hashlib.sha256(b"sealed-key").hexdigest()

    result = CliRunner().invoke(
        app,
        [
            "superadmin",
            "recover",
            "--username",
            "eve",
            "--email",
            "eve@example.com",
            "--emergency-key-path",
            str(key_path),
            "--expected-hash",
            expected_hash,
        ],
    )

    assert result.exit_code == 0
    assert mock_subprocess
    env = mock_subprocess[0]["kwargs"]["env"]
    assert env["PLATFORM_SUPERADMIN_USERNAME"] == "eve"
    assert env["PLATFORM_SUPERADMIN_EMAIL"] == "eve@example.com"
    assert env["PLATFORM_SUPERADMIN_RECOVERY"] == "true"
    assert env["PLATFORM_SUPERADMIN_MFA_ENROLLMENT"] == "required_before_first_login"
    assert mock_subprocess[0]["command"][-2:] == ["-m", "platform.admin.bootstrap"]


def test_superadmin_reset_requires_force() -> None:
    result = CliRunner().invoke(
        app,
        [
            "superadmin",
            "reset",
            "--username",
            "root",
            "--email",
            "root@example.com",
        ],
    )

    assert result.exit_code == 2
    assert "reset requires --force" in result.output
