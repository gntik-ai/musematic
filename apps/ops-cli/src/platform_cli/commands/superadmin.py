"""Super-admin bootstrap and recovery commands."""

# mypy: disable-error-code=untyped-decorator

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from platform_cli.config import ExitCode
from platform_cli.output.console import get_console
from platform_cli.runtime import emit_event, exit_with_error

superadmin_app = typer.Typer(help="Manage super admins.", no_args_is_help=True)

_DEFAULT_EMERGENCY_KEY_PATH = Path("/etc/musematic/emergency-key.bin")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _control_plane_src() -> Path:
    return _repo_root() / "apps" / "control-plane" / "src"


def _bootstrap_env(
    *,
    username: str,
    email: str,
    password: str | None,
    password_file: Path | None,
    force_reset: bool,
    recovery: bool,
    platform_env: str | None,
    allow_reset: bool,
) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = str(_control_plane_src())
    if env.get("PYTHONPATH"):
        pythonpath = f"{pythonpath}{os.pathsep}{env['PYTHONPATH']}"
    env["PYTHONPATH"] = pythonpath
    env["PLATFORM_SUPERADMIN_USERNAME"] = username
    env["PLATFORM_SUPERADMIN_EMAIL"] = email
    env["PLATFORM_SUPERADMIN_CLI_MODE"] = "true"
    env["PLATFORM_SUPERADMIN_FORCE_PASSWORD_CHANGE"] = "true"
    if password is not None:
        env["PLATFORM_SUPERADMIN_PASSWORD"] = password
        env.pop("PLATFORM_SUPERADMIN_PASSWORD_FILE", None)
    if password_file is not None:
        env["PLATFORM_SUPERADMIN_PASSWORD_FILE"] = str(password_file)
        env.pop("PLATFORM_SUPERADMIN_PASSWORD", None)
    if force_reset:
        env["PLATFORM_FORCE_RESET_SUPERADMIN"] = "true"
    if recovery:
        env["PLATFORM_SUPERADMIN_RECOVERY"] = "true"
        env["PLATFORM_SUPERADMIN_MFA_ENROLLMENT"] = "required_before_first_login"
    if platform_env is not None:
        env["PLATFORM_ENV"] = platform_env
    if allow_reset:
        env["ALLOW_SUPERADMIN_RESET"] = "true"
    return env


def _run_bootstrap(ctx: typer.Context, env: dict[str, str], stage: str) -> None:
    emit_event(ctx, stage=stage, status="started", message="super-admin bootstrap started")
    result = subprocess.run(
        [sys.executable, "-m", "platform.admin.bootstrap"],
        env=env,
        check=False,
    )
    if result.returncode != 0:
        exit_with_error(
            ctx,
            f"super-admin bootstrap failed with exit code {result.returncode}",
            code=ExitCode.PREFLIGHT_FAILURE
            if result.returncode == int(ExitCode.PREFLIGHT_FAILURE.value)
            else ExitCode.GENERAL_ERROR,
        )
    emit_event(ctx, stage=stage, status="completed", message="super-admin bootstrap completed")


@superadmin_app.command("reset")
def reset_superadmin(
    ctx: typer.Context,
    username: Annotated[str, typer.Option("--username", envvar="PLATFORM_SUPERADMIN_USERNAME")],
    email: Annotated[str, typer.Option("--email", envvar="PLATFORM_SUPERADMIN_EMAIL")],
    force: Annotated[bool, typer.Option("--force", help="Required safety confirmation.")] = False,
    password: Annotated[
        str | None,
        typer.Option("--password", envvar="PLATFORM_SUPERADMIN_PASSWORD"),
    ] = None,
    password_file: Annotated[
        Path | None,
        typer.Option(
            "--password-file",
            exists=True,
            dir_okay=False,
            file_okay=True,
            resolve_path=True,
            envvar="PLATFORM_SUPERADMIN_PASSWORD_FILE",
        ),
    ] = None,
    platform_env: Annotated[str | None, typer.Option("--platform-env")] = None,
    allow_reset: Annotated[bool, typer.Option("--allow-reset")] = False,
) -> None:
    """Force-reset an existing super admin through the bootstrap safety path."""

    if not force:
        exit_with_error(
            ctx,
            "reset requires --force",
            code=ExitCode.PREFLIGHT_FAILURE,
        )
    env = _bootstrap_env(
        username=username,
        email=email,
        password=password,
        password_file=password_file,
        force_reset=True,
        recovery=False,
        platform_env=platform_env,
        allow_reset=allow_reset,
    )
    _run_bootstrap(ctx, env, "superadmin-reset")
    get_console().print(f"Reset requested for super admin {username}")


@superadmin_app.command("recover")
def recover_superadmin(
    ctx: typer.Context,
    username: Annotated[str, typer.Option("--username")],
    email: Annotated[str, typer.Option("--email")],
    emergency_key_path: Annotated[
        Path,
        typer.Option(
            "--emergency-key-path",
            exists=True,
            dir_okay=False,
            file_okay=True,
            resolve_path=True,
        ),
    ] = _DEFAULT_EMERGENCY_KEY_PATH,
    expected_hash: Annotated[
        str | None,
        typer.Option("--expected-hash", envvar="PLATFORM_EMERGENCY_KEY_SHA256"),
    ] = None,
    platform_env: Annotated[str | None, typer.Option("--platform-env")] = None,
) -> None:
    """Create a recovery super admin after validating the sealed emergency key."""

    if expected_hash is None:
        exit_with_error(
            ctx,
            "recover requires --expected-hash or PLATFORM_EMERGENCY_KEY_SHA256",
            code=ExitCode.PREFLIGHT_FAILURE,
        )
    actual_hash = hashlib.sha256(emergency_key_path.read_bytes()).hexdigest()
    if actual_hash.lower() != expected_hash.lower():
        exit_with_error(
            ctx,
            "emergency key hash mismatch",
            code=ExitCode.PREFLIGHT_FAILURE,
        )
    env = _bootstrap_env(
        username=username,
        email=email,
        password=None,
        password_file=None,
        force_reset=False,
        recovery=True,
        platform_env=platform_env,
        allow_reset=False,
    )
    _run_bootstrap(ctx, env, "superadmin-recover")
    get_console().print(f"Recovery requested for super admin {username}")
