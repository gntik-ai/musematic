from __future__ import annotations

from dataclasses import dataclass
from platform.common.auth_middleware import AuthMiddleware
from platform.common.clients.redis import MultiWindowRateLimitResult
from platform.common.config import PlatformSettings
from platform.common.middleware.rate_limit_middleware import RateLimitMiddleware
from platform.common.rate_limiter.service import RateLimitEvaluation, ResolvedRateLimitPolicy
from uuid import uuid4

import httpx
import jwt
import pytest
from fastapi import FastAPI, Request
from redis.exceptions import RedisError


@dataclass(slots=True)
class _Scenario:
    policy: ResolvedRateLimitPolicy
    responses: list[RateLimitEvaluation | Exception]


class FakeRateLimiterService:
    def __init__(
        self, scenarios: dict[str, _Scenario], *, anonymous: _Scenario | None = None
    ) -> None:
        self.scenarios = scenarios
        self.anonymous = anonymous
        self.calls: list[tuple[str, str, bool]] = []

    async def resolve_policy_for_principal(
        self,
        principal_type: str,
        principal_id: str,
        *,
        use_cache: bool = True,
    ) -> ResolvedRateLimitPolicy:
        del use_cache
        scenario = self.scenarios[f"{principal_type}:{principal_id}"]
        self.calls.append((principal_type, principal_id, False))
        return scenario.policy

    async def resolve_anonymous_policy(
        self,
        source_ip: str,
        *,
        use_cache: bool = True,
    ) -> ResolvedRateLimitPolicy:
        del use_cache
        assert self.anonymous is not None
        self.calls.append(("anon", source_ip, True))
        return self.anonymous.policy

    async def enforce_policy(self, policy: ResolvedRateLimitPolicy) -> RateLimitEvaluation:
        if policy.anonymous:
            assert self.anonymous is not None
            item = self.anonymous.responses.pop(0)
        else:
            item = self.scenarios[f"{policy.principal_kind}:{policy.principal_key}"].responses.pop(
                0
            )
        if isinstance(item, Exception):
            raise item
        return item


def _policy(
    kind: str,
    key: str,
    *,
    tier: str = "default",
    rpm: int = 300,
    rph: int = 10_000,
    rpd: int = 100_000,
    anonymous: bool = False,
) -> ResolvedRateLimitPolicy:
    return ResolvedRateLimitPolicy(
        principal_kind=kind,
        principal_key=key,
        tier_name=tier,
        requests_per_minute=rpm,
        requests_per_hour=rph,
        requests_per_day=rpd,
        anonymous=anonymous,
    )


def _evaluation(
    policy: ResolvedRateLimitPolicy,
    *,
    allowed: bool,
    rem_min: int,
    rem_hour: int,
    rem_day: int,
    retry_after_ms: int = 0,
    reset_epoch_seconds: int = 1_700_000_000,
) -> RateLimitEvaluation:
    return RateLimitEvaluation(
        policy=policy,
        decision=MultiWindowRateLimitResult(
            allowed=allowed,
            remaining_minute=rem_min,
            remaining_hour=rem_hour,
            remaining_day=rem_day,
            retry_after_ms=retry_after_ms,
        ),
        reset_epoch_seconds=reset_epoch_seconds,
    )


def _settings(*, fail_open: bool = False, rate_limiting_enabled: bool = True) -> PlatformSettings:
    return PlatformSettings(
        AUTH_JWT_SECRET_KEY="a" * 32,
        AUTH_JWT_ALGORITHM="HS256",
        FEATURE_API_RATE_LIMITING=rate_limiting_enabled,
        FEATURE_API_RATE_LIMITING_FAIL_OPEN=fail_open,
    )


def _token(secret: str, sub: str) -> str:
    return jwt.encode(
        {"sub": sub, "principal_id": sub, "type": "access"}, secret, algorithm="HS256"
    )


