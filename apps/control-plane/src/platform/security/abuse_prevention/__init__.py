"""Abuse-prevention bounded context (UPD-050).

Owns:

- Velocity counters (Redis hot path + PostgreSQL durable record).
- Disposable-email registry with weekly upstream sync.
- Account-suspension lifecycle and auto-suspension rule engine.
- CAPTCHA verification, geo-blocking, and pluggable fraud-scoring.
- A super-admin admin surface at ``/admin/security/*``.
- Runtime-side cost-protection enforcement of UPD-047 plan caps.

See ``specs/100-abuse-prevention/`` for the full design.
"""
