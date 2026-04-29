from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session")
def mock_google_oidc() -> str:
    return os.environ.get("MOCK_GOOGLE_OIDC_URL", "http://localhost:8083")


@pytest.fixture(scope="session")
def mock_github_oauth() -> str:
    return os.environ.get("MOCK_GITHUB_OAUTH_URL", "http://localhost:8084")
