"""Subprocess wrapper around Helm and kubectl."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, check=False, text=True)


class HelmRunner:
    """Thin wrapper over the canonical Helm CLI."""

    def install(
        self,
        chart_path: Path,
        release_name: str,
        namespace: str,
        values_file: Path,
        *,
        dry_run: bool = False,
    ) -> None:
        """Install or upgrade a Helm release."""

        command = [
            "helm",
            "upgrade",
            "--install",
            release_name,
            str(chart_path),
            "-n",
            namespace,
            "-f",
            str(values_file),
            "--create-namespace",
            "--wait",
            "--timeout",
            "5m",
        ]
        if dry_run:
            command.append("--dry-run")
        result = _run(command)
        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip() or result.stdout.strip() or "helm install failed"
            )

    def wait_for_ready(self, deployment_name: str, namespace: str, timeout: int = 300) -> None:
        """Wait for a deployment rollout to report ready."""

        result = _run(
            [
                "kubectl",
                "rollout",
                "status",
                f"deployment/{deployment_name}",
                "-n",
                namespace,
                f"--timeout={timeout}s",
            ]
        )
        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip() or result.stdout.strip() or "deployment did not become ready"
            )

    def is_installed(self, release_name: str, namespace: str) -> bool:
        """Return whether a Helm release exists."""

        for release in self.list_releases(namespace):
            if release.get("name") == release_name:
                return True
        return False

    def list_releases(self, namespace: str | None = None) -> list[dict[str, Any]]:
        """List Helm releases as JSON."""

        command = ["helm", "list", "--output", "json"]
        if namespace:
            command.extend(["-n", namespace])
        result = _run(command)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "helm list failed")
        payload = json.loads(result.stdout or "[]")
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def uninstall(self, release_name: str, namespace: str) -> None:
        """Uninstall a Helm release if present."""

        result = _run(["helm", "uninstall", release_name, "-n", namespace])
        if result.returncode != 0 and "release: not found" not in result.stderr.lower():
            raise RuntimeError(
                result.stderr.strip() or result.stdout.strip() or "helm uninstall failed"
            )
