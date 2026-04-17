"""Shared pytest fixtures for the ops CLI package."""

from __future__ import annotations

import io
import subprocess
from pathlib import Path
from typing import Any

import pytest

from platform_cli.config import InstallerConfig, load_config
from platform_cli.output.structured import reset_output_stream, set_output_stream


@pytest.fixture
def tmp_config(tmp_path: Path) -> InstallerConfig:
    """Create a temporary installer config loaded from YAML."""

    path = tmp_path / "platform-install.yaml"
    path.write_text(
        "\n".join(
            [
                "deployment_mode: kubernetes",
                "namespace: platform",
                "storage_class: standard",
                "admin:",
                "  email: admin@example.com",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return load_config(path)


@pytest.fixture
def mock_subprocess(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Patch subprocess.run and capture invocations."""

    calls: list[dict[str, Any]] = []

    def fake_run(
        command: list[str],
        *,
        capture_output: bool = False,
        check: bool = False,
        text: bool = False,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(
            {
                "command": command,
                "capture_output": capture_output,
                "check": check,
                "text": text,
                "kwargs": kwargs,
            }
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


@pytest.fixture
def ndjson_capture() -> io.StringIO:
    """Capture structured output events in memory."""

    buffer = io.StringIO()
    set_output_stream(buffer)
    try:
        yield buffer
    finally:
        reset_output_stream()
