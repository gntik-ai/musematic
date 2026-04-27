# Signup Rate-Limit Policy Audit

Date: 2026-04-27

## Current Enforcement Path

`POST /api/v1/accounts/register` is public in `AuthMiddleware.EXEMPT_PATHS`, so `RateLimitMiddleware` treats callers as anonymous and resolves the policy with `RateLimiterService.resolve_anonymous_policy(source_ip)`.

That policy is tier based. It reads the tier named by `settings.api_governance.anonymous_tier_name` from `api_subscription_tiers` and enforces the shared multi-window limits (`requests_per_minute`, `requests_per_hour`, `requests_per_day`) against Redis keys keyed by source IP.

## FR-588 Gap

FR-588 requires signup-specific limits:

- 5 attempts per hour per source IP
- 3 attempts per 24 hours per email address

The current generic anonymous policy does not distinguish `/api/v1/accounts/register` from other public endpoints and has no per-email limiter for registration attempts. The resend-verification path has a separate per-user Redis counter capped by `ACCOUNTS_RESEND_RATE_LIMIT`, but that is not the same as the FR-588 per-email signup-registration limit.

## Required Follow-Up

Implement a route-specific signup limiter before T048 is considered complete. It should preserve the existing middleware for general anonymous traffic while adding the FR-588 per-IP and per-email windows for `POST /api/v1/accounts/register`, returning `429` with `Retry-After` when either window is exceeded.
