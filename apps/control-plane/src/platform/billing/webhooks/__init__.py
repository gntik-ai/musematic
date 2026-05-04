"""UPD-052 webhooks sub-bounded-context.

Owns the ``POST /api/webhooks/stripe`` ingress, dual-secret HMAC verification,
two-layer (Redis + PostgreSQL) idempotency, and the per-event-type handler
registry. Handlers themselves live under ``handlers/``.
"""
