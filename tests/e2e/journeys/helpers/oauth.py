from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


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


async def oauth_login(client, provider: str, mock_server: str, login: str):
    authorize = await client.get(f"/api/v1/auth/oauth/{provider}/authorize")
    authorize.raise_for_status()
    redirect_url = authorize.json()["redirect_url"]

    mock_authorize = _mock_authorize_url(provider, mock_server, redirect_url, login)
    mock_response = await client.raw_client.get(mock_authorize, follow_redirects=False)
    if mock_response.status_code not in _REDIRECT_STATUSES:
        mock_response.raise_for_status()
    callback_url = mock_response.headers.get("location")
    if not callback_url:
        raise AssertionError(f"{provider} mock authorize response missing redirect location")

    callback = await client.raw_client.get(callback_url, follow_redirects=False)
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
    return client
