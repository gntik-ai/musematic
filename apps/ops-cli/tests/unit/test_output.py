from __future__ import annotations

import io
import json

from platform_cli.output.console import (
    configure_console,
    create_progress,
    print_credentials_panel,
    print_error,
    print_status,
    print_step,
    print_table,
)
from platform_cli.output.structured import emit, set_output_stream


def test_console_helpers_render_to_configured_stream() -> None:
    stream = io.StringIO()
    configure_console(file=stream, no_color=True)

    print_status("postgresql", "healthy", 3.2)
    print_step(1, 3, "redis", "completed", 1.4)
    print_table(("A", "B"), [(1, 2)])
    print_credentials_panel("admin@example.com", "Secret123!", "http://localhost")
    print_error("boom", "fix it")
    progress = create_progress()

    with progress:
        task_id = progress.add_task("testing", total=1)
        progress.update(task_id, advance=1)

    output = stream.getvalue()
    assert "postgresql" in output
    assert "Admin Credentials" in output
    assert "fix it" in output


def test_structured_emit_writes_ndjson_line() -> None:
    stream = io.StringIO()
    set_output_stream(stream)

    emit(
        stage="diagnose",
        component="redis",
        status="failed",
        message="check failed",
        details={"reason": "timeout"},
    )

    payload = json.loads(stream.getvalue().strip())
    assert payload["stage"] == "diagnose"
    assert payload["component"] == "redis"
    assert payload["level"] == "error"
    assert payload["details"]["reason"] == "timeout"
