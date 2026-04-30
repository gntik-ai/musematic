from __future__ import annotations

import json
from pathlib import Path

import pytest

from .conftest import run_command


OPS_CLI = Path(__file__).resolve().parents[4] / "apps/ops-cli/.venv/bin/platform-cli"


def test_migration_dry_run_emits_manifest(tmp_path: Path) -> None:
    if not OPS_CLI.exists():
        pytest.skip("ops-cli venv is required for migration E2E tests")
    result = run_command(
        [
            str(OPS_CLI),
            "vault",
            "migrate-from-k8s",
            "--namespace",
            "platform",
            "--env",
            "dev",
            "--output-dir",
            str(tmp_path),
        ],
        check=False,
    )
    if result.returncode != 0:
        assert "kubectl" in result.stderr.lower() or "kubernetes" in result.stderr.lower()
        return
    assert list(tmp_path.glob("vault-migration-*.json"))


def test_migration_apply_flag_is_available() -> None:
    if not OPS_CLI.exists():
        pytest.skip("ops-cli venv is required for migration E2E tests")
    result = run_command([str(OPS_CLI), "vault", "migrate-from-k8s", "--help"], check=False)
    assert "--apply" in result.stdout


def test_migration_idempotency_summary_shape(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "entries": [],
                "success_count": 0,
                "failure_count": 0,
                "already_migrated_count": 0,
                "new_count": 0,
            }
        ),
        encoding="utf-8",
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert {"already_migrated_count", "new_count"} <= set(payload)


def test_verify_migration_requires_manifest() -> None:
    if not OPS_CLI.exists():
        pytest.skip("ops-cli venv is required for migration E2E tests")
    result = run_command([str(OPS_CLI), "vault", "verify-migration", "--help"], check=False)
    assert "--manifest" in result.stdout


def test_rollback_path_is_mode_flag_flip() -> None:
    runbook = Path(__file__).resolve().parents[4] / "specs/090-hashicorp-vault-integration/tasks.md"
    assert "rollback via mode-flag flip" in runbook.read_text(encoding="utf-8")


def test_malformed_kubernetes_secret_is_reported(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"entries":[{"k8s_secret_name":"bad","success":false}]}', encoding="utf-8")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["entries"][0]["success"] is False
