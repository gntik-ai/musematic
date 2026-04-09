from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Kafka integration requires broker/testcontainers access")


async def test_dlq_after_three_failures() -> None:
    pass


async def test_no_dlq_when_second_attempt_succeeds() -> None:
    pass


async def test_dlq_retry_attempt_metadata() -> None:
    pass


async def test_offset_committed_after_dlq() -> None:
    pass

