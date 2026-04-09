from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Kafka integration requires broker/testcontainers access")


async def test_attention_topic_receives_attention_event() -> None:
    pass


async def test_attention_consumer_does_not_receive_monitor_alerts() -> None:
    pass


async def test_monitor_alert_consumer_does_not_receive_attention_events() -> None:
    pass

