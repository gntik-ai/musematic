from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx
import pytest

from fixtures.http_client import AuthenticatedAsyncClient

pytest_plugins = [
    "fixtures.http_client",
    "fixtures.ws_client",
    "fixtures.db_session",
    "fixtures.kafka_consumer",
    "fixtures.workspace",
    "fixtures.agent",
    "fixtures.policy",
    "fixtures.mock_llm",
]

_SETUP_RETRY_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)
_SETUP_RETRY_ATTEMPTS = 6


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


@pytest.fixture(scope="session")
def db_dsn() -> str:
    return os.environ.get(
        "E2E_DB_DSN",
        "postgresql://e2e_reader:e2e-reader@localhost:5432/platform",
    )


@pytest.fixture(scope="session")
def kafka_bootstrap() -> str:
    return os.environ.get("E2E_KAFKA_BOOTSTRAP", "localhost:9092")


@pytest.fixture(scope="session", autouse=True)
async def ensure_seeded(platform_api_url: str) -> None:
    async with AuthenticatedAsyncClient(platform_api_url) as client:
        last_error: Exception | None = None
        for attempt in range(_SETUP_RETRY_ATTEMPTS):
            try:
                await client.login_as("admin@e2e.test", "e2e-test-password")
                response = await client.post("/api/v1/_e2e/seed", json={"scope": "all"})
                assert response.status_code == 200, response.text
                return
            except _SETUP_RETRY_EXCEPTIONS as exc:
                last_error = exc
                if attempt < _SETUP_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(min(2**attempt, 10))
        if last_error is not None:
            raise last_error


@pytest.fixture(autouse=True)
async def reset_ephemeral_state(request: pytest.FixtureRequest, http_client) -> None:
    path = Path(str(request.node.fspath))
    if "chaos" not in path.parts and "performance" not in path.parts:
        return
    response = await http_client.post(
        "/api/v1/_e2e/reset",
        json={"scope": "all", "include_baseline": False},
    )
    assert response.status_code == 200, response.text
