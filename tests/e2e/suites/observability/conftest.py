from __future__ import annotations

import asyncio
import os

import httpx
import pytest
import pytest_asyncio

from journeys.helpers.observability_readiness import wait_for_observability_stack_ready


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _loki_url() -> str:
    return _env("MUSEMATIC_E2E_LOKI_URL", "http://localhost:3100")


def _prom_url() -> str:
    return _env("MUSEMATIC_E2E_PROM_URL", "http://localhost:9090")


def _grafana_url() -> str:
    return _env("MUSEMATIC_E2E_GRAFANA_URL", "http://localhost:3000")


def _jaeger_url() -> str:
    return _env("MUSEMATIC_E2E_JAEGER_URL", "http://localhost:14269")


def _alertmanager_url() -> str:
    return _env("MUSEMATIC_E2E_ALERTMANAGER_URL", "http://localhost:9093")


def _grafana_auth() -> httpx.Auth | None:
    token = os.environ.get("MUSEMATIC_E2E_GRAFANA_TOKEN")
    if token:
        return None
    user = _env("MUSEMATIC_E2E_GRAFANA_USER", "admin")
    password = _env("MUSEMATIC_E2E_GRAFANA_PASSWORD", "admin")
    return httpx.BasicAuth(user, password)


def _grafana_headers() -> dict[str, str]:
    token = os.environ.get("MUSEMATIC_E2E_GRAFANA_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


@pytest.fixture(scope="session")
def observability_stack_ready() -> None:
    asyncio.run(wait_for_observability_stack_ready())


@pytest_asyncio.fixture
async def loki_client(observability_stack_ready: None):
    del observability_stack_ready
    async with httpx.AsyncClient(base_url=_loki_url(), timeout=30.0) as client:
        yield client


@pytest_asyncio.fixture
async def prom_client(observability_stack_ready: None):
    del observability_stack_ready
    async with httpx.AsyncClient(base_url=_prom_url(), timeout=30.0) as client:
        yield client


@pytest_asyncio.fixture
async def grafana_client(observability_stack_ready: None):
    del observability_stack_ready
    async with httpx.AsyncClient(
        base_url=_grafana_url(),
        auth=_grafana_auth(),
        headers=_grafana_headers(),
        timeout=30.0,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def jaeger_client(observability_stack_ready: None):
    del observability_stack_ready
    async with httpx.AsyncClient(base_url=_jaeger_url(), timeout=30.0) as client:
        yield client


@pytest_asyncio.fixture
async def alertmanager_client(observability_stack_ready: None):
    del observability_stack_ready
    async with httpx.AsyncClient(base_url=_alertmanager_url(), timeout=30.0) as client:
        yield client
