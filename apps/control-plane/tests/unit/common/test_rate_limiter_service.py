from __future__ import annotations

from datetime import UTC, datetime
from platform.common.clients.redis import MultiWindowRateLimitResult
from platform.common.config import PlatformSettings
from platform.common.exceptions import NotFoundError
from platform.common.rate_limiter.models import (
    RateLimitConfig,
    RateLimitPrincipalType,
    SubscriptionTier,
)
from platform.common.rate_limiter.repository import RateLimiterRepository
from platform.common.rate_limiter.schemas import (
    RateLimitConfigResponse,
    RateLimitConfigUpsertRequest,
    SubscriptionTierResponse,
)
from platform.common.rate_limiter.service import RateLimiterService, ResolvedRateLimitPolicy
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError


class FakeRedis:
    def __init__(self) -> None:
        self.cache: dict[tuple[str, str], dict[str, object]] = {}
        self.set_calls: list[tuple[str, str, dict[str, object], int]] = []
        self.rate_limit_calls: list[tuple[str, str, int, int, int]] = []
        self.pttl_value = 0
        self.decision = MultiWindowRateLimitResult(
            allowed=True,
            remaining_minute=9,
            remaining_hour=99,
            remaining_day=999,
            retry_after_ms=0,
        )

    async def cache_get(self, context: str, key: str) -> dict[str, object] | None:
        return self.cache.get((context, key))

    async def cache_set(
        self,
        context: str,
        key: str,
        value: dict[str, object],
        *,
        ttl_seconds: int,
    ) -> None:
        self.cache[(context, key)] = value
        self.set_calls.append((context, key, value, ttl_seconds))

    async def check_multi_window_rate_limit(
        self,
        principal_kind: str,
        principal_key: str,
        requests_per_minute: int,
        requests_per_hour: int,
        requests_per_day: int,
    ) -> MultiWindowRateLimitResult:
        self.rate_limit_calls.append(
            (
                principal_kind,
                principal_key,
                requests_per_minute,
                requests_per_hour,
                requests_per_day,
            )
        )
        return self.decision

    async def pttl(self, key: str) -> int:
        del key
        return self.pttl_value


class FakeRepository:
    def __init__(self, tier: SubscriptionTier | None = None) -> None:
        self.tiers: dict[str, SubscriptionTier] = {}
        if tier is not None:
            self.tiers[tier.name] = tier
        self.configs: dict[tuple[RateLimitPrincipalType, UUID], RateLimitConfig] = {}
        self.tier_lookups: list[str] = []
        self.config_lookups: list[tuple[RateLimitPrincipalType, UUID]] = []

    async def get_tier_by_name(self, name: str) -> SubscriptionTier | None:
        self.tier_lookups.append(name)
        return self.tiers.get(name)

    async def get_rate_limit_config(
        self,
        principal_type: RateLimitPrincipalType,
        principal_id: UUID,
    ) -> RateLimitConfig | None:
        self.config_lookups.append((principal_type, principal_id))
        return self.configs.get((principal_type, principal_id))


class FakeScalarResult:
    def __init__(self, value: object) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object:
        return self.value


class FakeSession:
    def __init__(self, results: list[object] | None = None) -> None:
        self.results = list(results or [])
        self.added: list[object] = []
        self.executed: list[object] = []
        self.flush_count = 0
        self.refreshes: list[tuple[object, list[str] | None]] = []

    async def execute(self, statement: object) -> FakeScalarResult:
        self.executed.append(statement)
        return FakeScalarResult(self.results.pop(0) if self.results else None)

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flush_count += 1

    async def refresh(self, item: object, attribute_names: list[str] | None = None) -> None:
        self.refreshes.append((item, attribute_names))


def _tier(name: str = "default") -> SubscriptionTier:
    now = datetime.now(UTC)
    return SubscriptionTier(
        id=uuid4(),
        name=name,
        requests_per_minute=10,
        requests_per_hour=100,
        requests_per_day=1_000,
        description=f"{name} tier",
        created_at=now,
        updated_at=now,
    )


