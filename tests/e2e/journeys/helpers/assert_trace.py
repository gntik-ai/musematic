"""Jaeger trace assertions.

Contract: specs/085-extended-e2e-journey/contracts/observability-helpers.md
"""

from __future__ import annotations

import asyncio
import time

import httpx


async def assert_trace_exists(
    jaeger_client: httpx.AsyncClient,
    trace_id: str,
    expected_services: list[str],
    expected_operations: list[str] | None = None,
    within_seconds: int = 30,
) -> dict:
    deadline = time.monotonic() + within_seconds
    last_services: set[str] = set()
    last_operations: set[str] = set()
    expected_service_set = set(expected_services)
    expected_operation_set = set(expected_operations or [])

    while time.monotonic() < deadline:
        response = await jaeger_client.get(f"/api/traces/{trace_id}")
        if response.status_code == 404:
            await asyncio.sleep(1)
            continue
        response.raise_for_status()
        payload = response.json()
        traces = payload.get("data", [])
        for trace in traces:
            processes = trace.get("processes", {})
            spans = trace.get("spans", [])
            service_by_process = {
                process_id: process.get("serviceName")
                for process_id, process in processes.items()
                if isinstance(process, dict)
            }
            last_services = {
                service
                for service in service_by_process.values()
                if isinstance(service, str) and service
            }
            last_operations = {
                str(span.get("operationName"))
                for span in spans
                if span.get("operationName")
            }
            if expected_service_set <= last_services and expected_operation_set <= last_operations:
                return trace
        await asyncio.sleep(1)

    raise AssertionError(
        f"Jaeger trace {trace_id} missing expected services/operations within {within_seconds}s; "
        f"expected_services={sorted(expected_service_set)!r}; actual_services={sorted(last_services)!r}; "
        f"expected_operations={sorted(expected_operation_set)!r}; "
        f"actual_operations={sorted(last_operations)!r}"
    )
