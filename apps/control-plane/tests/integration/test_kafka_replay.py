from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Kafka integration requires broker/testcontainers access")


async def test_replay_from_timestamp() -> None:
    pass

