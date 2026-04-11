from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


def compute_next_retry_at(attempt_count: int) -> datetime:
    delay_seconds = 4 ** max(attempt_count - 1, 0)
    return datetime.now(UTC) + timedelta(seconds=delay_seconds)


class RetryExecutor(Protocol):
    async def retry_pending_deliveries(self, limit: int = 100) -> None: ...


class RetryScanner:
    def __init__(self, executor: RetryExecutor, *, batch_limit: int = 100) -> None:
        self.executor = executor
        self.batch_limit = batch_limit

    async def run(self) -> None:
        await self.executor.retry_pending_deliveries(limit=self.batch_limit)
