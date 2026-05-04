"""UPD-052 — Stripe webhook event handlers.

The :mod:`registry` module owns the dispatch map. Handlers themselves live in
:mod:`subscription`, :mod:`invoice`, :mod:`payment_method`, and :mod:`dispute`.
Each handler is a pure async function that receives the verified
:class:`WebhookEvent` plus a context bundle (DB session, services, producer)
and returns ``None``. Side-effect logic stays inside the handler — the
registry is intentionally a thin lookup.
"""
