from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.ws_hub.fanout import _FanoutMetrics
from platform.ws_hub.router import _RouterMetrics


class _FakeCounter:
    def __init__(self) -> None:
        self.values: list[int] = []

    def add(self, value: int) -> None:
        self.values.append(value)


class _FakeHistogram:
    def __init__(self) -> None:
        self.values: list[float] = []

    def record(self, value: float) -> None:
        self.values.append(value)


class _FakeMeter:
    def __init__(self) -> None:
        self.counters: dict[str, _FakeCounter] = {}
        self.histograms: dict[str, _FakeHistogram] = {}
        self.up_down_counters: dict[str, _FakeCounter] = {}

    def create_counter(self, name: str, **_: object) -> _FakeCounter:
        counter = _FakeCounter()
        self.counters[name] = counter
        return counter

    def create_histogram(self, name: str, **_: object) -> _FakeHistogram:
        histogram = _FakeHistogram()
        self.histograms[name] = histogram
        return histogram

    def create_up_down_counter(self, name: str, **_: object) -> _FakeCounter:
        counter = _FakeCounter()
        self.up_down_counters[name] = counter
        return counter


class _FakeMetricsModule:
    def __init__(self, meter: _FakeMeter) -> None:
        self._meter = meter

    def get_meter(self, _: str) -> _FakeMeter:
        return self._meter


def test_fanout_metrics_record_delivery_drop_and_latency(monkeypatch) -> None:
    meter = _FakeMeter()
    monkeypatch.setattr(
        "platform.ws_hub.fanout.import_module",
        lambda name: _FakeMetricsModule(meter),
    )

    metrics = _FanoutMetrics()
    metrics.delivered()
    metrics.dropped()
    metrics.observe_latency({"occurred_at": datetime.now(UTC) - timedelta(seconds=1)})
    metrics.observe_latency({"occurred_at": "2024-01-01T00:00:00Z"})
    metrics.observe_latency({"occurred_at": "not-a-date"})
    metrics.observe_latency({})

    assert meter.counters["ws_hub.events.delivered"].values == [1]
    assert meter.counters["ws_hub.events.dropped"].values == [1]
    assert len(meter.histograms["ws_hub.event_delivery_latency"].values) == 2
    assert all(value >= 0 for value in meter.histograms["ws_hub.event_delivery_latency"].values)


def test_fanout_metrics_degrade_gracefully_without_opentelemetry(monkeypatch) -> None:
    def failing_import(_: str) -> _FakeMetricsModule:
        raise RuntimeError("otel unavailable")

    monkeypatch.setattr("platform.ws_hub.fanout.import_module", failing_import)

    metrics = _FanoutMetrics()
    metrics.delivered()
    metrics.dropped()
    metrics.observe_latency({"occurred_at": datetime.now(UTC)})


def test_router_metrics_track_connection_open_close(monkeypatch) -> None:
    meter = _FakeMeter()
    monkeypatch.setattr(
        "platform.ws_hub.router.import_module",
        lambda name: _FakeMetricsModule(meter),
    )

    metrics = _RouterMetrics()
    metrics.connection_opened()
    metrics.connection_closed()

    assert meter.up_down_counters["ws_hub.connections.active"].values == [1, -1]


def test_router_metrics_degrade_gracefully_without_opentelemetry(monkeypatch) -> None:
    def failing_import(_: str) -> _FakeMetricsModule:
        raise RuntimeError("otel unavailable")

    monkeypatch.setattr("platform.ws_hub.router.import_module", failing_import)

    metrics = _RouterMetrics()
    metrics.connection_opened()
    metrics.connection_closed()
