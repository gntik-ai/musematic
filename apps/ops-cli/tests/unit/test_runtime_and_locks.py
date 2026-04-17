from __future__ import annotations

import io
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import typer
from click import Command

from platform_cli.config import ExitCode, InstallerConfig
from platform_cli.locking.file import FileLock
from platform_cli.locking.kubernetes import KubernetesLock
from platform_cli.output.structured import set_output_stream
from platform_cli.runtime import (
    CLIState,
    emit_event,
    exit_with_error,
    get_state,
    inferred_api_base_url,
    load_runtime_config,
    resolve_config_path,
)


def test_runtime_helpers_and_error_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = typer.Context(Command("test"))
    config_path = tmp_path / "platform-install.yaml"
    config_path.write_text("namespace: demo\n", encoding="utf-8")
    ctx.obj = CLIState(config_path=config_path, verbose=False, json_output=True, no_color=False)

    config = load_runtime_config(ctx, namespace="override")

    assert get_state(ctx).config_path == config_path
    assert resolve_config_path(get_state(ctx)) == config_path
    assert config.namespace == "override"
    assert inferred_api_base_url(InstallerConfig()) == "http://platform.local"

    stream = io.StringIO()
    set_output_stream(stream)
    emit_event(ctx, stage="unit", status="completed", message="ok", details={"a": 1})
    payload = json.loads(stream.getvalue().strip())
    assert payload["stage"] == "unit"

    with pytest.raises(typer.Exit) as exc_info:
        exit_with_error(ctx, "boom", code=ExitCode.PARTIAL_FAILURE)
    assert exc_info.value.exit_code == 3


def test_get_state_raises_without_cli_state() -> None:
    ctx = typer.Context(Command("test"))
    with pytest.raises(RuntimeError):
        get_state(ctx)


def test_file_lock_acquire_release_and_stale(tmp_path: Path) -> None:
    lock_path = tmp_path / "install.lock"
    lock = FileLock(lock_path)

    assert lock.acquire() is True
    assert lock.is_locked() is True
    lock.release()
    assert lock_path.exists() is False

    lock_path.write_text("{invalid", encoding="utf-8")
    assert lock.acquire(timeout_minutes=0) is True
    lock.release()


def test_kubernetes_lock_acquire_release_and_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(UTC)
    expired = (now - timedelta(minutes=31)).isoformat()
    commands: list[list[str]] = []

    responses = [
        subprocess.CompletedProcess(args=["kubectl"], returncode=1, stdout="", stderr="missing"),
        subprocess.CompletedProcess(args=["kubectl"], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess(
            args=["kubectl"],
            returncode=0,
            stdout=json.dumps({"data": {"holder": "holder", "acquired_at": expired}}),
            stderr="",
        ),
        subprocess.CompletedProcess(args=["kubectl"], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess(
            args=["kubectl"],
            returncode=0,
            stdout=json.dumps({"data": {"holder": "holder", "acquired_at": now.isoformat()}}),
            stderr="",
        ),
        subprocess.CompletedProcess(args=["kubectl"], returncode=0, stdout="", stderr=""),
    ]

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return responses.pop(0)

    monkeypatch.setattr(KubernetesLock, "_run", staticmethod(fake_run))
    lock = KubernetesLock()

    assert lock.acquire("platform-control", "holder") is True
    assert lock.is_locked("platform-control", timeout_minutes=30) == (False, None)
    lock.release("platform-control", "holder")
    assert any(command[:3] == ["kubectl", "create", "configmap"] for command in commands)
