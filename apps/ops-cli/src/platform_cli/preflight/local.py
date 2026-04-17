"""Local-install preflight checks."""

from __future__ import annotations

import shutil
import socket
from pathlib import Path

from platform_cli.preflight.base import PreflightResult


class DiskSpaceCheck:
    """Ensure the target data directory has enough free space."""

    name = "disk-space"
    description = "Verify the data directory has at least 2GB free."

    def __init__(self, data_dir: Path, minimum_bytes: int = 2 * 1024 * 1024 * 1024) -> None:
        self._data_dir = data_dir
        self._minimum_bytes = minimum_bytes

    async def check(self) -> PreflightResult:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(self._data_dir)
        if usage.free >= self._minimum_bytes:
            free_gib = usage.free / (1024**3)
            return PreflightResult(True, f"{free_gib:.2f} GiB free in {self._data_dir}")
        return PreflightResult(
            False,
            f"Only {usage.free / (1024**3):.2f} GiB free in {self._data_dir}",
            "Free disk space in the data directory or choose another --data-dir.",
        )


class PortAvailabilityCheck:
    """Ensure required local ports are not already in use."""

    name = "port-availability"
    description = "Verify required local ports are free."

    def __init__(self, ports: tuple[int, ...] = (8000, 6333)) -> None:
        self._ports = ports

    @staticmethod
    def _is_port_available(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                return False
        return True

    async def check(self) -> PreflightResult:
        unavailable = [port for port in self._ports if not self._is_port_available(port)]
        if not unavailable:
            return PreflightResult(True, "Required local ports are available")
        unavailable_list = ", ".join(str(port) for port in unavailable)
        return PreflightResult(
            False,
            f"Ports already in use: {unavailable_list}",
            "Stop the conflicting services or choose different port settings.",
        )
