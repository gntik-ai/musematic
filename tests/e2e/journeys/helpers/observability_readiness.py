from __future__ import annotations

import asyncio
import os
import time

import httpx


LOKI_READY_PATH = "/loki/api/v1/status/buildinfo"


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _loki_url() -> str:
    return _env("MUSEMATIC_E2E_LOKI_URL", "http://localhost:3100")


def _prom_url() -> str:
    return _env("MUSEMATIC_E2E_PROM_URL", "http://localhost:9090")


def _grafana_url() -> str:
    return _env("MUSEMATIC_E2E_GRAFANA_URL", "http://localhost:3000")


def _jaeger_url() -> str:
    return _env("MUSEMATIC_E2E_JAEGER_URL", "http://localhost:14269")


def _otel_url() -> str:
    return _env("MUSEMATIC_E2E_OTEL_URL", "http://localhost:13133")


async def _probe(name: str, url: str, path: str) -> tuple[str, bool, str]:
    endpoint = f"{url.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(endpoint)
        ok = 200 <= response.status_code < 300
        return name, ok, f"{endpoint} -> {response.status_code}"
    except Exception as exc:
        return name, False, f"{endpoint} -> {type(exc).__name__}: {exc}"


async def wait_for_observability_stack_ready(timeout_seconds: int = 180) -> None:
    configured_timeout = int(os.environ.get("MUSEMATIC_E2E_OBS_READY_TIMEOUT", timeout_seconds))
    deadline = time.monotonic() + configured_timeout
    probes = {
        "loki": (_loki_url(), LOKI_READY_PATH),
        "prometheus": (_prom_url(), "/-/ready"),
        "grafana": (_grafana_url(), "/api/health"),
        "jaeger": (_jaeger_url(), "/"),
        "otel": (_otel_url(), "/"),
    }
    last_seen: dict[str, str] = {}
    while time.monotonic() < deadline:
        results = await asyncio.gather(
            *[_probe(name, base_url, path) for name, (base_url, path) in probes.items()]
        )
        last_seen = {name: detail for name, _ok, detail in results}
        if all(ok for _name, ok, _detail in results):
            return
        await asyncio.sleep(1)
    diagnostics = "; ".join(f"{name}: {detail}" for name, detail in sorted(last_seen.items()))
    raise RuntimeError(
        f"observability stack not ready within {configured_timeout}s: {diagnostics}"
    )
