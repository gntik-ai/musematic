from __future__ import annotations

from platform.analytics import clickhouse_setup
from platform.common.config import PlatformSettings

from tests.analytics_support import ClickHouseClientStub


async def test_run_setup_reuses_existing_client() -> None:
    client = ClickHouseClientStub()

    await clickhouse_setup.run_setup(client=client, settings=PlatformSettings())

    assert client.connected is False
    assert client.closed is False
    assert len(client.command_calls) == 7
    assert (
        "avgState(execution_duration_ms) AS avg_duration_ms_state"
        in clickhouse_setup.USAGE_MONTHLY_DDL
    )
    assert "goal_id Nullable(UUID)" in clickhouse_setup.USAGE_EVENTS_DDL
    assert "analytics_usage_hourly_v2" in clickhouse_setup.USAGE_HOURLY_MV_DDL


async def test_run_setup_creates_and_closes_client_when_needed(monkeypatch) -> None:
    client = ClickHouseClientStub()
    created_settings: list[PlatformSettings] = []

    def _fake_from_settings(settings: PlatformSettings) -> ClickHouseClientStub:
        created_settings.append(settings)
        return client

    monkeypatch.setattr(
        clickhouse_setup.AsyncClickHouseClient,
        "from_settings",
        _fake_from_settings,
    )
    settings = PlatformSettings()

    await clickhouse_setup.run_setup(settings=settings)

    assert created_settings == [settings]
    assert client.connected is True
    assert client.closed is True


def test_main_delegates_to_asyncio_run(monkeypatch) -> None:
    captured: list[object] = []

    def _fake_run(coro: object) -> None:
        captured.append(coro)
        close = getattr(coro, "close", None)
        if callable(close):
            close()

    monkeypatch.setattr(clickhouse_setup.asyncio, "run", _fake_run)

    clickhouse_setup.main()

    assert len(captured) == 1
