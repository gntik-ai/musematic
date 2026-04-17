"""Structured NDJSON output helpers for headless execution."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, TextIO

_stream: TextIO = sys.stdout


def set_output_stream(stream: TextIO) -> None:
    """Override the output stream used for NDJSON emission."""

    global _stream
    _stream = stream


def reset_output_stream() -> None:
    """Reset the output stream back to stdout."""

    set_output_stream(sys.stdout)


def emit(
    stage: str,
    component: str | None,
    status: str,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> None:
    """Emit a single NDJSON event."""

    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": "error" if status in {"failed", "error", "unhealthy"} else "info",
        "stage": stage,
        "component": component,
        "status": status,
        "message": message,
        "details": dict(details or {}),
    }
    _stream.write(json.dumps(payload, sort_keys=True))
    _stream.write("\n")
    _stream.flush()
