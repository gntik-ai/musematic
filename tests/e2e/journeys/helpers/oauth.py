from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Awaitable, Callable
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx


_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_RETRYABLE_STATUSES = {429, 503}
_RETRY_ATTEMPTS = 10
_RETRY_MAX_DELAY_SECONDS = 10.0


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return min(float(retry_after), _RETRY_MAX_DELAY_SECONDS)
        except ValueError:
            pass
    return min(2**attempt, _RETRY_MAX_DELAY_SECONDS)


async def _request_with_retry(
    request: Callable[[], Awaitable[httpx.Response]],
    *,
    attempts: int = _RETRY_ATTEMPTS,
) -> httpx.Response:
    response: httpx.Response | None = None
    for attempt in range(attempts):
        response = await request()
        if response.status_code not in _RETRYABLE_STATUSES or attempt == attempts - 1:
            return response
        await asyncio.sleep(_retry_delay(response, attempt))
    assert response is not None
    return response


def _mock_authorize_url(provider: str, mock_server: str, redirect_url: str, login: str) -> str:
    parsed = urlparse(redirect_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if provider == "google":
        query["login_hint"] = [login]
        path = "/authorize"
    else:
        query["login"] = [login]
        path = "/login/oauth/authorize"
    target = urlparse(mock_server)
    return urlunparse(
        (
            target.scheme,
            target.netloc,
            path,
            "",
            urlencode(query, doseq=True),
            "",
        )
    )


def _decode_oauth_session_payload(redirect_location: str) -> dict[str, object]:
    fragment = redirect_location.split("#oauth_session=", 1)
    if len(fragment) != 2:
        raise AssertionError("callback did not return an oauth_session fragment")
    token = fragment[1]
    padding = "=" * (-len(token) % 4)
    try:
        decoded = base64.urlsafe_b64decode((token + padding).encode("utf-8")).decode("utf-8")
    except Exception as exc:  # pragma: no cover - defensive decoding guard
        raise AssertionError("callback returned an invalid oauth_session payload") from exc
    payload = json.loads(decoded)
    if not isinstance(payload, dict):
        raise AssertionError("oauth_session payload must be a JSON object")
    return payload


def _profile_display_name(login: str) -> str:
    normalized = login.replace("_", " ").replace("-", " ").replace(".", " ").strip()
    if not normalized:
        return "E2E User"
    return f"E2E {normalized.title()}"


async def _complete_profile_if_required(client, login: str) -> None:
    profile = await _request_with_retry(lambda: client.get("/api/v1/accounts/me"))
    profile.raise_for_status()
    payload = profile.json()
    if payload.get("status") != "pending_profile_completion":
        return

    completion = await _request_with_retry(
        lambda: client.patch(
            "/api/v1/accounts/me",
            json={
                "display_name": _profile_display_name(login),
                "locale": "en",
                "timezone": "UTC",
            },
        )
    )
    completion.raise_for_status()


async def oauth_login(client, provider: str, mock_server: str, login: str):
    authorize = await _request_with_retry(
        lambda: client.get(f"/api/v1/auth/oauth/{provider}/authorize")
    )
    authorize.raise_for_status()
    redirect_url = authorize.json()["redirect_url"]

    mock_authorize = _mock_authorize_url(provider, mock_server, redirect_url, login)
    mock_response = await _request_with_retry(
        lambda: client.raw_client.get(mock_authorize, follow_redirects=False),
        attempts=5,
    )
    if mock_response.status_code not in _REDIRECT_STATUSES:
        mock_response.raise_for_status()
    callback_url = mock_response.headers.get("location")
    if not callback_url:
        raise AssertionError(f"{provider} mock authorize response missing redirect location")

    callback = await _request_with_retry(
        lambda: client.raw_client.get(callback_url, follow_redirects=False)
    )
    if callback.status_code not in _REDIRECT_STATUSES:
        callback.raise_for_status()
        raise AssertionError(
            f"{provider} callback expected a redirect response, got {callback.status_code}"
        )
    redirect_location = callback.headers.get("location", "")
    if not redirect_location:
        raise AssertionError(f"{provider} callback redirect response missing location header")
    payload = _decode_oauth_session_payload(redirect_location)

    token_pair = payload.get("token_pair")
    if isinstance(token_pair, dict):
        access_token = token_pair.get("access_token")
        refresh_token = token_pair.get("refresh_token")
    else:
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
    if not isinstance(access_token, str) or not access_token:
        raise AssertionError(f"{provider} callback did not include an access token")
    client.set_bearer_token(access_token)
    client.refresh_token = refresh_token if isinstance(refresh_token, str) else None
    await _complete_profile_if_required(client, login)
    return client
