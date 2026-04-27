# MCP Integration and Outbound Webhook Verification

Musematic's MCP integration is routed through the platform tool gateway. Tool descriptors should declare purpose, input schema, output schema, credential references, and audit metadata. Runtime calls are authorized by workspace visibility, policy bundles, and purpose checks before execution.

The current implementation still treats parts of the MCP surface as evolving. Keep integrations tolerant of additional fields and pin clients to a platform release when building production automations.

## Outbound Webhook Verification

musematic signs every outbound webhook with HMAC-SHA-256 over the exact canonical JSON bytes sent in the HTTP request body.

Receivers should verify the signature before processing the event, reject stale timestamps, and deduplicate with `X-Musematic-Idempotency-Key`.

```python
from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Mapping


def verify_musematic_signature(
    headers: Mapping[str, str],
    body: bytes,
    secret: bytes | str,
    *,
    replay_window_seconds: int = 300,
) -> bool:
    signature = headers["X-Musematic-Signature"].removeprefix("sha256=")
    timestamp = int(headers["X-Musematic-Timestamp"])
    if abs(time.time() - timestamp) > replay_window_seconds:
        raise ValueError("stale signature")

    secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
    signed = f"{timestamp}.".encode("ascii") + body
    expected = hmac.new(secret_bytes, signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("bad signature")
    return True
```

Minimum receiver rules:

- Use the raw request body bytes exactly as received. Do not reserialize JSON before verifying.
- Treat `X-Musematic-Idempotency-Key` as the deduplication key; retries of the same event reuse it.
- Reject signatures outside the replay window before performing side effects.
- Store the HMAC secret in your own secret manager and rotate it when the webhook secret is rotated in musematic.
