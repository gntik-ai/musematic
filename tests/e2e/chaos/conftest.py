from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

import pytest


@pytest.fixture
def chaos_correlation_id() -> str:
    return f"chaos-{uuid4()}"


@pytest.fixture
def failure_injector():
    @contextmanager
    def _scale_to_zero(namespace: str, selector: str) -> Iterator[None]:
        if os.environ.get("MUSEMATIC_E2E_CHAOS_LIVE") != "1":
            yield
            return
        _kubectl(["-n", namespace, "scale", "deployment,statefulset", "-l", selector, "--replicas=0"])
        try:
            yield
        finally:
            _kubectl(["-n", namespace, "scale", "deployment,statefulset", "-l", selector, "--replicas=1"])

    return _scale_to_zero


def _kubectl(args: list[str]) -> None:
    result = subprocess.run(
        ["kubectl", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout
