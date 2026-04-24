# Rate-Limit Middleware Contract

**Feature**: 073-api-governance-dx
**Date**: 2026-04-23
**Module**: `apps/control-plane/src/platform/common/middleware/rate_limit_middleware.py`

---

## Placement

`RateLimitMiddleware` is an ASGI `BaseHTTPMiddleware` subclass. It is
installed in `create_app()` AFTER `AuthMiddleware` (so a principal is
already on `request.state.user`) and BEFORE `ApiVersioningMiddleware`
(so 429 responses also pass through the versioning middleware and
carry deprecation headers when applicable).

Execution order (incoming): Correlation → Auth → **RateLimit** →
ApiVersioning → route handler.

---

## Per-request algorithm

```
1. If request.path in EXEMPT_PATHS:
     principal_kind = "anon"
     principal_key  = source_ip(request)
     tier           = get_cached_tier_budgets("anonymous")
2. Else:
     user = request.state.user  (set by AuthMiddleware)
     principal_kind = user["principal_type"]  # "user" | "service_account" | "external_a2a"
     principal_key  = user["principal_id"]
     tier = get_cached_tier_binding_and_budgets(principal_kind, principal_key)
          ↳ cache miss → SELECT tier + budgets from Postgres → cache 60s
          ↳ falls back to "default" tier if no api_rate_limits row

3. keys = [
     f"ratelimit:{principal_kind}:{principal_key}:min",
     f"ratelimit:{principal_kind}:{principal_key}:hour",
     f"ratelimit:{principal_kind}:{principal_key}:day",
   ]
   args = [rpm, rph, rpd, 60, 3600, 86400]

4. [allowed, rem_min, rem_hour, rem_day, retry_after_ms] =
       redis.evalsha("rate_limit_multi_window.lua", 3, keys, args)

5. if allowed == 0:
     response = JSONResponse(status_code=429, content={"error": "rate_limit_exceeded"})
     set_rate_limit_headers(response, rpm, min(rem_min, rem_hour, rem_day), retry_after_ms)
     response.headers["Retry-After"] = str(math.ceil(retry_after_ms / 1000))
     return response

6. response = await call_next(request)
   set_rate_limit_headers(response, rpm, min(rem_min, rem_hour, rem_day), retry_after_ms=0)
   return response
```

Where `set_rate_limit_headers` writes:

- `X-RateLimit-Limit` — RPM of the current tier.
- `X-RateLimit-Remaining` — smallest remaining across all three
  buckets (the most constrained bucket is the one the caller hits
  first).
- `X-RateLimit-Reset` — epoch seconds at which the minute bucket
  resets (always minute-bucket; documented in spec edge case).

---

## Fail-closed behaviour

If the Redis `EVALSHA` raises (connection refused, timeout, or
`NOSCRIPT` after unrecoverable reload), the middleware:

1. Emits a `structlog` WARNING with `redis_unreachable=true`,
   `principal_kind`, `principal_id_hash` (not the raw ID).
2. Consults `FEATURE_API_RATE_LIMITING_FAIL_OPEN` (default `false`).
3. If `FAIL_OPEN=false` (default): returns HTTP 503 with
   `{"error": "rate_limit_service_unavailable"}` and `Retry-After: 30`.
4. If `FAIL_OPEN=true` (incident override): passes the request
   through with `X-RateLimit-Remaining: unknown` and emits a second
   log line tagged `fail_open=true`.

Per constitution principle: no unthrottled bypass without an explicit
audit-logged flag flip.

---

## Settings (Pydantic)

New entries on `PlatformSettings.api_governance`:

| Name | Env var | Default | Purpose |
|---|---|---|---|
| `rate_limiting_enabled` | `FEATURE_API_RATE_LIMITING` | `true` | Master on/off switch (inherited from constitution's feature-flag inventory) |
| `rate_limiting_fail_open` | `FEATURE_API_RATE_LIMITING_FAIL_OPEN` | `false` | Incident-only override — pass requests through when Redis is unreachable |
| `tier_cache_ttl_seconds` | `API_TIER_CACHE_TTL_SECONDS` | `60` | TTL for the principal → tier cache in Redis |
| `principal_cache_ttl_seconds` | `API_PRINCIPAL_CACHE_TTL_SECONDS` | `60` | TTL for the principal binding cache |
| `anonymous_tier_name` | `API_ANONYMOUS_TIER_NAME` | `anonymous` | Name of the tier row applied to public endpoints |
| `default_tier_name` | `API_DEFAULT_TIER_NAME` | `default` | Name of the tier row applied to principals without an override |

All named settings have inline Pydantic field descriptions so the
constitution rule 37 (auto-documentation) is satisfied automatically.

---

## Response header contract (every response, not just rate-limited)

| Header | Format | Value |
|---|---|---|
| `X-RateLimit-Limit` | integer | RPM of the current tier |
| `X-RateLimit-Remaining` | integer | Min(RPM remaining, RPH remaining / 60, RPD remaining / 1440) rounded down |
| `X-RateLimit-Reset` | integer (epoch seconds) | Epoch time at which the minute bucket resets |
| `Retry-After` | integer seconds | Emitted only on 429 and 503; delta-seconds per RFC 7231 §7.1.3 |

**Policy**: Per RFC 6585 §4 guidance. Headers appear on 2xx, 4xx, 5xx
alike (except where upstream exceptions strip them before the
middleware egress pass).

---

## Observability

New Prometheus metrics (emitted via the existing
`common/observability/metrics.py`):

- `rate_limit_decisions_total{decision, principal_kind, tier}` —
  counter.
- `rate_limit_enforcement_duration_seconds{principal_kind}` —
  histogram.
- `rate_limit_redis_errors_total{reason}` — counter.
- `rate_limit_fail_open_activations_total` — counter (increments
  whenever the fail-open path fires).

---

## Unit-test contract

Covered by `apps/control-plane/tests/unit/common/test_rate_limit_middleware.py`:

- **T1** — Below budget: 3 requests in a row on an empty bucket return
  200 with decreasing `X-RateLimit-Remaining`.
- **T2** — Minute exhaustion: 301st request in a minute at default
  tier returns 429 with `Retry-After ∈ [1, 60]`.
- **T3** — Hour exhaustion at default tier: 10001st request in a
  rolling hour returns 429 with `Retry-After > 60`.
- **T4** — Two principals isolated: principal A exhausting does not
  affect principal B.
- **T5** — Tier change: principal moved from `default` to `pro`
  mid-session; next request uses the higher budget.
- **T6** — Anonymous tier: unauthenticated request to `/api/docs`
  counts against `ratelimit:anon:<ip>:*`, not against any principal.
- **T7** — Fail-closed: Redis raises → 503 with `Retry-After: 30`
  when `FAIL_OPEN=false`.
- **T8** — Fail-open override: Redis raises → request passes,
  `X-RateLimit-Remaining` header set to `unknown` when
  `FAIL_OPEN=true`.
- **T9** — Exempt paths: `/health` makes no Redis call (covered by
  `no_call_count`).

---

## Integration-test contract

Covered by `apps/control-plane/tests/integration/common/test_rate_limit_e2e.py`
against a live Postgres + Redis via `compose.integration.yml`:

- Drive 320 sequential requests from a user at `default` tier in a
  single minute; assert the 301st returns 429; assert the 319th and
  320th also return 429; assert the next request after 60 s delay
  returns 200.
- Drive 10 concurrent requests from two principals; assert no
  cross-contamination.
- Bounce Redis mid-traffic; assert fail-closed or fail-open behaviour
  matches config.
