"""UPD-050 — AbusePreventionSettingsService unit tests."""

from __future__ import annotations

from platform.security.abuse_prevention.exceptions import SettingKeyUnknownError
from platform.security.abuse_prevention.settings_service import AbusePreventionSettingsService
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


def _build_service():
    session = MagicMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    audit = MagicMock()
    audit.append = AsyncMock()
    producer = MagicMock()
    producer.publish = AsyncMock()
    return AbusePreventionSettingsService(
        session=session, audit_chain=audit, event_producer=producer
    )


@pytest.mark.asyncio
async def test_set_unknown_key_raises() -> None:
    service = _build_service()
    with pytest.raises(SettingKeyUnknownError):
        await service.set(uuid4(), "ufo_mode", True)


@pytest.mark.asyncio
async def test_set_wrong_type_raises_value_error() -> None:
    service = _build_service()
    # First mock the SELECT to return None (no existing row)
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=None)
    service._session.execute = AsyncMock(return_value=result)
    with pytest.raises(ValueError, match="setting_value_invalid"):
        await service.set(uuid4(), "captcha_enabled", "true")


@pytest.mark.asyncio
async def test_set_idempotent_when_value_unchanged() -> None:
    service = _build_service()
    existing = MagicMock()
    existing.setting_value_json = True
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=existing)
    service._session.execute = AsyncMock(return_value=result)
    await service.set(uuid4(), "captcha_enabled", True)
    # Idempotent path: no commit, no audit, no event
    service._session.commit.assert_not_awaited()
    service._audit.append.assert_not_awaited()
    service._producer.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_updates_audits_publishes() -> None:
    service = _build_service()
    existing = MagicMock()
    existing.setting_value_json = False
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=existing)
    service._session.execute = AsyncMock(return_value=result)
    await service.set(uuid4(), "captcha_enabled", True)
    service._session.commit.assert_awaited_once()
    service._audit.append.assert_awaited_once()
    service._producer.publish.assert_awaited_once()
    # row was mutated in-place
    assert existing.setting_value_json is True
