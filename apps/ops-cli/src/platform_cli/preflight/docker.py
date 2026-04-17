"""Docker-specific preflight checks."""

from __future__ import annotations

import subprocess

from platform_cli.preflight.base import PreflightResult


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
    )


class DockerDaemonCheck:
    """Verify that the Docker daemon is reachable."""

    name = "docker-daemon"
    description = "Verify docker info succeeds."

    async def check(self) -> PreflightResult:
        result = _run_command(["docker", "info"])
        if result.returncode == 0:
            return PreflightResult(True, "Docker daemon is available")
        return PreflightResult(
            False,
            result.stderr.strip() or "docker info failed",
            "Start Docker Engine and ensure the current user can access the Docker socket.",
        )


class ComposeVersionCheck:
    """Verify Docker Compose v2 is installed."""

    name = "docker-compose-version"
    description = "Verify docker compose version is v2 or later."

    async def check(self) -> PreflightResult:
        result = _run_command(["docker", "compose", "version"])
        stdout = result.stdout.strip()
        if result.returncode == 0 and "v2" in stdout.lower():
            return PreflightResult(True, stdout)
        return PreflightResult(
            False,
            stdout or result.stderr.strip() or "docker compose version failed",
            "Install Docker Compose v2 or newer.",
        )
