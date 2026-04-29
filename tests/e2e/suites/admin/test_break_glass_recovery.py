from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_break_glass_recovery_command_documents_emergency_key_and_audit() -> None:
    command = (ROOT / "apps/ops-cli/src/platform_cli/commands/superadmin.py").read_text()

    assert "recover" in command
    assert "/etc/musematic/emergency-key.bin" in command
    assert "platform.superadmin.break_glass_recovery" in command
    assert "severity=\"critical\"" in command or "severity='critical'" in command
    assert "exit code 2" in command or "raise typer.Exit(2)" in command
