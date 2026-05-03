"""UPD-050 — DisposableEmailService cache test."""

from __future__ import annotations

from platform.security.abuse_prevention.disposable_emails import DisposableEmailService
from unittest.mock import AsyncMock, MagicMock

import pytest


def _build_service(domains: set[str], overrides: set[str]):
    """Builds a service whose session.execute returns the domain rows on
    the first call and the override rows on the second (the order
    `_refresh_cache` issues them).
    """
    session = MagicMock()
    domain_result = MagicMock()
    domain_result.all = MagicMock(return_value=[(d,) for d in domains])
    override_result = MagicMock()
    override_result.all = MagicMock(return_value=[(d,) for d in overrides])
    session.execute = AsyncMock(side_effect=[domain_result, override_result] * 10)
    return DisposableEmailService(session=session, redis=None)


@pytest.mark.asyncio
async def test_block_when_in_list() -> None:
    service = _build_service({"10minutemail.com"}, set())
    assert await service.is_blocked("10minutemail.com") is True


@pytest.mark.asyncio
async def test_override_takes_precedence() -> None:
    service = _build_service({"corp-catchall.com"}, {"corp-catchall.com"})
    assert await service.is_blocked("corp-catchall.com") is False


@pytest.mark.asyncio
async def test_unknown_domain_not_blocked() -> None:
    service = _build_service({"10minutemail.com"}, set())
    assert await service.is_blocked("legitimate.com") is False


@pytest.mark.asyncio
async def test_normalisation_lowercases() -> None:
    service = _build_service({"10minutemail.com"}, set())
    assert await service.is_blocked("  10MinuteMail.COM  ") is True
