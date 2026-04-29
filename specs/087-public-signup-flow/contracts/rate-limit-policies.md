# Signup Rate-Limit Policy Audit

Date: 2026-04-27

## Current Enforcement Path

`POST /api/v1/accounts/register` is public in `AuthMiddleware.EXEMPT_PATHS`, so `RateLimitMiddleware` treats callers as anonymous and resolves the policy with `RateLimiterService.resolve_anonymous_policy(source_ip)`.

That policy is tier based. It reads the tier named by `settings.api_governance.anonymous_tier_name` from `api_subscription_tiers` and enforces the shared multi-window limits (`requests_per_minute`, `requests_per_hour`, `requests_per_day`) against Redis keys keyed by source IP.

## FR-588 Enforcement

FR-588 requires signup-specific limits:

- 5 attempts per hour per source IP
- 3 attempts per 24 hours per email address

UPD-037 adds route-specific registration counters in `AccountsService.register()` while preserving the generic anonymous middleware for other public endpoints:

- `accounts:signup:ip:{source_ip}` with a one-hour TTL and a max count of 5
- `accounts:signup:email:{sha256(email)}` with a 24-hour TTL and a max count of 3

Either limit returns `429` with `Retry-After`. The email counter uses a SHA-256 digest so Redis keys do not expose raw email addresses.
