# Debug Logging Admin API + Capture Middleware Contract

**Feature**: 073-api-governance-dx
**Date**: 2026-04-23
**Modules**:
- `apps/control-plane/src/platform/common/debug_logging/router.py` (admin endpoints)
- `apps/control-plane/src/platform/common/debug_logging/capture.py` (ASGI capture middleware)
- `apps/control-plane/src/platform/common/debug_logging/service.py` (business logic)

---

## A. Admin REST endpoints

All admin endpoints live under `/api/v1/admin/debug-logging/*` per
constitution rule 29 (admin endpoint segregation). Every method MUST
depend on `require_admin` or `require_superadmin` per rule 30.

### A.1 `POST /api/v1/admin/debug-logging/sessions`

Open a new debug logging session.

**Auth**: Requires permission `debug_logging_session:create`. Typical
role assignments: `platform_admin`, `auditor` (read-only cannot open).

**Request body**:

```json
{
  "target_type": "user" | "workspace",
  "target_id": "<UUID>",
  "justification": "<string, min 10 chars>",
  "duration_minutes": 60            // optional, default 60, max 240
}
```

**Response `201 Created`**:

```json
{
  "session_id": "<UUID>",
  "target_type": "user",
  "target_id": "<UUID>",
  "justification": "…",
  "started_at": "<ISO-8601>",
  "expires_at": "<ISO-8601>",       // started_at + duration_minutes, capped at 4h
  "capture_count": 0
}
```

**Error cases**:
- `400 Bad Request` — justification shorter than 10 chars, duration
  outside `[1, 240]`, `target_type` unsupported.