def _build_app(settings: PlatformSettings, service: FakeRateLimiterService) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
    app.state.rate_limiter_service = service
    app.state.clients = {"redis": object()}
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuthMiddleware)

    @app.get("/api/v1/limited")
    async def limited(request: Request) -> dict[str, object]:
        return {"ok": True, "sub": request.state.user.get("sub")}

    @app.get("/api/docs")
    async def docs() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_t1_below_budget_headers_decrease() -> None:
    user_id = str(uuid4())
    policy = _policy("user", user_id)
    service = FakeRateLimiterService(
        {
            f"user:{user_id}": _Scenario(
                policy,
                [
                    _evaluation(policy, allowed=True, rem_min=299, rem_hour=9_999, rem_day=99_999),
                    _evaluation(policy, allowed=True, rem_min=298, rem_hour=9_998, rem_day=99_998),
                    _evaluation(policy, allowed=True, rem_min=297, rem_hour=9_997, rem_day=99_997),
                ],
            )
        }
    )
    app = _build_app(_settings(), service)
    token = _token(app.state.settings.auth.verification_key, user_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        responses = [
            await client.get("/api/v1/limited", headers={"Authorization": f"Bearer {token}"}),
            await client.get("/api/v1/limited", headers={"Authorization": f"Bearer {token}"}),
            await client.get("/api/v1/limited", headers={"Authorization": f"Bearer {token}"}),
        ]

    assert [response.status_code for response in responses] == [200, 200, 200]
    assert [response.headers["X-RateLimit-Remaining"] for response in responses] == [
        "299",
        "298",
        "297",
    ]
    assert all(response.headers["X-RateLimit-Limit"] == "300" for response in responses)


@pytest.mark.asyncio
async def test_t2_minute_exhaustion_returns_429_with_retry_after() -> None:
    user_id = str(uuid4())
    policy = _policy("user", user_id)
    service = FakeRateLimiterService(
        {
            f"user:{user_id}": _Scenario(
                policy,
                [
                    _evaluation(
                        policy,
                        allowed=False,
                        rem_min=0,
                        rem_hour=9_700,
                        rem_day=99_700,
                        retry_after_ms=2_500,
                    ),
                ],
            )
        }
    )
    app = _build_app(_settings(), service)
    token = _token(app.state.settings.auth.verification_key, user_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/limited", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 429
    assert response.json() == {"error": "rate_limit_exceeded"}
    assert response.headers["Retry-After"] == "3"


@pytest.mark.asyncio
async def test_t3_hour_exhaustion_uses_longer_retry_after() -> None:
    user_id = str(uuid4())
    policy = _policy("user", user_id)
    service = FakeRateLimiterService(
        {
            f"user:{user_id}": _Scenario(
                policy,
                [
                    _evaluation(
                        policy,
                        allowed=False,
                        rem_min=25,
                        rem_hour=0,
                        rem_day=90_000,
                        retry_after_ms=61_000,
                    ),
                ],
            )
        }
    )
    app = _build_app(_settings(), service)
    token = _token(app.state.settings.auth.verification_key, user_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/limited", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 60


@pytest.mark.asyncio
async def test_t4_two_principals_are_isolated() -> None:
    user_a = str(uuid4())
    user_b = str(uuid4())
    policy_a = _policy("user", user_a)
    policy_b = _policy("user", user_b)
    service = FakeRateLimiterService(
        {
            f"user:{user_a}": _Scenario(
                policy_a,
                [
                    _evaluation(
                        policy_a,
                        allowed=False,
                        rem_min=0,
                        rem_hour=0,
                        rem_day=0,
                        retry_after_ms=1_000,
                    )
                ],
            ),
            f"user:{user_b}": _Scenario(
                policy_b,
                [_evaluation(policy_b, allowed=True, rem_min=299, rem_hour=9_999, rem_day=99_999)],
            ),
        }
    )
    app = _build_app(_settings(), service)
    token_a = _token(app.state.settings.auth.verification_key, user_a)
    token_b = _token(app.state.settings.auth.verification_key, user_b)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response_a = await client.get(
            "/api/v1/limited", headers={"Authorization": f"Bearer {token_a}"}
        )
        response_b = await client.get(
            "/api/v1/limited", headers={"Authorization": f"Bearer {token_b}"}
        )

    assert response_a.status_code == 429
    assert response_b.status_code == 200
    assert response_b.headers["X-RateLimit-Remaining"] == "299"


@pytest.mark.asyncio
async def test_t5_tier_change_is_reflected_on_next_request() -> None:
    user_id = str(uuid4())
    default_policy = _policy("user", user_id, tier="default", rpm=300)
    pro_policy = _policy("user", user_id, tier="pro", rpm=1_000, rph=50_000, rpd=500_000)
    service = FakeRateLimiterService(
        {
            f"user:{user_id}": _Scenario(
                default_policy,
                [
                    _evaluation(
                        default_policy, allowed=True, rem_min=299, rem_hour=9_999, rem_day=99_999
                    ),
                    _evaluation(
                        pro_policy, allowed=True, rem_min=999, rem_hour=49_999, rem_day=499_999
                    ),
                ],
            )
        }
    )
    app = _build_app(_settings(), service)
    token = _token(app.state.settings.auth.verification_key, user_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        first = await client.get("/api/v1/limited", headers={"Authorization": f"Bearer {token}"})
        service.scenarios[f"user:{user_id}"].policy = pro_policy
        second = await client.get("/api/v1/limited", headers={"Authorization": f"Bearer {token}"})

    assert first.headers["X-RateLimit-Limit"] == "300"
    assert second.headers["X-RateLimit-Limit"] == "1000"


@pytest.mark.asyncio
async def test_t6_anonymous_docs_use_anon_principal() -> None:
    anon_policy = _policy(
        "anon", "127.0.0.1", tier="anonymous", rpm=60, rph=1_000, rpd=10_000, anonymous=True
    )
    service = FakeRateLimiterService(
        {},
        anonymous=_Scenario(
            anon_policy,
            [
                _evaluation(anon_policy, allowed=True, rem_min=59, rem_hour=999, rem_day=9_999),
            ],
        ),
    )
    app = _build_app(_settings(), service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/docs")

    assert response.status_code == 200
    assert service.calls == [("anon", "127.0.0.1", True)]


@pytest.mark.asyncio
async def test_t7_fail_closed_returns_503() -> None:
    user_id = str(uuid4())
    policy = _policy("user", user_id)
    service = FakeRateLimiterService({f"user:{user_id}": _Scenario(policy, [RedisError("down")])})
    app = _build_app(_settings(fail_open=False), service)
    token = _token(app.state.settings.auth.verification_key, user_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/limited", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 503
    assert response.json() == {"error": "rate_limit_service_unavailable"}
    assert response.headers["Retry-After"] == "30"


@pytest.mark.asyncio
async def test_t8_fail_open_override_passes_request() -> None:
    user_id = str(uuid4())
    policy = _policy("user", user_id)
    service = FakeRateLimiterService({f"user:{user_id}": _Scenario(policy, [RedisError("down")])})
    app = _build_app(_settings(fail_open=True), service)
    token = _token(app.state.settings.auth.verification_key, user_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/limited", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.headers["X-RateLimit-Remaining"] == "unknown"


@pytest.mark.asyncio
async def test_t9_health_path_skips_rate_limiter() -> None:
    service = FakeRateLimiterService({})
    app = _build_app(_settings(), service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert service.calls == []
