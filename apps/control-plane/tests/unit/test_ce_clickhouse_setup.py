from __future__ import annotations

import asyncio
from platform.common.config import PlatformSettings
from platform.context_engineering import context_engineering_clickhouse_setup as ce_setup

from tests.analytics_support import ClickHouseClientStub


async def test_context_engineering_clickhouse_setup_reuses_existing_client() -> None:
    client = ClickHouseClientStub()

    await ce_setup.run_setup(client=client, settings=PlatformSettings())

    assert len(client.command_calls) == 1
    assert "context_quality_scores" in client.command_calls[0][0]


async def test_context_engineering_clickhouse_setup_creates_and_closes_client(monkeypatch) -> None:
    client = ClickHouseClientStub()

    def _fake_from_settings(settings: PlatformSettings) -> ClickHouseClientStub:
        del settings
        return client

    monkeypatch.setattr(ce_setup.AsyncClickHouseClient, "from_settings", _fake_from_settings)

    await ce_setup.run_setup(settings=PlatformSettings())

    assert client.connected is True
    assert client.closed is True


def test_context_engineering_clickhouse_setup_main_uses_asyncio_run(monkeypatch) -> None:
    captured = {}

    def _fake_run(coro):
        captured["name"] = coro.cr_code.co_name
        coro.close()

    monkeypatch.setattr(asyncio, "run", _fake_run)

    ce_setup.main()

    assert captured["name"] == "run_setup"
