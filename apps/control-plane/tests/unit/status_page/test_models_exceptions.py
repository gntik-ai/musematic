from __future__ import annotations

from platform.status_page import models
from platform.status_page.exceptions import (
    ConfirmationTokenExpiredError,
    ConfirmationTokenInvalidError,
    RateLimitExceededError,
    StatusPageError,
    SubscriptionAlreadyConfirmedError,
    SubscriptionNotFoundError,
    WebhookVerificationFailedError,
)


def test_status_page_models_export_expected_metadata() -> None:
    assert models.PlatformOverallState.operational.value == "operational"
    assert models.PlatformStatusSourceKind.manual.value == "manual"
    assert models.StatusSubscriptionChannel.webhook.value == "webhook"
    assert models.StatusSubscriptionHealth.pending.value == "pending"
    assert models.SubscriptionDispatchOutcome.dead_lettered.value == "dead_lettered"
    assert models.STATUS_SUBSCRIPTION_PENDING == "pending"
    assert "incident.created" in models.STATUS_EVENT_KINDS
    assert models._values(("alpha", "beta")) == "'alpha','beta'"
    assert "'operational'" in models._values(models.PlatformOverallState)
    assert models.PlatformStatusSnapshot.__tablename__ == "platform_status_snapshots"
    assert models.StatusSubscription.__tablename__ == "status_subscriptions"
    assert models.SubscriptionDispatch.__tablename__ == "subscription_dispatches"


def test_status_page_exceptions_preserve_codes_status_and_details() -> None:
    base = StatusPageError(
        "status.test",
        "Status test",
        {"field": "value"},
        status_code=418,
    )
    assert base.code == "status.test"
    assert base.details == {"field": "value"}
    assert base.status_code == 418

    cases = [
        (SubscriptionNotFoundError(), 404, "status.subscription.not_found"),
        (
            ConfirmationTokenInvalidError(),
            400,
            "status.subscription.confirmation_token_invalid",
        ),
        (
            ConfirmationTokenExpiredError(),
            410,
            "status.subscription.confirmation_token_expired",
        ),
        (
            SubscriptionAlreadyConfirmedError(),
            409,
            "status.subscription.already_confirmed",
        ),
        (
            WebhookVerificationFailedError("timeout"),
            400,
            "status.subscription.webhook_verification_failed",
        ),
    ]
    for error, status_code, code in cases:
        assert error.status_code == status_code
        assert error.code == code

    rate_limited = RateLimitExceededError(30)
    assert rate_limited.status_code == 429
    assert rate_limited.details == {"retry_after_seconds": 30}
