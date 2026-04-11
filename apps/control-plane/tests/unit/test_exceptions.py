from __future__ import annotations

from types import SimpleNamespace

import pytest

from platform.common.exceptions import (
    AuthorizationError,
    BudgetExceededError,
    ConvergenceFailedError,
    NotFoundError,
    PlatformError,
    platform_exception_handler,
)


@pytest.mark.asyncio
async def test_platform_exception_handler_returns_expected_shape() -> None:
    exc = NotFoundError("NOT_FOUND", "Missing resource", {"id": "123"})

    response = await platform_exception_handler(SimpleNamespace(), exc)

    assert response.status_code == 404
    assert response.body.decode("utf-8") == (
        '{"error":{"code":"NOT_FOUND","message":"Missing resource","details":{"id":"123"}}}'
    )


def test_exception_status_codes_match_contract() -> None:
    assert PlatformError.status_code == 500
    assert AuthorizationError("AUTH", "denied").status_code == 403
    assert BudgetExceededError("BUDGET", "limit").status_code == 429
    assert ConvergenceFailedError("CONVERGENCE", "failed").status_code == 500
