"""Kubernetes ConfigMap-based lock implementation."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta


class KubernetesLock:
    """Acquire and release a namespace-scoped installation lock."""

    lock_name = "platform-install-lock"

    @staticmethod
    def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
        )

    def acquire(self, namespace: str, holder_id: str, timeout_minutes: int = 30) -> bool:
        """Create or renew a ConfigMap-backed lock."""

        locked, current_holder = self.is_locked(namespace, timeout_minutes=timeout_minutes)
        if locked and current_holder != holder_id:
            return False
        if locked and current_holder == holder_id:
            return True

        now = datetime.now(UTC).isoformat()
        command = [
            "kubectl",
            "create",
            "configmap",
            self.lock_name,
            "-n",
            namespace,
            f"--from-literal=holder={holder_id}",
            f"--from-literal=acquired_at={now}",
        ]
        result = self._run(command)
        return result.returncode == 0

    def release(self, namespace: str, holder_id: str) -> None:
        """Delete the lock if it belongs to the caller."""

        locked, current_holder = self.is_locked(namespace)
        if not locked or current_holder != holder_id:
            return
        self._run(["kubectl", "delete", "configmap", self.lock_name, "-n", namespace])

    def is_locked(
        self,
        namespace: str,
        *,
        timeout_minutes: int = 30,
    ) -> tuple[bool, str | None]:
        """Return the lock state and current holder for the namespace."""

        result = self._run(
            ["kubectl", "get", "configmap", self.lock_name, "-n", namespace, "-o", "json"]
        )
        if result.returncode != 0:
            return False, None

        payload = json.loads(result.stdout or "{}")
        data = payload.get("data", {})
        holder = data.get("holder")
        acquired_at = data.get("acquired_at")
        if not isinstance(acquired_at, str):
            return True, holder

        acquired = datetime.fromisoformat(acquired_at)
        if datetime.now(UTC) - acquired > timedelta(minutes=timeout_minutes):
            self._run(["kubectl", "delete", "configmap", self.lock_name, "-n", namespace])
            return False, None
        return True, holder
