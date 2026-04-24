from __future__ import annotations

import hashlib
import logging
import time
from importlib import import_module
from math import ceil
from platform.common import database
from platform.common.auth_middleware import EXEMPT_PATHS
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.rate_limiter.repository import RateLimiterRepository
from platform.common.rate_limiter.service import (
    RateLimiterService,
    RateLimitEvaluation,
    ResolvedRateLimitPolicy,
)
from typing import Any, cast

from fastapi.responses import JSONResponse, Response
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request

LOGGER = logging.getLogger(__name__)
NO_RATE_LIMIT_PATHS: frozenset[str] = frozenset({"/health", "/healthz", "/api/v1/healthz"})


class _RateLimitMetrics:
    def __init__(self) -> None:
        self._decisions = None
        self._duration = None
        self._redis_errors = None
        self._fail_open = None
        try:
            metrics_module = import_module("opentelemetry.metrics")
            meter = metrics_module.get_meter(__name__)
            self._decisions = meter.create_counter(
                "rate_limit_decisions_total",
                description="Rate-limit decisions by principal kind and tier.",
                unit="{decision}",
            )
            self._duration = meter.create_histogram(
                "rate_limit_enforcement_duration_seconds",
                description="Time spent evaluating API rate limits.",
                unit="s",
            )
            self._redis_errors = meter.create_counter(
                "rate_limit_redis_errors_total",
                description="Redis failures while enforcing rate limits.",
                unit="{error}",
            )
            self._fail_open = meter.create_counter(
                "rate_limit_fail_open_activations_total",
                description="Fail-open activations for the rate limiter.",
                unit="{activation}",
            )
        except Exception:
            self._decisions = None
            self._duration = None
            self._redis_errors = None
            self._fail_open = None

    def decision(self, decision: str, principal_kind: str, tier: str) -> None:
        if self._decisions is not None:
            self._decisions.add(
                1,
                attributes={"decision": decision, "principal_kind": principal_kind, "tier": tier},
            )

    def duration(self, principal_kind: str, value: float) -> None:
        if self._duration is not None:
            self._duration.record(value, attributes={"principal_kind": principal_kind})

    def redis_error(self, reason: str) -> None:
        if self._redis_errors is not None:
            self._redis_errors.add(1, attributes={"reason": reason})

    def fail_open(self) -> None:
        if self._fail_open is not None:
            self._fail_open.add(1)


METRICS = _RateLimitMetrics()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = self._settings(request)
        if (
            not settings.api_governance.rate_limiting_enabled
        ) or request.url.path in NO_RATE_LIMIT_PATHS:
            return await call_next(request)

        async with database.AsyncSessionLocal() as session:
            service = getattr(request.app.state, "rate_limiter_service", None)
            if service is None:
                service = RateLimiterService(
                    repository=RateLimiterRepository(session),
                    redis_client=self._redis(request),
                    settings=settings,
                )

            principal_kind, principal_key, anonymous = self._principal(request)
            start = time.perf_counter()
            try:
                policy = await self._resolve_policy(
                    service, principal_kind, principal_key, anonymous
                )
                evaluation = await service.enforce_policy(policy)
            except RedisError as exc:
                METRICS.redis_error(type(exc).__name__)
                LOGGER.warning(
                    "rate limiter redis unavailable",
                    extra={
                        "redis_unreachable": True,
                        "principal_kind": principal_kind,
                        "principal_id_hash": hashlib.sha256(
                            principal_key.encode("utf-8")
                        ).hexdigest(),
                    },
                )
                policy = await self._resolve_policy(
                    service, principal_kind, principal_key, anonymous, use_cache=False
                )
                if settings.api_governance.rate_limiting_fail_open:
                    METRICS.fail_open()
                    LOGGER.warning("rate limiter fail-open activated", extra={"fail_open": True})
                    response = await call_next(request)
                    self._apply_headers(
                        response,
                        evaluation=None,
                        limit=policy.requests_per_minute,
                        remaining="unknown",
                    )
                    return response
                response = JSONResponse(
                    status_code=503,
                    content={"error": "rate_limit_service_unavailable"},
                )
                response.headers["Retry-After"] = "30"
                self._apply_headers(
                    response, evaluation=None, limit=policy.requests_per_minute, remaining="0"
                )
                return response
            finally:
                METRICS.duration(principal_kind, max(time.perf_counter() - start, 0.0))

            if not evaluation.decision.allowed:
                METRICS.decision("blocked", principal_kind, evaluation.policy.tier_name)
                response = JSONResponse(status_code=429, content={"error": "rate_limit_exceeded"})
                self._apply_headers(
                    response,
                    evaluation=evaluation,
                    limit=evaluation.policy.requests_per_minute,
                    remaining=str(self._remaining_value(evaluation)),
                )
                response.headers["Retry-After"] = str(
                    max(ceil(evaluation.decision.retry_after_ms / 1000), 1)
                )
                return response

            METRICS.decision("allowed", principal_kind, evaluation.policy.tier_name)
            response = await call_next(request)
            self._apply_headers(
                response,
                evaluation=evaluation,
                limit=evaluation.policy.requests_per_minute,
                remaining=str(self._remaining_value(evaluation)),
            )
            return response

    async def _resolve_policy(
        self,
        service: RateLimiterService,
        principal_kind: str,
        principal_key: str,
        anonymous: bool,
        *,
        use_cache: bool = True,
    ) -> ResolvedRateLimitPolicy:
        if anonymous:
            return await service.resolve_anonymous_policy(principal_key, use_cache=use_cache)
        return await service.resolve_policy_for_principal(
            principal_kind,
            principal_key,
            use_cache=use_cache,
        )

    @staticmethod
    def _settings(request: Request) -> PlatformSettings:
        return cast(PlatformSettings, request.app.state.settings)

    @staticmethod
    def _redis(request: Request) -> AsyncRedisClient:
        return cast(AsyncRedisClient, request.app.state.clients["redis"])

    @staticmethod
    def _source_ip(request: Request) -> str:
        forwarded_for = request.headers.get("X-Forwarded-For", "").strip()
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip()
        if request.client is not None and request.client.host:
            return request.client.host
        return "unknown"

    @staticmethod
    def _principal(request: Request) -> tuple[str, str, bool]:
        state_user = getattr(request.state, "user", None)
        if isinstance(state_user, dict):
            principal_kind = str(state_user.get("principal_type") or "user")
            principal_id = str(
                state_user.get("principal_id") or state_user.get("sub") or "anonymous"
            )
            return principal_kind, principal_id, False
        if request.url.path in EXEMPT_PATHS or request.url.path.startswith(
            "/api/v1/accounts/invitations/"
        ):
            return "anon", RateLimitMiddleware._source_ip(request), True
        return "anon", RateLimitMiddleware._source_ip(request), True

    @staticmethod
    def _remaining_value(evaluation: RateLimitEvaluation) -> int:
        return min(
            evaluation.decision.remaining_minute,
            evaluation.decision.remaining_hour,
            evaluation.decision.remaining_day,
        )

    @staticmethod
    def _apply_headers(
        response: Response,
        *,
        evaluation: RateLimitEvaluation | None,
        limit: int,
        remaining: str,
    ) -> None:
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = remaining
        response.headers["X-RateLimit-Reset"] = str(
            evaluation.reset_epoch_seconds if evaluation is not None else ceil(time.time() + 60)
        )
