from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from platform.common.database import database_health_check
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class DependencyHealth(BaseModel):
    status: str
    latency_ms: int


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: int
    profile: str
    dependencies: dict[str, DependencyHealth]


async def _run_check(check: Callable[[], Awaitable[Any]]) -> DependencyHealth:
    started = time.monotonic()
    try:
        result = await check()
    except Exception:
        healthy = False
    else:
        healthy = _is_healthy(result)
    latency_ms = int((time.monotonic() - started) * 1000)
    return DependencyHealth(status='healthy' if healthy else 'unhealthy', latency_ms=latency_ms)


def _is_healthy(result: Any) -> bool:
    if isinstance(result, bool):
        return result
    if isinstance(result, dict):
        status = result.get('status')
        if isinstance(status, str):
            return status.lower() in {'ok', 'healthy', 'green'}
        return False
    status = getattr(result, 'status', None)
    if isinstance(status, str):
        return status.lower() in {'ok', 'healthy', 'green'}
    return bool(result)


async def _build_health_response(request: Request) -> HealthResponse:
    clients = getattr(request.app.state, 'clients', {})
    checks: dict[str, Callable[[], Awaitable[Any]]] = {
        'postgresql': database_health_check,
        'redis': clients['redis'].health_check,
        'kafka': clients['kafka'].health_check,
        'qdrant': clients['qdrant'].health_check,
        'neo4j': clients['neo4j'].health_check,
        'clickhouse': clients['clickhouse'].health_check,
        'opensearch': clients['opensearch'].health_check,
        'object_storage': clients['object_storage'].health_check,
        'runtime_controller': clients['runtime_controller'].health_check,
        'reasoning_engine': clients['reasoning_engine'].health_check,
        'sandbox_manager': clients['sandbox_manager'].health_check,
        'simulation_controller': clients['simulation_controller'].health_check,
    }
    dependencies = {name: await _run_check(check) for name, check in checks.items()}
    unhealthy = {name for name, dep in dependencies.items() if dep.status == 'unhealthy'}
    if not unhealthy:
        status = 'healthy'
    elif 'postgresql' in unhealthy:
        status = 'unhealthy'
    else:
        status = 'degraded'
    started_at = getattr(request.app.state, 'started_at', time.monotonic())
    settings = request.app.state.settings
    return HealthResponse(
        status=status,
        uptime_seconds=int(time.monotonic() - started_at),
        profile=settings.profile,
        dependencies=dependencies,
    )


@router.get('/health', response_model=HealthResponse)
async def get_health(request: Request) -> HealthResponse:
    return await _build_health_response(request)


@router.get('/healthz', response_model=HealthResponse)
async def get_healthz(request: Request) -> HealthResponse:
    return await _build_health_response(request)


@router.get('/api/v1/healthz', response_model=HealthResponse)
async def get_api_healthz(request: Request) -> HealthResponse:
    return await _build_health_response(request)
