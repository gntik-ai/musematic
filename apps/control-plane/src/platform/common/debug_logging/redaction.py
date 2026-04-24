from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

HEADER_ALLOWLIST: frozenset[str] = frozenset(
    {
        "user-agent",
        "accept",
        "content-type",
        "content-length",
        "x-correlation-id",
        "x-goal-id",
        "x-request-id",
        "x-workspace-id",
    }
)

BODY_FIELD_DENYLIST: frozenset[str] = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "client_secret",
        "api_key",
        "mfa_secret",
        "totp_secret",
        "recovery_code",
        "authorization",
        "cookie",
        "set-cookie",
        "email",
        "email_verified_token",
        "session_id",
    }
)

QUERY_PARAM_DENYLIST: frozenset[str] = frozenset({"code", "state", "access_token", "id_token"})

SECRET_REGEX: tuple[str, ...] = (
    r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
    r"Bearer\s+[A-Za-z0-9_\-.=]+",
    r"msk_[A-Za-z0-9]{32,}",
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
)


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value if key.lower() in HEADER_ALLOWLIST else "[REDACTED]"
        for key, value in headers.items()
    }


def redact_body(body: bytes, content_type: str) -> str:
    text = _decode_truncated(body, max_bytes=8192)
    if content_type.startswith("application/json"):
        text = _redact_json_fields(text, BODY_FIELD_DENYLIST)
    for pattern in SECRET_REGEX:
        text = re.sub(pattern, "[REDACTED]", text)
    return text


def redact_path(path: str) -> str:
    parts = urlsplit(path)
    sanitized_query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in QUERY_PARAM_DENYLIST
        ],
        doseq=True,
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, sanitized_query, parts.fragment))


def _decode_truncated(body: bytes, *, max_bytes: int) -> str:
    prefix = body[:max_bytes]
    text = prefix.decode("utf-8", errors="replace")
    if len(body) <= max_bytes:
        return text
    digest = hashlib.sha256(prefix).hexdigest()[:32]
    return f"{text}…[truncated={digest}]"


def _redact_json_fields(text: str, denylist: frozenset[str]) -> str:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    redacted = _walk_json(payload, denylist)
    return json.dumps(redacted, ensure_ascii=False)


def _walk_json(value: object, denylist: frozenset[str]) -> object:
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, nested_value in value.items():
            if key.lower() in denylist:
                result[key] = "[REDACTED]"
            else:
                result[key] = _walk_json(nested_value, denylist)
        return result
    if isinstance(value, list):
        return [_walk_json(item, denylist) for item in value]
    return value
