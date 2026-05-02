from __future__ import annotations

from datetime import datetime
from platform.common.exceptions import NotFoundError, PlatformError, ValidationError
from uuid import UUID


class BillingError(PlatformError):
    status_code = 400


class PlanNotFoundError(NotFoundError):
    def __init__(self, identifier: UUID | str) -> None:
        super().__init__(
            "BILLING_PLAN_NOT_FOUND",
            "Billing plan not found",
            {"plan": str(identifier)},
        )


class PlanVersionImmutableError(BillingError):
    status_code = 409

    def __init__(self, plan_id: UUID | str, version: int) -> None:
        super().__init__(
            "BILLING_PLAN_VERSION_IMMUTABLE",
            "Published plan versions are immutable",
            {"plan_id": str(plan_id), "version": version},
        )


class PlanVersionInProgressError(BillingError):
    status_code = 409

    def __init__(self, plan_id: UUID | str) -> None:
        super().__init__(
            "BILLING_PLAN_VERSION_IN_PROGRESS",
            "A plan-version publish is already in progress",
            {"plan_id": str(plan_id)},
        )


class SubscriptionScopeError(ValidationError):
    def __init__(self, scope_type: str, tenant_kind: str) -> None:
        super().__init__(
            "BILLING_SUBSCRIPTION_SCOPE_INVALID",
            "Subscription scope is not valid for the tenant kind",
            {"scope_type": scope_type, "tenant_kind": tenant_kind},
        )


class SubscriptionNotFoundError(NotFoundError):
    def __init__(self, identifier: UUID | str) -> None:
        super().__init__(
            "BILLING_SUBSCRIPTION_NOT_FOUND",
            "Billing subscription not found",
            {"subscription": str(identifier)},
        )


class NoActiveSubscriptionError(BillingError):
    status_code = 403

    def __init__(self, workspace_id: UUID | str) -> None:
        super().__init__(
            "BILLING_NO_ACTIVE_SUBSCRIPTION",
            "Workspace has no active subscription",
            {"workspace_id": str(workspace_id)},
        )


class SubscriptionSuspendedError(BillingError):
    status_code = 403

    def __init__(self, workspace_id: UUID | str) -> None:
        super().__init__(
            "BILLING_SUBSCRIPTION_SUSPENDED",
            "The active subscription is suspended",
            {"workspace_id": str(workspace_id)},
        )


class QuotaExceededError(BillingError):
    status_code = 402

    def __init__(
        self,
        quota_name: str,
        current: int | float,
        limit: int | float,
        *,
        reset_at: datetime | str | None = None,
        plan_slug: str | None = None,
        upgrade_url: str | None = None,
        overage_available: bool = False,
    ) -> None:
        details = {
            "quota_name": quota_name,
            "current": current,
            "limit": limit,
            "reset_at": reset_at.isoformat() if isinstance(reset_at, datetime) else reset_at,
            "plan_slug": plan_slug,
            "upgrade_url": upgrade_url,
            "overage_available": overage_available,
        }
        super().__init__(
            "BILLING_QUOTA_EXCEEDED",
            "Quota has been exceeded",
            details,
        )


class OverageRequiredError(BillingError):
    status_code = 202

    def __init__(self, workspace_id: UUID | str, quota_name: str) -> None:
        super().__init__(
            "BILLING_OVERAGE_REQUIRED",
            "Overage authorization is required before work can continue",
            {"workspace_id": str(workspace_id), "quota_name": quota_name},
        )


class OverageCapExceededError(BillingError):
    status_code = 402

    def __init__(
        self,
        workspace_id: UUID | str,
        cap_eur: str,
        *,
        quota_name: str | None = None,
        reset_at: datetime | str | None = None,
        plan_slug: str | None = None,
        upgrade_url: str | None = None,
    ) -> None:
        super().__init__(
            "BILLING_OVERAGE_CAP_EXCEEDED",
            "Authorized overage cap has been exceeded",
            {
                "workspace_id": str(workspace_id),
                "cap_eur": cap_eur,
                "quota_name": quota_name,
                "reset_at": reset_at.isoformat() if isinstance(reset_at, datetime) else reset_at,
                "plan_slug": plan_slug,
                "upgrade_url": upgrade_url,
            },
        )


class ModelTierNotAllowedError(BillingError):
    status_code = 402

    def __init__(
        self,
        workspace_id: UUID | str,
        model_id: str,
        allowed_model_tier: str,
        *,
        quota_name: str = "allowed_model_tier",
        reset_at: datetime | str | None = None,
        plan_slug: str | None = None,
        upgrade_url: str | None = None,
    ) -> None:
        super().__init__(
            "BILLING_MODEL_TIER_NOT_ALLOWED",
            "Requested model tier is not allowed by the active subscription",
            {
                "workspace_id": str(workspace_id),
                "model_id": model_id,
                "allowed_model_tier": allowed_model_tier,
                "quota_name": quota_name,
                "reset_at": reset_at.isoformat() if isinstance(reset_at, datetime) else reset_at,
                "plan_slug": plan_slug,
                "upgrade_url": upgrade_url,
            },
        )


class PaymentProviderError(BillingError):
    status_code = 502

    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(
            "BILLING_PAYMENT_PROVIDER_ERROR",
            "Payment provider operation failed",
            {"provider": provider, "reason": reason},
        )


class UpgradeFailedError(BillingError):
    status_code = 409

    def __init__(self, workspace_id: UUID | str, reason: str) -> None:
        super().__init__(
            "BILLING_UPGRADE_FAILED",
            "Subscription upgrade failed",
            {"workspace_id": str(workspace_id), "reason": reason},
        )


class DowngradeAlreadyScheduledError(BillingError):
    status_code = 409

    def __init__(self, subscription_id: UUID | str) -> None:
        super().__init__(
            "BILLING_DOWNGRADE_ALREADY_SCHEDULED",
            "A downgrade is already scheduled for this subscription",
            {"subscription_id": str(subscription_id)},
        )


class ConcurrentLifecycleActionError(BillingError):
    status_code = 409

    def __init__(self, subscription_id: UUID | str) -> None:
        super().__init__(
            "BILLING_CONCURRENT_LIFECYCLE_ACTION",
            "Another subscription lifecycle action is already in progress",
            {"subscription_id": str(subscription_id)},
        )
