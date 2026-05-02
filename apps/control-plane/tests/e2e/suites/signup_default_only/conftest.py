from __future__ import annotations

import os
from uuid import uuid4

import pytest


@pytest.fixture
def signup_default_e2e() -> None:
    if os.environ.get("RUN_SIGNUP_DEFAULT_ONLY_E2E") != "true":
        pytest.skip("set RUN_SIGNUP_DEFAULT_ONLY_E2E=true to run UPD-048 E2E checks")


@pytest.fixture
def platform_api_url() -> str:
    return os.environ.get("PLATFORM_API_URL", "http://localhost:8081")


@pytest.fixture
def platform_ui_url() -> str:
    return os.environ.get("PLATFORM_UI_URL", "http://localhost:8080")


@pytest.fixture
def default_tenant_host() -> str:
    return os.environ.get("DEFAULT_TENANT_HOST", "app.localhost")


@pytest.fixture
def acme_tenant_host() -> str:
    return os.environ.get("ACME_TENANT_HOST", "acme.localhost")


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}@e2e.test"
