from __future__ import annotations

import pytest

from suites.ui_playwright import ui_page as ui_page  # noqa: F401


@pytest.fixture(scope="session", autouse=True)
async def ensure_seeded() -> None:
    """Simulation UI tests use route fixtures instead of the live seed API."""


@pytest.fixture(autouse=True)
async def reset_ephemeral_state() -> None:
    """Avoid live reset calls for route-backed simulation UI tests."""
