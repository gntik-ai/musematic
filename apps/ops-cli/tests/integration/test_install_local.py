from __future__ import annotations

import socket
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.installers.local import LocalInstaller
from platform_cli.models import CheckStatus, DiagnosticReport


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _write_health_server(path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            """
            from http.server import BaseHTTPRequestHandler, HTTPServer
            import sys


            class Handler(BaseHTTPRequestHandler):
                def do_GET(self) -> None:  # noqa: N802
                    status = 200 if self.path == "/health" else 404
                    self.send_response(status)
                    self.end_headers()
                    self.wfile.write(b"ok")

                def log_message(self, format: str, *args: object) -> None:
                    return None


            HTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_local_installer_start_stop_lifecycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    port = _free_port()
    server_script = tmp_path / "health_server.py"
    _write_health_server(server_script)

    config = InstallerConfig(data_dir=tmp_path, deployment_mode=DeploymentMode.LOCAL)
    installer = LocalInstaller(config, port=port, skip_preflight=True)

    real_popen = subprocess.Popen
    launched: list[subprocess.Popen[str]] = []

    def fake_popen(*args: object, **kwargs: object) -> subprocess.Popen[str]:
        process = real_popen(
            [sys.executable, str(server_script), str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        launched.append(process)
        return process

    monkeypatch.setattr("platform_cli.installers.local.shutil.which", lambda binary: None)
    monkeypatch.setattr("platform_cli.installers.local.subprocess.Popen", fake_popen)
    monkeypatch.setattr(installer.migration_runner, "run_alembic", lambda database_url: None)

    async def create_admin(api_url: str, email: str, password: str) -> None:
        return None

    async def healthy_report(self: object) -> DiagnosticReport:
        return DiagnosticReport(
            deployment_mode=DeploymentMode.LOCAL,
            checked_at="2026-01-01T00:00:00+00:00",
            duration_seconds=0.1,
            overall_status=CheckStatus.HEALTHY,
            checks=[],
        )

    monkeypatch.setattr(installer.migration_runner, "create_admin_user", create_admin)
    monkeypatch.setattr("platform_cli.installers.local.DiagnosticRunner.run", healthy_report)

    try:
        result = await installer.run()
        assert installer.sqlite_path.exists()
        assert installer.pid_path.exists()
        assert result.admin_email == config.admin.email
        assert result.admin_password is not None
        assert launched

        assert LocalInstaller.stop(config.data_dir) is True
        launched[0].wait(timeout=5)
        assert installer.pid_path.exists() is False
    finally:
        for process in launched:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
