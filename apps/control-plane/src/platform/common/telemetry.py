from __future__ import annotations

from importlib import import_module
from typing import Any


def setup_telemetry(
    service_name: str,
    exporter_endpoint: str | None,
    *,
    app: Any | None = None,
    engine: Any | None = None,
) -> None:
    if not exporter_endpoint:
        return

    try:
        trace_module = import_module("opentelemetry.trace")
        exporter_module = import_module(
            "opentelemetry.exporter.otlp.proto.http.trace_exporter"
        )
        fastapi_module = import_module("opentelemetry.instrumentation.fastapi")
        grpc_module = import_module("opentelemetry.instrumentation.grpc")
        redis_module = import_module("opentelemetry.instrumentation.redis")
        sqlalchemy_module = import_module("opentelemetry.instrumentation.sqlalchemy")
        resources_module = import_module("opentelemetry.sdk.resources")
        trace_sdk_module = import_module("opentelemetry.sdk.trace")
        export_module = import_module("opentelemetry.sdk.trace.export")
    except Exception:
        return

    provider = trace_sdk_module.TracerProvider(
        resource=resources_module.Resource.create({"service.name": service_name})
    )
    provider.add_span_processor(
        export_module.BatchSpanProcessor(
            exporter_module.OTLPSpanExporter(endpoint=exporter_endpoint)
        )
    )
    trace_module.set_tracer_provider(provider)

    if app is not None:
        fastapi_module.FastAPIInstrumentor().instrument_app(app)
    if engine is not None:
        sqlalchemy_module.SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    redis_module.RedisInstrumentor().instrument()
    grpc_module.GrpcInstrumentorClient().instrument()