def _service(
    *,
    repository: FakeRepository | None = None,
    redis_client: FakeRedis | None = None,
) -> tuple[RateLimiterService, FakeRepository, FakeRedis]:
    tier = _tier()
    repo = repository or FakeRepository(tier)
    redis = redis_client or FakeRedis()
    service = RateLimiterService(
        repository=repo,  # type: ignore[arg-type]
        redis_client=redis,  # type: ignore[arg-type]
        settings=PlatformSettings(
            api_governance={
                "default_tier_name": "default",
                "anonymous_tier_name": "anonymous",
                "tier_cache_ttl_seconds": 60,
                "principal_cache_ttl_seconds": 30,
            }
        ),
    )
    return service, repo, redis


@pytest.mark.asyncio
async def test_resolves_anonymous_policy_and_caches_tier_payload() -> None:
    repo = FakeRepository(_tier("anonymous"))
    service, _, redis = _service(repository=repo)

    policy = await service.resolve_anonymous_policy("127.0.0.1")

    assert policy.anonymous is True
    assert policy.principal_kind == "anon"
    assert policy.principal_key == "127.0.0.1"
    assert policy.requests_per_minute == 10
    assert redis.cache[("rate-limit-tier", "anonymous")]["requests_per_day"] == 1_000


@pytest.mark.asyncio
async def test_resolves_principal_policy_from_cache_without_repository_lookup() -> None:
    service, repo, redis = _service()
    redis.cache[("rate-limit-principal-tier", "user:user-1")] = {
        "principal_kind": "user",
        "principal_key": "user-1",
        "tier_name": "cached",
        "requests_per_minute": 5,
        "requests_per_hour": 50,
        "requests_per_day": 500,
        "anonymous": False,
    }

    policy = await service.resolve_policy_for_principal("user", "user-1")

    assert policy == ResolvedRateLimitPolicy("user", "user-1", "cached", 5, 50, 500)
    assert repo.config_lookups == []


@pytest.mark.asyncio
async def test_resolves_principal_policy_with_config_overrides_and_cache_write() -> None:
    principal_id = uuid4()
    tier = _tier("pro")
    repo = FakeRepository(_tier())
    repo.configs[(RateLimitPrincipalType.user, principal_id)] = RateLimitConfig(
        principal_type=RateLimitPrincipalType.user,
        principal_id=principal_id,
        subscription_tier=tier,
        requests_per_minute_override=20,
        requests_per_hour_override=None,
        requests_per_day_override=2_000,
    )
    service, _, redis = _service(repository=repo)

    policy = await service.resolve_policy_for_principal("user", str(principal_id))

    assert policy.tier_name == "pro"
    assert policy.requests_per_minute == 20
    assert policy.requests_per_hour == 100
    assert policy.requests_per_day == 2_000
    assert redis.cache[("rate-limit-principal-tier", f"user:{principal_id}")]["tier_name"] == "pro"


@pytest.mark.asyncio
async def test_resolves_default_policy_for_unknown_or_non_uuid_principals() -> None:
    service, repo, _ = _service()

    policy = await service.resolve_policy_for_principal("unknown", "not-a-uuid", use_cache=False)
    uuid_policy = await service.resolve_policy_for_principal(
        "unknown",
        str(uuid4()),
        use_cache=False,
    )

    assert policy.tier_name == "default"
    assert policy.principal_kind == "unknown"
    assert uuid_policy.tier_name == "default"
    assert repo.config_lookups == []


@pytest.mark.asyncio
async def test_tier_payload_can_be_served_from_cache() -> None:
    service, repo, redis = _service()
    redis.cache[("rate-limit-tier", "default")] = {
        "name": "default",
        "requests_per_minute": 7,
        "requests_per_hour": 70,
        "requests_per_day": 700,
        "description": "cached tier",
    }

    policy = await service.resolve_policy_for_principal("user", "not-a-uuid")

    assert policy.requests_per_minute == 7
    assert repo.tier_lookups == []


