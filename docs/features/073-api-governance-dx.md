# API Governance and Developer Experience

## Summary

Feature `073-api-governance-dx` ships the cross-cutting platform guardrails for API consumers: discoverable OpenAPI 3.1 docs, release-time SDK generation, per-principal rate limiting, HTTP deprecation headers with sunset enforcement, and audited time-bounded debug logging.

## Delivered capabilities

- Canonical OpenAPI document exposed at `/api/openapi.json` plus Swagger UI at `/api/docs` and Redoc at `/api/redoc`.
- Spectral linting in CI to enforce operation tags, security metadata, and admin tagging conventions.
- Release workflow `sdks.yml` that fetches the published schema, guards against breaking changes, generates Python / Go / TypeScript / Rust SDKs, and publishes them.
- Redis-backed multi-window rate limiting with per-minute, per-hour, and per-day budgets plus `X-RateLimit-*` headers and 429 enforcement.
- URL-based API deprecation markers that emit `Deprecation`, `Sunset`, and successor `Link` headers and return HTTP 410 once the sunset threshold is reached.
- Admin-only debug logging sessions scoped to a user or workspace, with redacted request / response capture, Kafka audit events, and retention-driven cleanup.

## Operational notes

- Rate limiting depends on Redis script preload during control-plane startup; fail-open behavior is controlled by `FEATURE_API_RATE_LIMITING_FAIL_OPEN`.
- Debug logging sessions are capped at four hours and inherit the platform audit retention window.
- SDK publishing requires repository Actions secrets documented in `docs/administration/integrations-and-credentials.md`.
