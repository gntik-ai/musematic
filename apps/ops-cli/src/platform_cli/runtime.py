"""Runtime helpers shared by Typer commands."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

from platform_cli.config import ExitCode, InstallerConfig, load_config
from platform_cli.output.console import print_error
from platform_cli.output.structured import emit

DEFAULT_CONFIG_NAME = "platform-install.yaml"


@dataclass(slots=True)
class CLIState:
    """Global runtime state initialised by the root Typer callback."""

    config_path: Path | None
    verbose: bool
    json_output: bool
    no_color: bool


def get_state(ctx: typer.Context) -> CLIState:
    """Return the current CLI state from the Typer context."""

    state = ctx.obj
    if not isinstance(state, CLIState):
        raise RuntimeError("CLI state has not been initialised.")
    return state


def resolve_config_path(state: CLIState) -> Path | None:
    """Resolve the effective config path for a command."""

    if state.config_path is not None:
        return state.config_path
    default = Path.cwd() / DEFAULT_CONFIG_NAME
    if default.exists():
        return default
    return None


def load_runtime_config(ctx: typer.Context, **overrides: Any) -> InstallerConfig:
    """Load config from file/env and apply explicit command-line overrides."""

    state = get_state(ctx)
    config = load_config(resolve_config_path(state))
    cleaned = {key: value for key, value in overrides.items() if value is not None}
    if not cleaned:
        return config
    return config.model_copy(update=cleaned)


def emit_event(
    ctx: typer.Context,
    *,
    stage: str,
    status: str,
    message: str,
    component: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Emit a structured event when the CLI runs in headless mode."""

    if get_state(ctx).json_output:
        emit(stage=stage, component=component, status=status, message=message, details=details)


def exit_with_error(
    ctx: typer.Context,
    message: str,
    *,
    code: ExitCode = ExitCode.GENERAL_ERROR,
    remediation: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Render an error for humans, or emit one for headless callers, and exit."""

    state = get_state(ctx)
    if state.json_output:
        emit(
            stage="error",
            component=None,
            status="failed",
            message=message,
            details=details or {"remediation": remediation},
        )
    else:
        print_error(message, remediation)
    raise typer.Exit(int(code.value))


def inferred_api_base_url(config: InstallerConfig) -> str:
    """Derive the control plane base URL from config when it is not explicit."""

    if config.api_base_url:
        return config.api_base_url.rstrip("/")
    if config.deployment_mode.value == "local":
        return "http://127.0.0.1:8000"
    scheme = "https" if config.ingress.tls_enabled else "http"
    return f"{scheme}://{config.ingress.hostname}".rstrip("/")
