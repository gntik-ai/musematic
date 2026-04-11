from __future__ import annotations

from datetime import UTC, datetime
from platform.connectors.retry import RetryScanner, compute_next_retry_at

import pytest


def test_compute_next_retry_at_uses_base_four_backoff() -> None:
    now = datetime.now(UTC)
    first = compute_next_retry_at(1)
    second = compute_next_retry_at(2)
    third = compute_next_retry_at(3)

    assert round((first - now).total_seconds()) == 1
    assert round((second - now).total_seconds()) == 4
    assert round((third - now).total_seconds()) == 16


@pytest.mark.asyncio
async def test_retry_scanner_delegates_to_executor() -> None:
    called: list[int] = []

    class Executor:
        async def retry_pending_deliveries(self, limit: int = 100) -> None:
            called.append(limit)

    await RetryScanner(Executor(), batch_limit=25).run()

    assert called == [25]