- `403 Forbidden` — caller missing `debug_logging_session:create`.
- `409 Conflict` — another active session already exists for
  `(target_type, target_id)` belonging to a different requester. (An
  admin can view but not overlap another admin's investigation.)

**Side effects**:
- Inserts row into `debug_logging_sessions`.
- Publishes `debug_logging.session.created` on `debug_logging.events`.
- Sets Redis `debug_session:active:{target_type}:{target_id}` →
  `session_id` with TTL = remaining session lifetime.

---

### A.2 `GET /api/v1/admin/debug-logging/sessions`

List debug sessions.

**Auth**: Requires permission `debug_logging_session:read`. Typical
role assignments: `platform_admin`, `auditor`, `superadmin`.

**Query params**:
- `active_only` (bool, default `false`) — filter to sessions where
  `terminated_at IS NULL AND expires_at > now()`.
- `requested_by` (UUID, optional) — filter by requester.
- `target_type` + `target_id` (optional pair) — filter by scope.
- `limit` (int, default 50, max 200), `cursor` (opaque pagination).

**Response `200 OK`**:

```json
{
  "items": [ <session objects>... ],
  "next_cursor": "<opaque string or null>"
}
```

---

### A.3 `GET /api/v1/admin/debug-logging/sessions/{session_id}`

Fetch a single session.

**Auth**: `debug_logging_session:read`.

**Response `200 OK`**: full session object + summary counts.

**Error cases**: `404 Not Found` if not present or soft-deleted.

---

### A.4 `DELETE /api/v1/admin/debug-logging/sessions/{session_id}`

Close (terminate) an active session before its `expires_at`.

**Auth**: `debug_logging_session:close`. Typically limited to the
requester OR `superadmin`.

**Response `204 No Content`** on success.

**Side effects**:
- Sets `terminated_at = now()`, `termination_reason = "manual_close"`.
- Deletes Redis `debug_session:active:{target_type}:{target_id}` key.
- Publishes `debug_logging.session.expired`.

**Error cases**:
- `404 Not Found`.
- `409 Conflict` — session already terminated.

---

### A.5 `GET /api/v1/admin/debug-logging/sessions/{session_id}/captures`

List captures belonging to a session.

**Auth**: `debug_logging_session:read`.

**Query params**: `limit` (default 100, max 500), `cursor`.

**Response `200 OK`**:

```json
{
  "items": [
    {
      "id": "<UUID>",
      "captured_at": "<ISO-8601>",
      "method": "POST",
      "path": "/api/v1/workspaces",
      "response_status": 200,
      "duration_ms": 143,
      "correlation_id": "<UUID>",
      "request_headers": { /* redacted */ },
      "request_body": "...[redacted]",
      "response_headers": { /* redacted */ },
      "response_body": "...[redacted]"
    }
  ],
  "next_cursor": null
}
```

---

### A.6 `PATCH /api/v1/admin/debug-logging/sessions/{session_id}`

**Explicitly NOT supported.** Attempting to extend `expires_at` MUST
return `405 Method Not Allowed` with body explaining that the
4-hour maximum is a hard cap and a new session is required (FR-025).

---

## B. Capture middleware

### B.1 Placement

`debug_logging.capture.DebugCaptureMiddleware` is installed AFTER
`RateLimitMiddleware` and BEFORE `ApiVersioningMiddleware`. It MUST
NOT be installed on the outermost path because deprecation headers
should still emit on the 410 short-circuit, and rate limit headers
should appear on debug-captured responses too.

Final order (incoming): Correlation → Auth → RateLimit →
**DebugCapture** → ApiVersioning → route handler.

### B.2 Per-request algorithm

```
1. Resolve target_type + target_id from request:
   - If request.state.user has principal_type == "user":
       candidate_target = ("user", user["principal_id"])
   - Else if request carries X-Workspace-ID header:
       candidate_target = ("workspace", header_value)
   - Else: no candidate (skip capture)

2. For each candidate (a request may match BOTH a user AND a workspace):
   session_id = redis.get(f"debug_session:active:{target_type}:{target_id}")
   if session_id is None: cache miss → SELECT from debug_logging_sessions
      WHERE (target_type, target_id) AND now() < expires_at AND terminated_at IS NULL
      cache the answer (or cache the sentinel "" for no-hit) with 30s TTL

3. If no active session: pass through.

4. Clone the incoming request body (if small); capture it.
5. Call next middleware; capture the response status + headers + body.
6. Redact request_headers, request_body, response_headers, response_body
   per common/debug_logging/redaction.py.
7. INSERT INTO debug_logging_captures (...).
8. UPDATE debug_logging_sessions SET capture_count = capture_count + 1.
9. Publish debug_logging.capture.written on debug_logging.events.
10. Return the original response to the next outer middleware.
```

### B.3 Performance budgets

- Cache hit for "no active session": 0 Redis round-trips (sentinel
  TTL check in local LRU is acceptable for 30 s).
- Cache miss: 1 Postgres indexed lookup, cached 30 s.
- Capture write: 1 Postgres INSERT (non-blocking — the response is
  returned to the client before the Kafka publish completes).

---

## C. Redaction contract

`apps/control-plane/src/platform/common/debug_logging/redaction.py`:

```python
HEADER_ALLOWLIST: frozenset[str] = frozenset({
    "user-agent", "accept", "content-type", "content-length",
    "x-correlation-id", "x-goal-id", "x-request-id", "x-workspace-id",
})

BODY_FIELD_DENYLIST: frozenset[str] = frozenset({
    "password", "password_hash", "token", "access_token", "refresh_token",
    "secret", "client_secret", "api_key", "mfa_secret", "totp_secret",
    "recovery_code", "authorization", "cookie", "set-cookie",
    "email", "email_verified_token", "session_id",
})

QUERY_PARAM_DENYLIST: frozenset[str] = frozenset({
    "code", "state", "access_token", "id_token",
})

SECRET_REGEX = [
    r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",   # JWT
    r"Bearer\s+[A-Za-z0-9_\-.=]+",                           # Bearer tokens
    r"msk_[A-Za-z0-9]{32,}",                                 # Platform API keys
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",  # Emails
]

def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        k: (v if k.lower() in HEADER_ALLOWLIST else "[REDACTED]")
        for k, v in headers.items()
    }

def redact_body(body: bytes, content_type: str) -> str:
    text = _decode_truncated(body, max_bytes=8192)
    if content_type.startswith("application/json"):
        text = _redact_json_fields(text, BODY_FIELD_DENYLIST)
    for pattern in SECRET_REGEX:
        text = re.sub(pattern, "[REDACTED]", text)
    return text

def redact_path(path: str) -> str:
    """Strip denylisted query params from a path."""
    ...
```

---

## D. Unit-test contract

- **D1** — Headers: `Authorization: Bearer xyz` → `[REDACTED]`;
  `User-Agent: curl` → verbatim.
- **D2** — JSON body: `{"password": "hunter2", "name": "alice"}` →
  `{"password": "[REDACTED]", "name": "alice"}`.
- **D3** — JWT in free text: `"token: eyJabc.eyJdef.ghi"` →
  `"token: [REDACTED]"`.
- **D4** — Email regex: `"user@example.com"` → `"[REDACTED]"`.
- **D5** — Query params: `/callback?code=x&state=y&foo=z` →
  `/callback?foo=z`.
- **D6** — Body truncation: 9 KiB body → truncated at 8 KiB with
  `…[truncated=<sha256-32>]` suffix; sha is the sha256 hex of the
  original body's first 8 KiB.

---

## E. Integration-test contract

- **E1** — Open a session for user A; user A makes 3 requests while
  the session is active; all 3 are captured. User B's requests are
  not captured.
- **E2** — Open a session for workspace W; a request whose
  `X-Workspace-ID` header equals W is captured even if the acting user
  has no personal session.
- **E3** — Session expiry: open a 1-minute session; after 65 seconds,
  user A's requests are not captured.
- **E4** — Termination via DELETE: after close, no further captures.
- **E5** — RTBF cascade: user A is deleted → session auto-terminates,
  captures cascade-delete via FK.
- **E6** — Session-create emits Kafka event on `debug_logging.events`
  with the expected shape; session-expired and capture-written
  similarly.
