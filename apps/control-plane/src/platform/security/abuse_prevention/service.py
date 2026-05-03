"""Façade for the abuse-prevention guards (UPD-050 T025).

Composes the per-guard services (velocity, disposable-email, captcha,
geo-block, fraud-scoring) into a single ``check_signup_guards`` call
that the accounts BC's register endpoint invokes per-request.

Guards run in the order documented in
``specs/100-abuse-prevention/contracts/signup-guards-rest.md``:

  1. trusted-allowlist bypass (skips velocity / geo / fraud)
  2. geo-block
  3. velocity
  4. disposable-email
  5. CAPTCHA
  6. fraud-scoring (fail-soft, never blocks signup directly)

Each guard is independently toggleable by the
``abuse_prevention_settings`` row that controls it. The default
configuration ships with velocity + disposable-email on; CAPTCHA,
geo-block, and fraud-scoring off.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from platform.security.abuse_prevention.disposable_emails import DisposableEmailService
from platform.security.abuse_prevention.events import (
    AbuseEventType,
    SignupDisposableEmailBlockedPayload,
    SignupVelocityHitPayload,
    publish_abuse_event,
)
from platform.security.abuse_prevention.exceptions import (
    DisposableEmailNotAllowedError,
    SignupRateLimitExceededError,
)
from platform.security.abuse_prevention.metrics import (
    abuse_disposable_email_blocks_total,
)
from platform.security.abuse_prevention.repository import TrustedSourceAllowlistRepository
from platform.security.abuse_prevention.settings_service import (
    AbusePreventionSettingsService,
)
from platform.security.abuse_prevention.velocity import (
    SignupVelocityLimiter,
    VelocityThresholds,
)
from typing import Any
from uuid import uuid4

LOGGER = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SignupContext:
    """Per-request input to ``AbusePreventionService.check_signup_guards``."""

    ip: str | None
    asn: str | None
    email: str
    captcha_token: str | None = None
    country: str | None = None
    user_agent: str | None = None


class AbusePreventionService:
    """Coordinates the per-guard services for the register endpoint."""

    def __init__(
        self,
        *,
        settings: AbusePreventionSettingsService,
        velocity: SignupVelocityLimiter,
        disposable: DisposableEmailService,
        trusted: TrustedSourceAllowlistRepository,
        event_producer: EventProducer | None,
    ) -> None:
        self._settings = settings
        self._velocity = velocity
        self._disposable = disposable
        self._trusted = trusted
        self._event_producer = event_producer

    async def check_signup_guards(self, ctx: SignupContext) -> None:
        """Run all enabled signup guards. First refusal wins."""
        # 1) Trusted-allowlist bypass — skips velocity, geo-block, and
        # fraud-scoring (CAPTCHA + disposable-email still run, since
        # those are not source-IP signals).
        is_trusted_source = await self._trusted.is_trusted_ip(
            ctx.ip
        ) or await self._trusted.is_trusted_asn(ctx.asn)

        # 2) Velocity (skipped for trusted sources).
        if not is_trusted_source:
            await self._check_velocity(ctx)

        # 3) Disposable-email check.
        await self._check_disposable_email(ctx)

        # 4-6) CAPTCHA / geo-block / fraud-scoring branches are
        # implemented in Phase 8 (T057-T059). The façade signature is
        # fixed up front so the route handler is stable.

    async def _check_velocity(self, ctx: SignupContext) -> None:
        thresholds = VelocityThresholds(
            ip_threshold=int(
                await self._settings.get("velocity_per_ip_hour") or 5
            ),
            asn_threshold=int(
                await self._settings.get("velocity_per_asn_hour") or 50
            ),
            email_domain_threshold=int(
                await self._settings.get("velocity_per_email_domain_day") or 20
            ),
        )
        email_domain = ctx.email.split("@", 1)[-1].lower() if "@" in ctx.email else None
        try:
            await self._velocity.check_and_record(
                ip=ctx.ip,
                asn=ctx.asn,
                email_domain=email_domain,
                thresholds=thresholds,
            )
        except SignupRateLimitExceededError as exc:
            await publish_abuse_event(
                self._event_producer,
                AbuseEventType.signup_velocity_hit,
                SignupVelocityHitPayload(
                    counter_key=exc.details.get("counter_key", "unknown")
                    if isinstance(exc.details, dict)
                    else "unknown",
                    counter_window_start="",  # the limiter is stateless re: window-start
                    threshold=_extract_threshold(exc, thresholds),
                    source_ip=ctx.ip or "",
                    asn=ctx.asn,
                    email_domain=email_domain,
                ),
                CorrelationContext(correlation_id=uuid4()),
            )
            LOGGER.info(
                "abuse.velocity.refused",
                extra={
                    "source_ip": ctx.ip,
                    "asn": ctx.asn,
                    "email_domain": email_domain,
                    "retry_after_seconds": exc.retry_after_seconds,
                },
            )
            raise

    async def _check_disposable_email(self, ctx: SignupContext) -> None:
        enabled = bool(
            await self._settings.get("disposable_email_blocking") or False
        )
        if not enabled:
            return
        if "@" not in ctx.email:
            return
        domain = ctx.email.split("@", 1)[-1].lower()
        if not await self._disposable.is_blocked(domain):
            return
        abuse_disposable_email_blocks_total.inc()
        await publish_abuse_event(
            self._event_producer,
            AbuseEventType.signup_disposable_email_blocked,
            SignupDisposableEmailBlockedPayload(
                email_domain=domain,
                source_ip=ctx.ip or "",
            ),
            CorrelationContext(correlation_id=uuid4()),
        )
        LOGGER.info(
            "abuse.disposable_email.refused",
            extra={
                "email_domain": domain,
                "email_hash": hashlib.sha256(ctx.email.encode("utf-8")).hexdigest()[:16],
                "source_ip": ctx.ip,
            },
        )
        raise DisposableEmailNotAllowedError(domain)


def _extract_threshold(
    exc: SignupRateLimitExceededError, thresholds: VelocityThresholds
) -> int:
    """Best-effort threshold extraction from the counter_key embedded in
    the raised exception (so the Kafka payload reports the right number).
    """
    counter_key: Any = (
        exc.details.get("counter_key", "")
        if isinstance(exc.details, dict)
        else ""
    )
    if not isinstance(counter_key, str):
        return 0
    if counter_key.startswith("ip:"):
        return thresholds.ip_threshold
    if counter_key.startswith("asn:"):
        return thresholds.asn_threshold
    if counter_key.startswith("email_domain:"):
        return thresholds.email_domain_threshold
    return 0