@pytest.mark.asyncio
async def test_missing_tier_raises_not_found() -> None:
    service, _, _ = _service(repository=FakeRepository())

    with pytest.raises(NotFoundError):
        await service.resolve_policy_for_principal("user", str(uuid4()), use_cache=False)


@pytest.mark.asyncio
async def test_enforce_policy_uses_redis_decision_and_default_reset_ttl(monkeypatch) -> None:
    service, _, redis = _service()
    monkeypatch.setattr("platform.common.rate_limiter.service.time.time", lambda: 1_000.1)
    policy = ResolvedRateLimitPolicy("user", "user-1", "default", 10, 100, 1_000)

    evaluation = await service.enforce_policy(policy)

    assert evaluation.decision is redis.decision
    assert evaluation.reset_epoch_seconds == 1_061
    assert redis.rate_limit_calls == [("user", "user-1", 10, 100, 1_000)]


@pytest.mark.asyncio
async def test_enforce_policy_uses_existing_minute_ttl(monkeypatch) -> None:
    service, _, redis = _service()
    redis.pttl_value = 1_234
    monkeypatch.setattr("platform.common.rate_limiter.service.time.time", lambda: 2_000.0)
    policy = ResolvedRateLimitPolicy("user", "user-2", "default", 10, 100, 1_000)

    evaluation = await service.enforce_policy(policy)

    assert evaluation.reset_epoch_seconds == 2_002


def test_rate_limit_schemas_validate_requests_and_serialize_from_models() -> None:
    principal_id = uuid4()
    tier = _tier("enterprise")
    config = RateLimitConfig(
        id=uuid4(),
        principal_type=RateLimitPrincipalType.service_account,
        principal_id=principal_id,
        subscription_tier_id=tier.id,
        subscription_tier=tier,
        requests_per_minute_override=None,
        requests_per_hour_override=500,
        requests_per_day_override=None,
        created_at=tier.created_at,
        updated_at=tier.updated_at,
    )

    request = RateLimitConfigUpsertRequest(
        principal_type="service_account",
        principal_id=principal_id,
        subscription_tier_name="enterprise",
        requests_per_minute_override=1,
    )
    tier_response = SubscriptionTierResponse.model_validate(tier)
    config_response = RateLimitConfigResponse.model_validate(config)

    assert request.principal_type is RateLimitPrincipalType.service_account
    assert tier_response.name == "enterprise"
    assert config_response.subscription_tier.requests_per_hour == 100
    with pytest.raises(PydanticValidationError):
        RateLimitConfigUpsertRequest(
            principal_type="user",
            principal_id=principal_id,
            subscription_tier_name="",
            requests_per_minute_override=0,
        )


@pytest.mark.asyncio
async def test_repository_queries_and_upsert_paths() -> None:
    principal_id = uuid4()
    tier = _tier("repo")
    existing = RateLimitConfig(
        principal_type=RateLimitPrincipalType.user,
        principal_id=principal_id,
        subscription_tier=tier,
        requests_per_minute_override=None,
        requests_per_hour_override=None,
        requests_per_day_override=None,
    )
    session = FakeSession(results=[tier, existing, None, existing])
    repository = RateLimiterRepository(session)  # type: ignore[arg-type]

    assert await repository.get_tier_by_name("repo") is tier
    assert (
        await repository.get_rate_limit_config(RateLimitPrincipalType.user, principal_id)
        is existing
    )
    created = await repository.upsert_rate_limit_config(
        principal_type=RateLimitPrincipalType.user,
        principal_id=uuid4(),
        subscription_tier=tier,
        requests_per_minute_override=1,
        requests_per_hour_override=2,
        requests_per_day_override=3,
    )
    updated = await repository.upsert_rate_limit_config(
        principal_type=RateLimitPrincipalType.user,
        principal_id=principal_id,
        subscription_tier=tier,
        requests_per_minute_override=4,
        requests_per_hour_override=5,
        requests_per_day_override=6,
    )

    assert created in session.added
    assert updated.requests_per_minute_override == 4
    assert session.flush_count == 2
    assert session.refreshes[-1] == (existing, ["subscription_tier"])
