"""Generic gRPC health-check implementation."""

from __future__ import annotations

from time import perf_counter

from platform_cli.constants import ComponentCategory
from platform_cli.models import CheckStatus, DiagnosticCheck


class GrpcServiceCheck:
    """Run the standard gRPC health check against a service endpoint."""

    def __init__(self, host: str, port: int, component: str, display_name: str) -> None:
        self.host = host
        self.port = port
        self.component = component
        self.display_name = display_name
        self.name = component

    async def run(self) -> DiagnosticCheck:
        import grpc
        from grpc_health.v1 import health_pb2, health_pb2_grpc

        started = perf_counter()
        try:
            async with grpc.aio.insecure_channel(f"{self.host}:{self.port}") as channel:
                stub = health_pb2_grpc.HealthStub(channel)
                response = await stub.Check(health_pb2.HealthCheckRequest())
            status = (
                CheckStatus.HEALTHY
                if response.status == health_pb2.HealthCheckResponse.SERVING
                else CheckStatus.UNHEALTHY
            )
        except Exception as exc:
            return DiagnosticCheck(
                component=self.component,
                display_name=self.display_name,
                category=ComponentCategory.SATELLITE_SERVICE,
                status=CheckStatus.UNHEALTHY,
                error=str(exc),
                remediation=f"Check {self.display_name} gRPC endpoint.",
            )
        latency_ms = round((perf_counter() - started) * 1000, 2)
        return DiagnosticCheck(
            component=self.component,
            display_name=self.display_name,
            category=ComponentCategory.SATELLITE_SERVICE,
            status=status,
            latency_ms=latency_ms,
        )
