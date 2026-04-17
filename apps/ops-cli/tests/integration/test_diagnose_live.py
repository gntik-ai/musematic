from __future__ import annotations

import asyncio
import io
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from typer.testing import CliRunner

from platform_cli.commands import diagnose as diagnose_commands
from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.diagnostics import checker as diagnostic_checker
from platform_cli.diagnostics.checker import DiagnosticRunner
from platform_cli.diagnostics.checks.model_providers import ModelProviderCheck
from platform_cli.diagnostics.checks.opensearch import OpenSearchCheck
from platform_cli.diagnostics.checks.qdrant import QdrantCheck
from platform_cli.main import app
from platform_cli.models import CheckStatus
from platform_cli.output.structured import set_output_stream


@contextmanager
def _live_http_service() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/healthz":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
                return
            if self.path == "/_cluster/health":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status":"green"}')
                return
            if self.path == "/model":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ready":true}')
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, fmt: str, *args: object) -> None:
            return None

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_diagnostic_runner_live_checks_and_cli_exit_codes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = InstallerConfig(data_dir=tmp_path, deployment_mode=DeploymentMode.LOCAL)

    with _live_http_service() as base_url:
        live_runner = DiagnosticRunner(config)
        monkeypatch.setattr(
            live_runner,
            "build_checks",
            lambda: [
                QdrantCheck(base_url),
                OpenSearchCheck(base_url),
                ModelProviderCheck(f"{base_url}/model"),
            ],
        )
        report = await live_runner.run(timeout_per_check=2)

        assert report.overall_status == CheckStatus.HEALTHY
        assert {item.component for item in report.checks} == {
            "qdrant",
            "opensearch",
            f"{base_url}/model",
        }

        runner = CliRunner()
        monkeypatch.chdir(tmp_path)
        (tmp_path / "platform-install.yaml").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(
            diagnose_commands,
            "load_runtime_config",
            lambda ctx, **overrides: config.model_copy(update=overrides),
        )
        monkeypatch.setattr(
            diagnostic_checker.DiagnosticRunner,
            "build_checks",
            lambda self: [
                QdrantCheck(base_url),
                OpenSearchCheck(base_url),
                ModelProviderCheck(f"{base_url}/model"),
            ],
        )

        ok_stream = io.StringIO()
        set_output_stream(ok_stream)
        ok_result = await asyncio.to_thread(
            runner.invoke,
            app,
            ["--json", "diagnose", "--deployment-mode", "local"],
        )
        ok_payload = json.loads(ok_stream.getvalue().strip())

        assert ok_result.exit_code == 0
        assert ok_payload["status"] == "healthy"
        assert ok_payload["details"]["overall_status"] == "healthy"

        bad_stream = io.StringIO()
        set_output_stream(bad_stream)
        monkeypatch.setattr(
            diagnostic_checker.DiagnosticRunner,
            "build_checks",
            lambda self: [ModelProviderCheck("http://127.0.0.1:1/unreachable")],
        )
        bad_result = await asyncio.to_thread(
            runner.invoke,
            app,
            ["--json", "diagnose", "--deployment-mode", "local"],
        )
        bad_payload = json.loads(bad_stream.getvalue().strip())

        assert bad_result.exit_code == 3
        assert bad_payload["status"] == "unhealthy"
        assert bad_payload["details"]["overall_status"] == "unhealthy"
