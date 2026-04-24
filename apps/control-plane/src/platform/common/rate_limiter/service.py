from __future__ import annotations

import math
import time
from dataclasses import dataclass
from platform.common.clients.redis import AsyncRedisClient, MultiWindowRateLimitResult
from platform.common.config import PlatformSettings
from platform.common.exceptions import NotFoundError
from platform.common.rate_limiter.models import RateLimitPrincipalType
from platform.common.rate_limiter.repository import RateLimiterRepository
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class ResolvedRateLimitPolicy:
    principal_kind: str
    principal_key: str
    tier_name: str
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    anonymous: bool = False


@dataclass(slots=True)
class RateLimitEvaluation:
    policy: ResolvedRateLimitPolicy
    decision: MultiWindowRateLimitResult
    reset_epoch_seconds: int


class RateLimiterService:
    def __init__(
        self,
        *,
        repository: RateLimiterRepository,
        redis_client: AsyncRedisClient,
        settings: PlatformSettings,
    ) -> None:
        self.repository = repository
        self.redis_client = redis_client
        self.settings = settings

    async def resolve_anonymous_policy(
        self, source_ip: str, *, use_cache: bool = True
    ) -> ResolvedRateLimitPolicy:
        tier_name = self.settings.api_governance.anonymous_tier_name
        tier_payload = await self._get_tier_payload(tier_name, use_cache=use_cache)
        return ResolvedRateLimitPolicy(
            principal_kind="anon",
            principal_key=source_ip,
            tier_name=tier_name,
            requests_per_minute=int(tier_payload["requests_per_minute"]),
            requests_per_hour=int(tier_payload["requests_per_hour"]),
            requests_per_day=int(tier_payload["requests_per_day"]),
            anonymous=True,
        )

    async def resolve_policy_for_principal(
        self,
        principal_type: str,
        principal_id: str,
        *,
        use_cache: bool = True,
    ) -> ResolvedRateLimitPolicy:
        cache_key = f"{principal_type}:{principal_id}"
        if use_cache:
            cached = await self.redis_client.cache_get("rate-limit-principal-tier", cache_key)
            if cached is not None:
                return self._payload_to_policy(cached)

        policy = await self._lookup_policy(principal_type, principal_id, use_cache=use_cache)
        if use_cache:
            await self.redis_client.cache_set(
                "rate-limit-principal-tier",
                cache_key,
                self._policy_payload(policy),
                ttl_seconds=self.settings.api_governance.principal_cache_ttl_seconds,
            )
        return policy

    async def enforce_policy(self, policy: ResolvedRateLimitPolicy) -> RateLimitEvaluation:
        decision = await self.redis_client.check_multi_window_rate_limit(
            policy.principal_kind,
            policy.principal_key,
            policy.requests_per_minute,
            policy.requests_per_hour,
            policy.requests_per_day,
        )
        minute_key = self._minute_bucket_key(policy)
        ttl_ms = await self.redis_client.pttl(minute_key)
        if ttl_ms <= 0:
            ttl_ms = 60_000
        reset_epoch_seconds = math.ceil(time.time() + (ttl_ms / 1000))
        return RateLimitEvaluation(
            policy=policy,
            decision=decision,
            reset_epoch_seconds=reset_epoch_seconds,
        )

    async def _lookup_policy(
        self,
        principal_type: str,
        principal_id: str,
        *,
        use_cache: bool,
    ) -> ResolvedRateLimitPolicy:
        tier_name = self.settings.api_governance.default_tier_name
        tier_payload = await self._get_tier_payload(tier_name, use_cache=use_cache)
        parsed_principal = self._parse_uuid(principal_id)
        config = None
        if parsed_principal is not None:
            try:
                normalized_principal_type = RateLimitPrincipalType(principal_type)
            except ValueError:
                normalized_principal_type = None
            if normalized_principal_type is not None:
                config = await self.repository.get_rate_limit_config(
                    normalized_principal_type,
                    parsed_principal,
                )
        if config is None:
            return ResolvedRateLimitPolicy(
                principal_kind=principal_type,
                principal_key=principal_id,
                tier_name=tier_name,
                requests_per_minute=int(tier_payload["requests_per_minute"]),
                requests_per_hour=int(tier_payload["requests_per_hour"]),
                requests_per_day=int(tier_payload["requests_per_day"]),
            )

        tier = config.subscription_tier
        return ResolvedRateLimitPolicy(
            principal_kind=principal_type,
            principal_key=principal_id,
            tier_name=tier.name,
            requests_per_minute=config.requests_per_minute_override or tier.requests_per_minute,
            requests_per_hour=config.requests_per_hour_override or tier.requests_per_hour,
            requests_per_day=config.requests_per_day_override or tier.requests_per_day,
        )

    async def _get_tier_payload(self, tier_name: str, *, use_cache: bool) -> dict[str, Any]:
        if use_cache:
            cached = await self.redis_client.cache_get("rate-limit-tier", tier_name)
            if cached is not None:
                return cached
        tier = await self.repository.get_tier_by_name(tier_name)
        if tier is None:
            raise NotFoundError(
                "RATE_LIMIT_TIER_NOT_FOUND", f"Unknown subscription tier: {tier_name}"
            )
        payload = {
            "name": tier.name,
            "requests_per_minute": tier.requests_per_minute,
            "requests_per_hour": tier.requests_per_hour,
            "requests_per_day": tier.requests_per_day,
            "description": tier.description,
        }
        if use_cache:
            await self.redis_client.cache_set(
                "rate-limit-tier",
                tier_name,
                payload,
                ttl_seconds=self.settings.api_governance.tier_cache_ttl_seconds,
            )
        return payload

    @staticmethod
    def _parse_uuid(raw_value: str) -> UUID | None:
        try:
            return UUID(str(raw_value))
        except ValueError:
            return None

    @staticmethod
    def _policy_payload(policy: ResolvedRateLimitPolicy) -> dict[str, Any]:
        return {
            "principal_kind": policy.principal_kind,
            "principal_key": policy.principal_key,
            "tier_name": policy.tier_name,
            "requests_per_minute": policy.requests_per_minute,
            "requests_per_hour": policy.requests_per_hour,
            "requests_per_day": policy.requests_per_day,
            "anonymous": policy.anonymous,
        }

    @staticmethod
    def _payload_to_policy(payload: dict[str, Any]) -> ResolvedRateLimitPolicy:
        return ResolvedRateLimitPolicy(
            principal_kind=str(payload["principal_kind"]),
            principal_key=str(payload["principal_key"]),
            tier_name=str(payload["tier_name"]),
            requests_per_minute=int(payload["requests_per_minute"]),
            requests_per_hour=int(payload["requests_per_hour"]),
            requests_per_day=int(payload["requests_per_day"]),
            anonymous=bool(payload.get("anonymous", False)),
        )

    @staticmethod
    def _minute_bucket_key(policy: ResolvedRateLimitPolicy) -> str:
        return AsyncRedisClient._multi_window_rate_limit_keys(
            policy.principal_kind,
            policy.principal_key,
        )[0]
