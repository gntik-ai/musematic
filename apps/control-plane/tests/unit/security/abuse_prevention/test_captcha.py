"""UPD-050 — CAPTCHA verifier tests with mocked HTTP + Redis."""

from __future__ import annotations

from platform.security.abuse_prevention.captcha import (
    TurnstileVerifier,
)
from platform.security.abuse_prevention.exceptions import (
    CaptchaInvalidError,
    CaptchaRequiredError,
)
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeClient:
    def __init__(self, store: dict[str, str]) -> None:
        self._store = store

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self._store[key] = value


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self.client = _FakeClient(self._store)


@pytest.mark.asyncio
async def test_missing_token_raises_required() -> None:
    verifier = TurnstileVerifier(secret="s3cret", redis=_FakeRedis())
    with pytest.raises(CaptchaRequiredError):
        await verifier.verify(token="", remote_ip="1.2.3.4")


@pytest.mark.asyncio
async def test_invalid_token_raises_invalid() -> None:
    redis = _FakeRedis()
    verifier = TurnstileVerifier(secret="s3cret", redis=redis)
    mock_response = MagicMock()
    mock_response.json = MagicMock(return_value={"success": False})
    mock_response.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(CaptchaInvalidError) as exc:
            await verifier.verify(token="bad-token", remote_ip="1.2.3.4")
    assert exc.value.details["reason"] == "token_invalid"


@pytest.mark.asyncio
async def test_replay_protection() -> None:
    redis = _FakeRedis()
    verifier = TurnstileVerifier(secret="s3cret", redis=redis)
    mock_response = MagicMock()
    mock_response.json = MagicMock(return_value={"success": True})
    mock_response.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    with patch("httpx.AsyncClient", return_value=mock_client):
        await verifier.verify(token="valid-token", remote_ip="1.2.3.4")
        # Second use of the same token — refused even though the
        # provider would say "success" again.
        with pytest.raises(CaptchaInvalidError) as exc:
            await verifier.verify(token="valid-token", remote_ip="1.2.3.4")
    assert exc.value.details["reason"] == "token_replayed"


@pytest.mark.asyncio
async def test_provider_outage_collapses_to_invalid() -> None:
    import httpx

    redis = _FakeRedis()
    verifier = TurnstileVerifier(secret="s3cret", redis=redis)
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(CaptchaInvalidError) as exc:
            await verifier.verify(token="tok", remote_ip="1.2.3.4")
    assert exc.value.details["reason"] == "provider_error"
