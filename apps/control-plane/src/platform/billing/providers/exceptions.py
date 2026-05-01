from __future__ import annotations

from platform.billing.exceptions import PaymentProviderError as BillingPaymentProviderError


class PaymentProviderError(BillingPaymentProviderError):
    pass


class PaymentMethodInvalid(PaymentProviderError):  # noqa: N818
    def __init__(self, provider: str, reason: str = "Payment method is invalid") -> None:
        super().__init__(provider, reason)
        self.code = "BILLING_PAYMENT_METHOD_INVALID"


class ProviderUnavailable(PaymentProviderError):  # noqa: N818
    status_code = 503

    def __init__(self, provider: str, reason: str = "Payment provider unavailable") -> None:
        super().__init__(provider, reason)
        self.code = "BILLING_PAYMENT_PROVIDER_UNAVAILABLE"


class IdempotencyConflict(PaymentProviderError):  # noqa: N818
    status_code = 409

    def __init__(self, provider: str, idempotency_key: str) -> None:
        super().__init__(provider, "Provider idempotency key conflict")
        self.code = "BILLING_PAYMENT_IDEMPOTENCY_CONFLICT"
        self.details["idempotency_key"] = idempotency_key
