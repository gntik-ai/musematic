from __future__ import annotations

import os

import pytest


def _port(name: str, default: str) -> str:
    return os.environ.get(name, default)


@pytest.fixture(scope="session")
def platform_api_url() -> str:
    return os.environ.get("PLATFORM_API_URL", f"http://localhost:{_port('PORT_API', '8081')}")


@pytest.fixture(scope="session")
def platform_ws_url() -> str:
    return os.environ.get("PLATFORM_WS_URL", f"ws://localhost:{_port('PORT_WS', '8082')}")


@pytest.fixture(scope="session")
def platform_ui_url() -> str:
    return os.environ.get("PLATFORM_UI_URL", f"http://localhost:{_port('PORT_UI', '8080')}")
