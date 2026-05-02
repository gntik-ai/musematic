from __future__ import annotations

import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from decimal import Decimal
from platform.billing.exceptions import NoActiveSubscriptionError
from platform.billing.metrics import metrics
from platform.billing.plans.models import Plan, PlanVersion
from platform.billing.quotas.schemas import QuotaCheckResult, QuotaDecision
from platform.billing.quotas.usage_repository import UsageRepository
from platform.billing.subscriptions.models import Subscription
from platform.billing.subscriptions.resolver import SubscriptionResolver
from platform.common.config import PlatformSettings
from platform.model_catalog.models import ModelCatalogEntry
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class _PlanContext:
    subscription: Subscription
    plan: Plan
    version: PlanVersion


class _TTLCache:
    def __init__(self, *, maxsize: int, ttl_seconds: int) -> None:
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        item = self._items.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at <= time.monotonic():
            self._items.pop(key, None)
            return None
        self._items.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        self._items[key] = (time.monotonic() + self.ttl_seconds, value)
        self._items.move_to_end(key)
        while len(self._items) > self.maxsize:
            self._items.popitem(last=False)

    def delete_prefix(self, prefix: str) -> None:
        for key in list(self._items):
            if key.startswith(prefix):
                self._items.pop(key, None)


class QuotaEnforcer:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: PlatformSettings,
        resolver: SubscriptionResolver | None = None,
        usage_repository: UsageRepository | None = None,
        redis_client: Any | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.resolver = resolver or SubscriptionResolver(session)
        self.usage = usage_repository or UsageRepository(session, redis_client)
        self.redis_client = redis_client
        self.local_cache = _TTLCache(
            maxsize=4096,
            ttl_seconds=settings.BILLING_QUOTA_CACHE_TTL_SECONDS,
        )

    async def check_execution(
        self,
        workspace_id: UUID,
        projected_minutes: float | Decimal = Decimal("1.0"),
    ) -> QuotaCheckResult:
        started = time.perf_counter()

        def finish(result: QuotaCheckResult, plan_tier: str = "unknown") -> QuotaCheckResult:
            metrics.record_quota_check(
                result=result.decision,
                plan_tier=plan_tier,
                seconds=time.perf_counter() - started,
            )
            return result

        context = await self._plan_context(workspace_id)
        if context is None:
            return finish(_result("NO_ACTIVE_SUBSCRIPTION", workspace_id=workspace_id))
        if context.subscription.status == "suspended":
            return finish(
                _result("SUSPENDED", workspace_id=workspace_id, plan=context.plan),
                context.plan.tier,
            )
        if _is_unlimited(context.version):
            return finish(_result("OK", plan=context.plan), context.plan.tier)
        usage = await self._usage(context.subscription, workspace_id)
        executions = usage["executions"] + Decimal("1")
        minutes = usage["minutes"] + Decimal(str(projected_minutes))
        execution_failure = _limit_failure(
            "executions_per_month",
            executions,
            Decimal(context.version.executions_per_month),
        )
        minute_failure = _limit_failure(
            "minutes_per_month",
            minutes,
            Decimal(context.version.minutes_per_month),
        )
        failure = execution_failure or minute_failure
        if failure is None:
            return finish(_result("OK", plan=context.plan), context.plan.tier)
        quota_name, current, limit = failure
        if context.version.overage_price_per_minute > ZERO:
            authorized, max_overage_eur = await self._overage_authorization(
                context.subscription,
                workspace_id,
            )
            if authorized:
                if max_overage_eur is not None:
                    projected_overage_eur = await self._projected_overage_eur(
                        context.subscription,
                        current,
                        limit,
                        Decimal(context.version.overage_price_per_minute),
                    )
                    if projected_overage_eur > max_overage_eur:
                        return finish(
                            _result(
                                "OVERAGE_CAP_EXCEEDED",
                                quota_name=quota_name,
                                current=projected_overage_eur,
                                limit=max_overage_eur,
                                subscription=context.subscription,
                                plan=context.plan,
                                overage_available=True,
                            ),
                            context.plan.tier,
                        )
                return finish(_result("OVERAGE_AUTHORIZED", plan=context.plan), context.plan.tier)
            return finish(
                _result(
                    "OVERAGE_REQUIRED",
                    quota_name=quota_name,
                    current=current,
                    limit=limit,
                    subscription=context.subscription,
                    plan=context.plan,
                    overage_available=True,
                ),
                context.plan.tier,
            )
        return finish(
            _result(
                "HARD_CAP_EXCEEDED",
                quota_name=quota_name,
                current=current,
                limit=limit,
                subscription=context.subscription,
                plan=context.plan,
            ),
            context.plan.tier,
        )

    async def check_workspace_create(self, user_id: UUID) -> QuotaCheckResult:
        context = await self._context_for_user(user_id)
        if context is None or _is_unlimited(context.version):
            return _result("OK", plan=context.plan if context else None)
        count = await self.session.scalar(
            text(
                """
                SELECT count(*)
                  FROM workspaces_workspaces
                 WHERE owner_id = :user_id
                   AND status != 'deleted'
                """
            ),
            {"user_id": str(user_id)},
        )
        projected = Decimal(int(count or 0) + 1)
        limit = Decimal(context.version.max_workspaces)
        failure = _limit_failure("max_workspaces", projected, limit)
        if failure is None:
            return _result("OK", plan=context.plan)
        quota_name, current, cap = failure
        return _result(
            "HARD_CAP_EXCEEDED",
            quota_name=quota_name,
            current=current,
            limit=cap,
            subscription=context.subscription,
            plan=context.plan,
        )

    async def check_agent_publish(self, workspace_id: UUID) -> QuotaCheckResult:
        context = await self._plan_context(workspace_id)
        if context is None:
            return _result("NO_ACTIVE_SUBSCRIPTION", workspace_id=workspace_id)
        if _is_unlimited(context.version):
            return _result("OK", plan=context.plan)
        count = await self.session.scalar(
            text(
                """
                SELECT count(*)
                  FROM registry_agent_profiles
                 WHERE workspace_id = :workspace_id
                   AND status = 'published'
                """
            ),
            {"workspace_id": str(workspace_id)},
        )
        projected = Decimal(int(count or 0) + 1)
        limit = Decimal(context.version.max_agents_per_workspace)
        failure = _limit_failure("max_agents_per_workspace", projected, limit)
        if failure is None:
            return _result("OK", plan=context.plan)
        quota_name, current, cap = failure
        return _result(
            "HARD_CAP_EXCEEDED",
            quota_name=quota_name,
            current=current,
            limit=cap,
            subscription=context.subscription,
            plan=context.plan,
        )

    async def check_user_invite(self, workspace_id: UUID) -> QuotaCheckResult:
        context = await self._plan_context(workspace_id)
        if context is None:
            return _result("NO_ACTIVE_SUBSCRIPTION", workspace_id=workspace_id)
        if _is_unlimited(context.version):
            return _result("OK", plan=context.plan)
        count = await self.session.scalar(
            text(
                """
                SELECT count(*)
                  FROM workspaces_memberships
                 WHERE workspace_id = :workspace_id
                """
            ),
            {"workspace_id": str(workspace_id)},
        )
        projected = Decimal(int(count or 0) + 1)
        limit = Decimal(context.version.max_users_per_workspace)
        failure = _limit_failure("max_users_per_workspace", projected, limit)
        if failure is None:
            return _result("OK", plan=context.plan)
        quota_name, current, cap = failure
        return _result(
            "HARD_CAP_EXCEEDED",
            quota_name=quota_name,
            current=current,
            limit=cap,
            subscription=context.subscription,
            plan=context.plan,
        )

    async def check_model_tier(
        self,
        workspace_id: UUID,
        model_id: str,
        model_tier: str | None = None,
    ) -> QuotaCheckResult:
        context = await self._plan_context(workspace_id)
        if context is None:
            return _result("NO_ACTIVE_SUBSCRIPTION", workspace_id=workspace_id)
        if context.plan.allowed_model_tier == "all":
            return _result("OK", plan=context.plan)
        resolved_tier = model_tier or await self._model_quality_tier(model_id)
        allowed = _model_allowed(context.plan.allowed_model_tier, resolved_tier)
        if allowed:
            return _result("OK", plan=context.plan)
        return _result(
            "MODEL_TIER_NOT_ALLOWED",
            quota_name="allowed_model_tier",
            current=Decimal("1"),
            limit=Decimal("0"),
            subscription=context.subscription,
            plan=context.plan,
            message=f"Model {model_id} is not allowed by the active plan.",
        )

    async def invalidate_workspace(self, workspace_id: UUID) -> None:
        self.local_cache.delete_prefix(f"{workspace_id}:")
        if self.redis_client is not None:
            delete = getattr(self.redis_client, "delete", None)
            if callable(delete):
                await delete(f"quota:plan_version:{workspace_id}")

    async def _plan_context(self, workspace_id: UUID) -> _PlanContext | None:
        cache_key = f"{workspace_id}:plan_context"
        cached = self.local_cache.get(cache_key)
        if isinstance(cached, _PlanContext):
            return cached
        try:
            subscription = await self.resolver.resolve_active_subscription(workspace_id)
        except NoActiveSubscriptionError:
            return None
        result = await self.session.execute(
            select(Plan, PlanVersion)
            .join(PlanVersion, PlanVersion.plan_id == Plan.id)
            .where(
                Plan.id == subscription.plan_id,
                PlanVersion.plan_id == subscription.plan_id,
                PlanVersion.version == subscription.plan_version,
            )
            .limit(1)
        )
        row = result.one_or_none()
        if row is None:
            return None
        context = _PlanContext(subscription=subscription, plan=row[0], version=row[1])
        self.local_cache.set(cache_key, context)
        return context

    async def _context_for_user(self, user_id: UUID) -> _PlanContext | None:
        workspace_id = await self.session.scalar(
            text(
                """
                SELECT id
                  FROM workspaces_workspaces
                 WHERE owner_id = :user_id
                   AND status != 'deleted'
                 ORDER BY created_at ASC
                 LIMIT 1
                """
            ),
            {"user_id": str(user_id)},
        )
        if workspace_id is None:
            return None
        return await self._plan_context(UUID(str(workspace_id)))

    async def _usage(self, subscription: Subscription, workspace_id: UUID) -> dict[str, Decimal]:
        cache_key = (
            f"{workspace_id}:{subscription.id}:"
            f"{subscription.current_period_start.isoformat()}"
        )
        cached = self.local_cache.get(cache_key)
        if isinstance(cached, dict):
            return {
                "executions": Decimal(cached["executions"]),
                "minutes": Decimal(cached["minutes"]),
            }
        redis_usage = await self._redis_usage(subscription)
        if redis_usage is not None:
            self.local_cache.set(cache_key, redis_usage)
            return redis_usage
        usage = await self.usage.get_current_usage(
            subscription.id,
            subscription.current_period_start,
        )
        self.local_cache.set(cache_key, usage)
        await self._set_redis_usage(subscription, usage)
        return usage

    async def _redis_usage(self, subscription: Subscription) -> dict[str, Decimal] | None:
        if self.redis_client is None:
            return None
        get = getattr(self.redis_client, "get", None)
        if not callable(get):
            return None
        value = await get(_usage_key(subscription))
        if value is None:
            return None
        raw = value.decode() if isinstance(value, bytes) else str(value)
        payload = json.loads(raw)
        return {
            "executions": Decimal(str(payload.get("executions", "0"))),
            "minutes": Decimal(str(payload.get("minutes", "0"))),
        }

    async def _set_redis_usage(self, subscription: Subscription, usage: dict[str, Decimal]) -> None:
        if self.redis_client is None:
            return
        set_value = getattr(self.redis_client, "set", None)
        if not callable(set_value):
            return
        await set_value(
            _usage_key(subscription),
            json.dumps({key: str(value) for key, value in usage.items()}).encode(),
            ttl=self.settings.BILLING_QUOTA_CACHE_TTL_SECONDS,
        )

    async def _overage_authorization(
        self,
        subscription: Subscription,
        workspace_id: UUID,
    ) -> tuple[bool, Decimal | None]:
        result = await self.session.execute(
            text(
                """
                SELECT max_overage_eur
                  FROM overage_authorizations
                 WHERE workspace_id = :workspace_id
                   AND subscription_id = :subscription_id
                   AND billing_period_start = :period_start
                   AND revoked_at IS NULL
                 LIMIT 1
                """
            ),
            {
                "workspace_id": str(workspace_id),
                "subscription_id": str(subscription.id),
                "period_start": subscription.current_period_start,
            },
        )
        row = result.one_or_none()
        if row is None:
            return False, None
        value = row[0]
        return True, None if value is None else Decimal(value)

    async def _projected_overage_eur(
        self,
        subscription: Subscription,
        projected: Decimal,
        included_limit: Decimal,
        overage_price_per_minute: Decimal,
    ) -> Decimal:
        existing = await self.session.scalar(
            text(
                """
                SELECT coalesce(sum(quantity), 0)
                  FROM usage_records
                 WHERE subscription_id = :subscription_id
                   AND period_start = :period_start
                   AND metric = 'minutes'
                   AND is_overage = true
                """
            ),
            {
                "subscription_id": str(subscription.id),
                "period_start": subscription.current_period_start,
            },
        )
        projected_overage_minutes = max(projected - included_limit, ZERO)
        return (Decimal(existing or 0) + projected_overage_minutes) * overage_price_per_minute

    async def _model_quality_tier(self, model_id: str) -> str:
        if ":" in model_id:
            provider, provider_model = model_id.split(":", 1)
            result = await self.session.execute(
                select(ModelCatalogEntry.quality_tier).where(
                    ModelCatalogEntry.provider == provider,
                    ModelCatalogEntry.model_id == provider_model,
                )
            )
        else:
            result = await self.session.execute(
                select(ModelCatalogEntry.quality_tier).where(
                    ModelCatalogEntry.model_id == model_id,
                )
            )
        return str(result.scalar_one_or_none() or "tier1")


