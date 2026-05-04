"""UPD-052 — Stripe-specific provider implementation.

Modules:

* :mod:`secrets` — Vault-backed Stripe secret loader (api key + webhook secret pair)
* :mod:`webhook_signing` — dual-secret HMAC verification for the webhook ingress
* :mod:`client` — `stripe` SDK initializer with API-version pinning + retry
* :mod:`customer`, :mod:`subscription`, :mod:`usage`, :mod:`portal`, :mod:`tax` — feature helpers
* :mod:`provider` — :class:`StripePaymentProvider` composing all of the above
"""
