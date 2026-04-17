from __future__ import annotations

import shutil
import socket
import subprocess
from collections import namedtuple
from pathlib import Path

import pytest

from platform_cli.preflight.base import PreflightResult, PreflightRunner
from platform_cli.preflight.docker import ComposeVersionCheck, DockerDaemonCheck
from platform_cli.preflight.kubernetes import (
    IngressControllerCheck,
    KubectlAccessCheck,
    NamespacePermissionCheck,
    StorageClassCheck,
)
from platform_cli.preflight.local import DiskSpaceCheck, PortAvailabilityCheck


class FakeCheck:
    def __init__(self, name: str, result: PreflightResult) -> None:
        self.name = name
        self.description = name
        self._result = result

    async def check(self) -> PreflightResult:
        return self._result


@pytest.mark.asyncio
async def test_preflight_runner_aggregates_results() -> None:
    summary = await PreflightRunner(
        [
            FakeCheck("one", PreflightResult(True, "ok")),
            FakeCheck("two", PreflightResult(False, "bad")),
        ]
    ).run()

    assert summary.passed is False
    assert summary.passed_count == 1
    assert summary.failed_count == 1


def _result(code: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["cmd"], returncode=code, stdout=stdout, stderr=stderr)


@pytest.mark.asyncio
async def test_kubernetes_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: _result(stdout="ok"))

    checks = [
        KubectlAccessCheck(),
        NamespacePermissionCheck("platform-control"),
        StorageClassCheck("standard"),
        IngressControllerCheck(),
    ]
    for check in checks:
        result = await check.check()
        assert result.passed is True


@pytest.mark.asyncio
async def test_docker_checks_handle_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "compose"]:
            return _result(stdout="Docker Compose version v2.25.0")
        return _result(code=1, stderr="daemon down")

    monkeypatch.setattr("subprocess.run", fake_run)

    daemon = await DockerDaemonCheck().check()
    compose = await ComposeVersionCheck().check()

    assert daemon.passed is False
    assert compose.passed is True


@pytest.mark.asyncio
async def test_local_checks_cover_disk_and_ports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda path: usage(10, 2, 8 * 1024 * 1024 * 1024),
    )

    class FakeSocket:
        def __enter__(self) -> FakeSocket:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def setsockopt(self, *args: object) -> None:
            return None

        def bind(self, address: tuple[str, int]) -> None:
            if address[1] == 6333:
                raise OSError("busy")

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: FakeSocket())

    disk_result = await DiskSpaceCheck(tmp_path).check()
    port_result = await PortAvailabilityCheck((8000, 6333)).check()

    assert disk_result.passed is True
    assert port_result.passed is False
