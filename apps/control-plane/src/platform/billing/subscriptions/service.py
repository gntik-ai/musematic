from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.audit.service import AuditChainService
from platform.billing.exceptions import (
    ConcurrentLifecycleActionError,
    DowngradeAlreadyScheduledError,
    PlanNotFoundError,
    SubscriptionNotFoundError,
    SubscriptionScopeError,
    UpgradeFailedError,
)
from platform.billing.metrics import metrics
from platform.billing.plans.models import Plan
from platform.billing.plans.repository import PlansRepository
from platform.billing.providers.protocol import PaymentProvider
from platform.billing.subscriptions.models import Subscription
from platform.billing.subscriptions.repository import SubscriptionsRepository
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.tenants.models import Tenant
from platform.workspaces.models import Workspace
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession


class SubscriptionService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        subscriptions: SubscriptionsRepository,
        plans: PlansRepository,
        payment_provider: PaymentProvider | None = None,
        audit_chain: AuditChainService | None = None,
        producer: EventProducer | None = None,
        quota_enforcer: object | None = None,
    ) -> None:
        self.session = session
        self.subscriptions = subscriptions
        self.plans = plans
        self.payment_provider = payment_provider
        self.audit_chain = audit_chain
        self.producer = producer
        self.quota_enforcer = quota_enforcer

    async def provision_for_default_workspace(
        self,
        workspace_id: UUID,
        *,
        plan_slug: str = "free",
        created_by_user_id: UUID | None = None,
    ) -> Subscription:
        workspace = await self.session.get(Workspace, workspace_id)
        if workspace is None:
            raise SubscriptionNotFoundError(workspace_id)
        tenant = await self.session.get(Tenant, workspace.tenant_id)
        if tenant is None or tenant.kind != "default":
            raise SubscriptionScopeError("workspace", tenant.kind if tenant else "missing")
        existing = await self.subscriptions.get_by_scope("workspace", workspace_id)
        if existing is not None:
            return existing
        return await self._provision(
            tenant_id=workspace.tenant_id,
            scope_type="workspace",
            scope_id=workspace_id,
            plan_slug=plan_slug,
            created_by_user_id=created_by_user_id,
        )

    async def provision_for_enterprise_tenant(
        self,
        tenant_id: UUID,
        *,
        created_by_user_id: UUID | None = None,
    ) -> Subscription:
        tenant = await self.session.get(Tenant, tenant_id)
        if tenant is None or tenant.kind != "enterprise":
            raise SubscriptionScopeError("tenant", tenant.kind if tenant else "missing")
        existing = await self.subscriptions.get_by_scope("tenant", tenant_id)
        if existing is not None:
            return existing
        return await self._provision(
            tenant_id=tenant_id,
            scope_type="tenant",
            scope_id=tenant_id,
            plan_slug="enterprise",
            created_by_user_id=created_by_user_id,
        )

    async def upgrade(
        self,
        workspace_id: UUID,
        target_plan_slug: str,
        payment_method_token: str | None,
        *,
        actor_id: UUID | None = None,
    ) -> Subscription:
        workspace = await self.session.get(Workspace, workspace_id)
        if workspace is None:
            raise SubscriptionNotFoundError(workspace_id)
        current = await self.subscriptions.get_by_scope("workspace", workspace_id)
        if current is None:
            raise SubscriptionNotFoundError(workspace_id)
        target_plan = await self.plans.get_by_slug(target_plan_slug)
        if target_plan is None:
            raise PlanNotFoundError(target_plan_slug)
        if not target_plan.is_public or not target_plan.is_active:
            raise PlanNotFoundError(target_plan_slug)
        current_plan = await self.session.get(Plan, current.plan_id)
        if current_plan is None:
            raise PlanNotFoundError(str(current.plan_id))
        if _tier_rank(target_plan.tier) <= _tier_rank(current_plan.tier):
            raise UpgradeFailedError(workspace_id, "target plan is not a higher tier")
        target_version = await self.plans.get_published_version(target_plan.id)
        if target_version is None:
            raise PlanNotFoundError(target_plan_slug)
        from_plan_slug = current_plan.slug
        from_plan_version = current.plan_version
        from_status = current.status
        try:
            provider_sub = None
            payment_method_id = current.payment_method_id
            customer_id = current.stripe_customer_id
            if self.payment_provider is not None:
                customer_id = (
                    current.stripe_customer_id
                    or await self.payment_provider.create_customer(
                        workspace_id,
                        workspace.tenant_id,
                        f"workspace-{workspace_id}@billing.local",
                    )
                )
                if payment_method_token:
                    provider_method_id = await self.payment_provider.attach_payment_method(
                        customer_id,
                        payment_method_token,
                    )
                    payment_method_id = _provider_id_to_uuid(provider_method_id)
                provider_sub = await self.payment_provider.update_subscription(
                    current.stripe_subscription_id or f"stub_sub_{current.id.hex[:24]}",
                    f"{target_plan.slug}:v{target_version.version}",
                    True,
                    str(uuid4()),
                )
            updated = await self.subscriptions.update_plan_pinning(
                current.id,
                plan_id=target_plan.id,
                plan_version=target_version.version,
                current_period_start=(
                    provider_sub.current_period_start if provider_sub is not None else None
                ),
                current_period_end=(
                    provider_sub.current_period_end if provider_sub is not None else None
                ),
                payment_method_id=payment_method_id,
                status="active",
                stripe_customer_id=customer_id,
                stripe_subscription_id=(
                    provider_sub.provider_subscription_id if provider_sub is not None else None
                ),
            )
            assert updated is not None
            await self._append_audit(
                "billing.subscription.upgraded",
                updated,
                {
                    "workspace_id": str(workspace_id),
                    "target_plan_slug": target_plan_slug,
                    "actor_id": str(actor_id) if actor_id else None,
                },
            )
            await self._publish_event(
                updated,
                "billing.subscription.upgraded",
                {
                    "from_plan_slug": from_plan_slug,
                    "from_plan_version": from_plan_version,
                    "to_plan_slug": target_plan.slug,
                    "to_plan_version": target_version.version,
                    "effective_at": datetime.now(UTC).isoformat(),
                    "prorated_charge_eur": Decimal("0.00"),
                },
            )
            invalidate = getattr(self.quota_enforcer, "invalidate_workspace", None)
            if callable(invalidate):
                await invalidate(workspace_id)
            metrics.record_subscription_transition(from_status, updated.status)
            return updated
        except Exception as exc:
            raise UpgradeFailedError(workspace_id, str(exc)) from exc

    async def downgrade_at_period_end(
        self,
        workspace_or_subscription_id: UUID,
        target_plan_slug: str,
    ) -> Subscription:
        subscription = await self._workspace_or_subscription(workspace_or_subscription_id)
        if subscription is None:
            raise SubscriptionNotFoundError(workspace_or_subscription_id)
        if subscription.cancel_at_period_end:
            raise DowngradeAlreadyScheduledError(subscription.id)
        if subscription.status != "active":
            raise ConcurrentLifecycleActionError(subscription.id)
        target_plan = await self.plans.get_by_slug(target_plan_slug)
        if target_plan is None:
            raise PlanNotFoundError(target_plan_slug)
        current_plan = await self.session.get(Plan, subscription.plan_id)
        if current_plan is None:
            raise PlanNotFoundError(str(subscription.plan_id))
        if _tier_rank(target_plan.tier) >= _tier_rank(current_plan.tier):
            raise ConcurrentLifecycleActionError(subscription.id)
        if self.payment_provider is not None:
            await self.payment_provider.cancel_subscription(
                subscription.stripe_subscription_id or f"stub_sub_{subscription.id.hex[:24]}",
                at_period_end=True,
            )
        previous_status = subscription.status
        updated = await self.subscriptions.set_cancel_at_period_end(subscription.id, True)
        assert updated is not None
        metrics.record_subscription_transition(previous_status, updated.status)
        await self._publish_event(
            updated,
            "billing.subscription.downgrade_scheduled",
            {
                "from_plan_slug": current_plan.slug,
                "to_plan_slug": target_plan.slug,
                "scheduled_for": updated.current_period_end.isoformat(),
            },
        )
        await self._append_audit(
            "billing.subscription.downgrade_scheduled",
            updated,
            {
                "subscription_id": str(updated.id),
                "target_plan_slug": target_plan.slug,
                "scheduled_for": updated.current_period_end.isoformat(),
            },
        )
        return updated

    async def cancel_scheduled_downgrade(self, workspace_or_subscription_id: UUID) -> Subscription:
        subscription = await self._workspace_or_subscription(workspace_or_subscription_id)
        if subscription is None:
            raise SubscriptionNotFoundError(workspace_or_subscription_id)
        if subscription.status != "cancellation_pending" or not subscription.cancel_at_period_end:
            raise ConcurrentLifecycleActionError(subscription.id)
        scheduled_for = subscription.current_period_end
        if self.payment_provider is not None:
            current_plan = await self.session.get(Plan, subscription.plan_id)
            await self.payment_provider.update_subscription(
                subscription.stripe_subscription_id or f"stub_sub_{subscription.id.hex[:24]}",
                f"{current_plan.slug if current_plan is not None else 'unknown'}:v"
                f"{subscription.plan_version}",
                False,
                str(uuid4()),
            )
        previous_status = subscription.status
        updated = await self.subscriptions.set_cancel_at_period_end(subscription.id, False)
        assert updated is not None
        metrics.record_subscription_transition(previous_status, updated.status)
        await self._publish_event(
            updated,
            "billing.subscription.downgrade_cancelled",
            {"had_been_scheduled_for": scheduled_for.isoformat()},
        )
        await self._append_audit(
            "billing.subscription.downgrade_cancelled",
            updated,
            {
                "subscription_id": str(updated.id),
                "had_been_scheduled_for": scheduled_for.isoformat(),
            },
        )
        return updated

    async def suspend(self, subscription_id: UUID, reason: str) -> Subscription:
        subscription = await self.subscriptions.get_by_id(subscription_id)
        if subscription is None:
            raise SubscriptionNotFoundError(subscription_id)
        if subscription.status in {"canceled", "suspended"}:
            raise ConcurrentLifecycleActionError(subscription_id)
        previous_status = subscription.status
        updated = await self.subscriptions.update_status(subscription_id, "suspended")
        assert updated is not None
        metrics.record_subscription_transition(previous_status, updated.status)
        await self._publish_event(updated, "billing.subscription.suspended", {"reason": reason})
        await self._append_audit(
            "billing.subscription.suspended",
            updated,
            {"subscription_id": str(updated.id), "reason": reason},
        )
        return updated

    async def reactivate(self, subscription_id: UUID) -> Subscription:
        subscription = await self.subscriptions.get_by_id(subscription_id)
        if subscription is None:
            raise SubscriptionNotFoundError(subscription_id)
        if subscription.status not in {"past_due", "suspended"}:
            raise ConcurrentLifecycleActionError(subscription_id)
        previous_status = subscription.status
        updated = await self.subscriptions.update_status(subscription_id, "active")
        assert updated is not None
        metrics.record_subscription_transition(previous_status, updated.status)
        await self._publish_event(
            updated,
            "billing.subscription.reactivated",
            {"previous_status": previous_status},
        )
        await self._append_audit(
            "billing.subscription.reactivated",
            updated,
            {"subscription_id": str(updated.id), "previous_status": previous_status},
        )
        return updated

    async def cancel(self, subscription_id: UUID) -> Subscription:
        subscription = await self.subscriptions.get_by_id(subscription_id)
        if subscription is None:
            raise SubscriptionNotFoundError(subscription_id)
        if subscription.status == "canceled":
            raise ConcurrentLifecycleActionError(subscription_id)
        if self.payment_provider is not None:
            await self.payment_provider.cancel_subscription(
                subscription.stripe_subscription_id or f"stub_sub_{subscription.id.hex[:24]}",
                at_period_end=False,
            )
        previous_status = subscription.status
        updated = await self.subscriptions.update_status(subscription_id, "canceled")
        assert updated is not None
        metrics.record_subscription_transition(previous_status, updated.status)
        await self._publish_event(
            updated,
            "billing.subscription.canceled",
            {"canceled_at": datetime.now(UTC).isoformat(), "final_invoice_eur": Decimal("0.00")},
        )
        await self._append_audit(
            "billing.subscription.canceled",
            updated,
            {"subscription_id": str(updated.id), "canceled_at": datetime.now(UTC).isoformat()},
        )
        return updated

    async def migrate_version(
        self,
        subscription_id: UUID,
        plan_id: UUID,
        plan_version: int,
    ) -> Subscription:
        subscription = await self.subscriptions.get_by_id(subscription_id)
        if subscription is None:
            raise SubscriptionNotFoundError(subscription_id)
        if subscription.status in {"canceled", "suspended"}:
            raise ConcurrentLifecycleActionError(subscription_id)
        updated = await self.subscriptions.update_plan_pinning(
            subscription_id,
            plan_id=plan_id,
            plan_version=plan_version,
        )
        assert updated is not None
        await self._append_audit(
            "billing.subscription.migrated",
            updated,
            {
                "subscription_id": str(updated.id),
                "plan_id": str(plan_id),
                "plan_version": plan_version,
            },
        )
        return updated

    async def _provision(
        self,
        *,
        tenant_id: UUID,
        scope_type: str,
        scope_id: UUID,
        plan_slug: str,
        created_by_user_id: UUID | None,
    ) -> Subscription:
        plan = await self.plans.get_by_slug(plan_slug)
        if plan is None:
            raise PlanNotFoundError(plan_slug)
        version = await self.plans.get_published_version(plan.id)
        if version is None:
            raise PlanNotFoundError(plan_slug)
        now = datetime.now(UTC)
        period_start, period_end = _period_bounds(now, version.quota_period_anchor)
        status = "trial" if version.trial_days > 0 else "active"
        subscription = await self.subscriptions.create(
            tenant_id=tenant_id,
            scope_type=scope_type,
            scope_id=scope_id,
            plan_id=plan.id,
            plan_version=version.version,
            status=status,
            current_period_start=period_start,
            current_period_end=period_end,
            created_by_user_id=created_by_user_id,
        )
        await self._publish_event(
            subscription,
            "billing.subscription.created",
            {
                "scope_type": scope_type,
                "scope_id": str(scope_id),
                "plan_id": str(plan.id),
                "plan_slug": plan.slug,
                "plan_version": version.version,
                "status": status,
                "started_at": subscription.started_at.isoformat(),
                "current_period_start": period_start.isoformat(),
                "current_period_end": period_end.isoformat(),
                "trial_expires_at": (
                    (now + timedelta(days=version.trial_days)).isoformat()
                    if version.trial_days > 0
                    else None
                ),
            },
        )
        await self._append_audit(
            "billing.subscription.created",
            subscription,
            {
                "subscription_id": str(subscription.id),
                "scope_type": scope_type,
                "scope_id": str(scope_id),
                "plan_slug": plan.slug,
                "plan_version": version.version,
            },
        )
        return subscription

    async def _workspace_or_subscription(self, identifier: UUID) -> Subscription | None:
        workspace_subscription = await self.subscriptions.get_by_scope("workspace", identifier)
        if workspace_subscription is not None:
            return workspace_subscription
        return await self.subscriptions.get_by_id(identifier)

    async def _append_audit(
        self,
        event_type: str,
        subscription: Subscription,
        payload: dict[str, object],
    ) -> None:
        if self.audit_chain is None:
            return
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
        await self.audit_chain.append(
            uuid4(),
            "billing.subscriptions",
            canonical,
            event_type=event_type,
            canonical_payload_json=dict(payload),
            tenant_id=subscription.tenant_id,
        )

    async def _publish_event(
        self,
        subscription: Subscription,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        if self.producer is None:
            return
        workspace_id = subscription.scope_id if subscription.scope_type == "workspace" else None
        await self.producer.publish(
            "billing.lifecycle",
            str(subscription.tenant_id),
            event_type,
            payload,
            CorrelationContext(
                correlation_id=uuid4(),
                tenant_id=subscription.tenant_id,
                workspace_id=workspace_id,
            ),
            "billing.subscriptions",
        )


def _period_bounds(now: datetime, anchor: str) -> tuple[datetime, datetime]:
    if anchor == "calendar_month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = _add_month(start)
        return start, end
    return now, now + timedelta(days=30)


def _add_month(value: datetime) -> datetime:
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    return value.replace(year=year, month=month)


def _provider_id_to_uuid(provider_id: str) -> UUID:
    return UUID(hex=provider_id.encode("utf-8").hex().ljust(32, "0")[:32])


def _tier_rank(tier: str) -> int:
    return {"free": 0, "pro": 1, "enterprise": 2}.get(tier, -1)
