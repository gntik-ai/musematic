# API Versioning Middleware Contract

**Feature**: 073-api-governance-dx
**Date**: 2026-04-23
**Module**: `apps/control-plane/src/platform/common/middleware/api_versioning_middleware.py`

---

## Placement

`ApiVersioningMiddleware` is the outermost custom middleware (after
any framework-level middleware FastAPI installs). It runs on the way
in to decide whether the route is sunset-past-due, and on the way out
to decorate headers.

Execution order (incoming): Correlation → Auth → RateLimit →
**ApiVersioning** → route handler. Outgoing reverses.

---

## Inbound behaviour

```
1. Resolve route = request.scope["route"] (set by Starlette routing layer; may be None for 404)
2. If route is None or has no route_id: pass through.
3. marker = get_marker(route.unique_id)  # from common/api_versioning/registry.py
4. If marker exists AND datetime.now(UTC) >= marker.sunset:
     response = JSONResponse(
       status_code=410,
       content={
         "error": "endpoint_sunset",
         "successor": marker.successor_path,  # may be null
         "sunset_date": marker.sunset.isoformat(),
       },
     )
     # Still emit deprecation headers on the 410 response
     _decorate(response, marker)
     return response
5. Else: proceed to next middleware.
```

---

## Outbound behaviour

```
6. response = await call_next(request)
7. If marker exists AND datetime.now(UTC) < marker.sunset:
     response.headers["Deprecation"] = "true"
     response.headers["Sunset"] = marker.sunset.strftime("%a, %d %b %Y %H:%M:%S GMT")  # RFC 9110 HTTP-date
     if marker.successor_path:
         response.headers["Link"] = f'<{marker.successor_path}>; rel="successor-version"'
8. Return response.
```

**Note**: Deprecation/Sunset headers are emitted whether the response
was 2xx, 4xx, or 5xx — any client receiving anything from a
deprecated endpoint MUST learn of the sunset.

---

## `@deprecated_route` decorator

```python
# common/api_versioning/decorator.py

from datetime import datetime
from typing import Callable
from fastapi.routing import APIRoute
from .registry import mark_deprecated

def deprecated_route(
    *,
    sunset: str | datetime,   # ISO-8601 date or datetime
    successor: str | None = None,
) -> Callable:
    """Decorator for FastAPI route handlers. Marks the route deprecated.

    Usage:
        @router.get("/legacy-endpoint")
        @deprecated_route(sunset="2026-10-01", successor="/api/v2/new-endpoint")
        async def legacy_endpoint(...):
            ...
    """
    sunset_dt = sunset if isinstance(sunset, datetime) else datetime.fromisoformat(sunset)

    def decorator(fn: Callable) -> Callable:
        # Mark the underlying function; after route registration a
        # post-register hook will copy the marker into the route object.
        fn.__deprecated_marker__ = (sunset_dt, successor)
        return fn

    return decorator
```

**Registration hook**: In `create_app()`, after all routers are
mounted, iterate through `app.routes` and copy any
`__deprecated_marker__` attribute from the endpoint into the registry
keyed by `route.unique_id`. Simultaneously set `route.deprecated =
True` so FastAPI's OpenAPI generator emits `deprecated: true`.

```python
# main.py, near the end of create_app()
for route in app.routes:
    if isinstance(route, APIRoute):
        marker = getattr(route.endpoint, "__deprecated_marker__", None)
        if marker:
            sunset, successor = marker
            mark_deprecated(route.unique_id, sunset=sunset, successor=successor)
            route.deprecated = True
```

---

## Successor discoverability in OpenAPI

The FastAPI OpenAPI generator does not natively emit a "successor"
field. To surface it to SDK consumers, the `@deprecated_route`
decorator also mutates the handler's docstring at registration time,
prepending:

```
.. deprecated:: Sunset on {sunset_date}. Successor: {successor}
```

FastAPI lifts the docstring into the operation's `description` in the
OpenAPI document, so SDK consumers see the sunset date and successor
path in the generated client.

---

## Unit-test contract

Covered by
`apps/control-plane/tests/unit/common/test_api_versioning_middleware.py`:

- **V1** — Non-deprecated route: response has no `Deprecation`,
  `Sunset`, or `Link` headers.
- **V2** — Deprecated route before sunset: response has
  `Deprecation: true` and `Sunset: <RFC-9110 HTTP-date>`.
- **V3** — Deprecated route with successor: `Link` header is present
  with `rel="successor-version"`.
- **V4** — Deprecated route after sunset: response is 410 with body
  `{"error": "endpoint_sunset", "successor": …, "sunset_date": …}`.
- **V5** — Sunset in the future by 1 minute: endpoint still
  functional; response 200 with deprecation headers.
- **V6** — Sunset exactly at current time: returns 410 (boundary
  inclusive — "after the sunset date passes" covers `>=`).
- **V7** — Deprecation visible in OpenAPI: generated doc has
  `deprecated: true` for the operation AND the description contains
  the sunset + successor prose.

---

## Integration-test contract

Covered by
`apps/control-plane/tests/integration/common/test_versioning_e2e.py`:

- Register a stub route `/api/v1/legacy-test` with a sunset 1 hour in
  the future and successor `/api/v2/new-test`.
- Hit `/api/v1/legacy-test` with a valid auth token. Assert 200 with
  `Deprecation: true`, `Sunset: <HTTP-date>`, `Link: </api/v2/new-test>;
  rel="successor-version"`.
- Monkey-patch datetime.now to be 1 minute past sunset. Hit the route
  again. Assert 410 with body pointing at the successor.
- Fetch `/api/openapi.json`. Assert operation for `/api/v1/legacy-test`
  has `"deprecated": true` and the description mentions the sunset date.
