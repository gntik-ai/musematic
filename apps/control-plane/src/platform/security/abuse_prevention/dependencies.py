"""FastAPI dependency builders for the abuse-prevention BC.

Per UPD-050 T017 — wires `AbusePreventionService` (signup-guards façade)
into the request scope so the accounts BC's register endpoint can call
`check_signup_guards` before reaching `AccountsService.register`.
"""

from __future__ import annotations

from platform.audit.dependencies import build_audit_chain_service
from platform.common import database
from platform.security.abuse_prevention.disposable_emails import (
    DisposableEmailService,
)
from platform.security.abuse_prevention.repository import (
    TrustedSourceAllowlistRepository,
)
from platform.security.abuse_prevention.service import AbusePreventionService
from platform.security.abuse_prevention.settings_service import (
    AbusePreventionSettingsService,
)
from platform.security.abuse_prevention.velocity import SignupVelocityLimiter
from typing import Any

from fastapi import Request


def _event_producer(request: Request) -> Any:
    return getattr(request.app.state, "event_producer", None)


def _redis_client(request: Request) -> Any:
    return getattr(request.app.state, "redis_client", None)


async def build_abuse_prevention_facade(
    request: Request,
) -> AbusePreventionService:
    """Build the per-request `AbusePreventionService` façade.

    Used as a FastAPI Depends from `accounts/router.py:register`. Each
    sub-service binds to a fresh DB session that is closed when the
    request ends.
    """
    # The session lifetime is handled by the caller — accounts/router.py
    # uses its own session context. We use the BYPASSRLS staff session
    # for cross-tenant settings + allowlist reads (signup is pre-tenant).
    settings = request.app.state.settings
    producer = _event_producer(request)
    redis = _redis_client(request)

    session_ctx = database.PlatformStaffAsyncSessionLocal()
    session = await session_ctx.__aenter__()
    request.state._abuse_session_ctx = session_ctx  # cleaned up by middleware

    settings_service = AbusePreventionSettingsService(
        session=session,
        audit_chain=build_audit_chain_service(
            session=session, settings=settings, producer=producer
        ),
        event_producer=producer,
    )
    velocity_limiter = SignupVelocityLimiter(redis=redis)
    disposable_service = DisposableEmailService(session=session, redis=redis)
    trusted_repo = TrustedSourceAllowlistRepository(session=session)

    return AbusePreventionService(
        settings=settings_service,
        velocity=velocity_limiter,
        disposable=disposable_service,
        trusted=trusted_repo,
        event_producer=producer,
    )
