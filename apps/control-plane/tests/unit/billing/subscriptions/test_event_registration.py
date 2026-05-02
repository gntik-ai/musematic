from __future__ import annotations

from platform.billing.subscriptions.events import register_billing_event_types
from platform.common.events.registry import event_registry


def test_billing_event_types_are_registered() -> None:
    register_billing_event_types()

    for event_type in {
        "billing.plan.published",
        "billing.plan.deprecated",
        "billing.subscription.created",
        "billing.subscription.upgraded",
        "billing.subscription.downgrade_scheduled",
        "billing.subscription.downgrade_cancelled",
        "billing.subscription.downgrade_effective",
        "billing.subscription.suspended",
        "billing.subscription.reactivated",
        "billing.subscription.canceled",
        "billing.subscription.period_renewed",
        "billing.overage.authorized",
        "billing.overage.revoked",
        "billing.overage.cap_reached",
    }:
        assert event_registry.is_registered(event_type)
