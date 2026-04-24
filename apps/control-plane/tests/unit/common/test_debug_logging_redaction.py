from __future__ import annotations

import hashlib
import json
from platform.common.debug_logging.redaction import redact_body, redact_headers, redact_path


def test_headers_only_keep_allowlisted_values() -> None:
    redacted = redact_headers(
        {
            "Authorization": "Bearer secret-token",
            "User-Agent": "curl/8.0",
        }
    )

    assert redacted == {
        "Authorization": "[REDACTED]",
        "User-Agent": "curl/8.0",
    }


def test_json_body_redacts_denylisted_fields() -> None:
    payload = json.dumps({"password": "hunter2", "name": "alice"}).encode("utf-8")

    redacted = redact_body(payload, "application/json")

    assert json.loads(redacted) == {"password": "[REDACTED]", "name": "alice"}


def test_jwt_like_tokens_in_text_are_redacted() -> None:
    redacted = redact_body(b"token: eyJabc.eyJdef.ghi", "text/plain")

    assert redacted == "token: [REDACTED]"


def test_emails_are_redacted() -> None:
    redacted = redact_body(b"user@example.com", "text/plain")

    assert redacted == "[REDACTED]"


def test_query_params_strip_denylisted_values() -> None:
    assert redact_path("/callback?code=x&state=y&foo=z") == "/callback?foo=z"


def test_large_body_truncates_with_digest_suffix() -> None:
    body = b"a" * 9000
    redacted = redact_body(body, "text/plain")
    digest = hashlib.sha256(body[:8192]).hexdigest()[:32]

    assert redacted.endswith(f"…[truncated={digest}]")
    assert len(redacted.split("…[truncated=")[0].encode("utf-8")) == 8192
