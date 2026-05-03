"""CAPTCHA verification for the signup-guard path (UPD-050 T057).

Two adapters share a Protocol:

- ``TurnstileVerifier`` — Cloudflare Turnstile (default).
- ``HCaptchaVerifier`` — hCaptcha alternate provider.

Both POST to the provider's `siteverify` endpoint with the harvested
client token plus the source IP. Replay protection: a SHA-256 hash of
each successfully-verified token is stored in Redis under
``abuse:captcha_seen:{hash}`` with a 5-minute TTL (matching the token's
documented validity window). A second verification of the same token
fails with ``CaptchaInvalidError(reason="token_replayed")``.

Per FR-014/FR-015 CAPTCHA is off by default; the
``captcha_enabled``/``captcha_provider`` settings (admin surface)
control whether this path runs at all.
"""

from __future__ import annotations

import hashlib
from platform.common.clients.redis import AsyncRedisClient
from platform.common.logging import get_logger
from platform.security.abuse_prevention.exceptions import (
    CaptchaInvalidError,
    CaptchaRequiredError,
)
from platform.security.abuse_prevention.metrics import abuse_captcha_failures_total
from typing import Protocol

import httpx

LOGGER = get_logger(__name__)

REPLAY_KEY_TEMPLATE = "abuse:captcha_seen:{token_hash}"
REPLAY_TTL_SECONDS = 300  # match Turnstile / hCaptcha token validity


class CaptchaVerifier(Protocol):
    """Provider-agnostic verification protocol."""

    async def verify(self, *, token: str, remote_ip: str | None) -> None: ...


class TurnstileVerifier:
    """Cloudflare Turnstile verifier (default provider).

    Uses the documented siteverify URL
    (``https://challenges.cloudflare.com/turnstile/v0/siteverify``).
    """

    URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

    def __init__(
        self,
        *,
        secret: str,
        redis: AsyncRedisClient,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._secret = secret
        self._redis = redis
        self._timeout = timeout_seconds

    async def verify(self, *, token: str, remote_ip: str | None) -> None:
        await _verify(
            token=token,
            remote_ip=remote_ip,
            secret=self._secret,
            url=self.URL,
            redis=self._redis,
            timeout=self._timeout,
        )


class HCaptchaVerifier:
    """hCaptcha alternate provider."""

    URL = "https://hcaptcha.com/siteverify"

    def __init__(
        self,
        *,
        secret: str,
        redis: AsyncRedisClient,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._secret = secret
        self._redis = redis
        self._timeout = timeout_seconds

    async def verify(self, *, token: str, remote_ip: str | None) -> None:
        await _verify(
            token=token,
            remote_ip=remote_ip,
            secret=self._secret,
            url=self.URL,
            redis=self._redis,
            timeout=self._timeout,
        )


async def _verify(
    *,
    token: str,
    remote_ip: str | None,
    secret: str,
    url: str,
    redis: AsyncRedisClient,
    timeout: float,  # noqa: ASYNC109 — provider-level HTTP timeout, not asyncio cancellation
) -> None:
    if not token:
        abuse_captcha_failures_total.labels(reason="token_missing").inc()
        raise CaptchaRequiredError()

    # Replay protection — refuse if the token's hash is already in the
    # cache.
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    key = REPLAY_KEY_TEMPLATE.format(token_hash=token_hash)
    client = redis.client
    if client is not None:
        existing = await client.get(key)
        if existing is not None:
            abuse_captcha_failures_total.labels(reason="token_replayed").inc()
            raise CaptchaInvalidError(reason="token_replayed")

    payload = {"secret": secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        async with httpx.AsyncClient(timeout=timeout) as http:
            response = await http.post(url, data=payload)
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPError:
        abuse_captcha_failures_total.labels(reason="provider_error").inc()
        LOGGER.exception(
            "abuse.captcha.provider_error", extra={"url": url}
        )
        raise CaptchaInvalidError(reason="provider_error") from None

    if not body.get("success", False):
        abuse_captcha_failures_total.labels(reason="token_invalid").inc()
        raise CaptchaInvalidError(reason="token_invalid")

    # Record the token-hash with the replay TTL.
    if client is not None:
        # set() with EX is the canonical replay-cache shape.
        await client.set(key, "1", ex=REPLAY_TTL_SECONDS)