def _usage_key(subscription: Subscription) -> str:
    return f"quota:usage:{subscription.id}:{subscription.current_period_start.isoformat()}"


def _is_unlimited(version: PlanVersion) -> bool:
    return all(
        getattr(version, field) == 0
        for field in (
            "executions_per_day",
            "executions_per_month",
            "minutes_per_day",
            "minutes_per_month",
            "max_workspaces",
            "max_agents_per_workspace",
            "max_users_per_workspace",
        )
    )


def _limit_failure(
    quota_name: str,
    projected: Decimal,
    limit: Decimal,
) -> tuple[str, Decimal, Decimal] | None:
    if limit == 0 or projected <= limit:
        return None
    return quota_name, projected, limit


def _model_allowed(allowed_model_tier: str, quality_tier: str) -> bool:
    if allowed_model_tier == "all":
        return True
    if allowed_model_tier == "standard":
        return quality_tier in {"tier2", "tier3"}
    return quality_tier == "tier3"


def _result(
    decision: QuotaDecision,
    *,
    quota_name: str | None = None,
    current: Decimal | int | None = None,
    limit: Decimal | int | None = None,
    subscription: Subscription | None = None,
    plan: Plan | None = None,
    workspace_id: UUID | None = None,
    overage_available: bool = False,
    message: str | None = None,
) -> QuotaCheckResult:
    resolved_workspace_id = workspace_id or (
        subscription.scope_id if subscription and subscription.scope_type == "workspace" else None
    )
    return QuotaCheckResult(
        decision=decision,
        quota_name=quota_name,
        current=current,
        limit=limit,
        reset_at=subscription.current_period_end if subscription else None,
        plan_slug=plan.slug if plan else None,
        upgrade_url=(
            f"/workspaces/{resolved_workspace_id}/billing/upgrade"
            if resolved_workspace_id is not None
            else None
        ),
        overage_available=overage_available,
        message=message,
    )
