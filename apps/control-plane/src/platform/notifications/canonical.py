from __future__ import annotations

import hashlib
import hmac
import json
import time
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel

_IDEMPOTENCY_NAMESPACE = uuid5(NAMESPACE_URL, "musematic.notifications.webhooks")


def canonicalise_payload(envelope: object) -> bytes:
    """Return deterministic UTF-8 JSON bytes suitable for signing."""
    payload = _jsonable(envelope)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return unicodedata.normalize("NFC", encoded).encode("utf-8")


def derive_idempotency_key(webhook_id: UUID, event_id: UUID) -> UUID:
    return uuid5(_IDEMPOTENCY_NAMESPACE, f"{webhook_id}:{event_id}")


def build_signature_headers(
    *,
    webhook_id: UUID,
    payload: bytes,
    secret: bytes | str,
    idempotency_key: UUID,
    platform_version: str,
) -> dict[str, str]:
    del webhook_id
    secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
    timestamp = str(int(time.time()))
    signed = f"{timestamp}.".encode("ascii") + payload
    digest = hmac.new(secret_bytes, signed, hashlib.sha256).hexdigest()
    return {
        "X-Musematic-Signature": f"sha256={digest}",
        "X-Musematic-Timestamp": timestamp,
        "X-Musematic-Idempotency-Key": str(idempotency_key),
        "Content-Type": "application/json",
        "User-Agent": f"musematic-webhook/{platform_version}",
    }


def _jsonable(value: object) -> Any:
    if isinstance(value, BaseModel):
        return _jsonable(value.model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_jsonable(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value
