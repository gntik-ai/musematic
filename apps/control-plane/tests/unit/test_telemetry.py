from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

from platform.common.telemetry import setup_telemetry


def test_setup_telemetry_is_noop_without_exporter() -> None:
    setup_telemetry("service", "")


def test_setup_telemetry_handles_missing_optional_modules(monkeypatch) -> None:
    real_import = __import__

    def broken_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("opentelemetry"):
            raise ImportError("missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", broken_import)
    setup_telemetry("svc", "http://collector")


def test_setup_telemetry_instruments_when_modules_exist(monkeypatch) -> None:
    calls: dict[str, object] = {}

    def _module(name: str, **attributes):
        module = ModuleType(name)
        for key, value in attributes.items():
            setattr(module, key, value)
        return module

    class FakeProvider:
        def __init__(self, resource=None) -> None:
            calls["resource"] = resource

        def add_span_processor(self, processor) -> None:
            calls["processor"] = processor

    class FakeExporter:
        def __init__(self, endpoint: str) -> None:
            calls["endpoint"] = endpoint

    class FakeBatchSpanProcessor:
        def __init__(self, exporter) -> None:
            calls["exporter"] = exporter

    class FakeFastAPIInstrumentor:
        def instrument_app(self, app) -> None:
            calls["app"] = app

    class FakeSQLAlchemyInstrumentor:
        def instrument(self, engine) -> None:
            calls["engine"] = engine

    class FakeRedisInstrumentor:
        def instrument(self) -> None:
            calls["redis"] = True

    class FakeGrpcInstrumentorClient:
        def instrument(self) -> None:
            calls["grpc"] = True

    trace_module = _module("opentelemetry.trace", set_tracer_provider=lambda provider: calls.setdefault("provider", provider))
    monkeypatch.setitem(sys.modules, "opentelemetry", _module("opentelemetry", trace=trace_module))
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace_module)
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.exporter.otlp.proto.http.trace_exporter",
        _module("opentelemetry.exporter.otlp.proto.http.trace_exporter", OTLPSpanExporter=FakeExporter),
    )
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.instrumentation.fastapi",
        _module("opentelemetry.instrumentation.fastapi", FastAPIInstrumentor=FakeFastAPIInstrumentor),
    )
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.instrumentation.grpc",
        _module("opentelemetry.instrumentation.grpc", GrpcInstrumentorClient=FakeGrpcInstrumentorClient),
    )
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.instrumentation.redis",
        _module("opentelemetry.instrumentation.redis", RedisInstrumentor=FakeRedisInstrumentor),
    )
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.instrumentation.sqlalchemy",
        _module("opentelemetry.instrumentation.sqlalchemy", SQLAlchemyInstrumentor=FakeSQLAlchemyInstrumentor),
    )
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.sdk.resources",
        _module("opentelemetry.sdk.resources", Resource=SimpleNamespace(create=lambda attrs: attrs)),
    )
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.sdk.trace",
        _module("opentelemetry.sdk.trace", TracerProvider=FakeProvider),
    )
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.sdk.trace.export",
        _module("opentelemetry.sdk.trace.export", BatchSpanProcessor=FakeBatchSpanProcessor),
    )

    engine = SimpleNamespace(sync_engine="sync-engine")
    app = object()
    setup_telemetry("svc", "http://collector", app=app, engine=engine)

    assert calls["endpoint"] == "http://collector"
    assert calls["app"] is app
    assert calls["engine"] == "sync-engine"
    assert calls["redis"] is True
    assert calls["grpc"] is True
