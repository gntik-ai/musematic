from __future__ import annotations

import os

import pytest

from suites.ui_playwright import ui_page as ui_page  # noqa: F401


@pytest.fixture
def platform_status_url(platform_ui_url: str) -> str:
    return os.environ.get("PLATFORM_STATUS_URL", platform_ui_url)


@pytest.fixture(scope="session", autouse=True)
async def ensure_seeded() -> None:
    """Platform-state UI tests use route fixtures instead of the live seed API."""


@pytest.fixture(autouse=True)
async def reset_ephemeral_state() -> None:
    """Avoid live reset calls for route-backed platform-state UI tests."""
