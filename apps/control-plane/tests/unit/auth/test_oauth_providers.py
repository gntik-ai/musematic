from __future__ import annotations

from platform.auth.services.oauth_providers.github import GitHubOAuthProvider
from platform.auth.services.oauth_providers.google import GoogleOAuthProvider

import httpx
import pytest


class ResponseStub:
    def __init__(self, payload, *, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "request failed",
                request=httpx.Request("GET", "https://example.test"),
                response=httpx.Response(self.status_code),
            )


class AsyncClientStub:
    def __init__(self, *, get_responses=None, post_responses=None, calls=None, **kwargs) -> None:
        del kwargs
        self.get_responses = get_responses if get_responses is not None else []
        self.post_responses = post_responses if post_responses is not None else []
        self.calls = calls if calls is not None else []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        return self.get_responses.pop(0)

    async def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return self.post_responses.pop(0)


def test_google_auth_url_contains_pkce_fields() -> None:
    provider = GoogleOAuthProvider()

    url = provider.get_auth_url(
        client_id="google-client",
        redirect_uri="https://app.example.com/callback",
        scopes=["openid", "email"],
        state="signed-state",
        code_challenge="challenge",
    )

    assert "code_challenge=challenge" in url
    assert "state=signed-state" in url


@pytest.mark.asyncio
async def test_google_fetch_user_validates_audience_and_email_verification(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "platform.auth.services.oauth_providers.google.httpx.AsyncClient",
        lambda **kwargs: AsyncClientStub(
            get_responses=[
                ResponseStub(
                    {
                        "sub": "google-sub",
                        "email": "alex@example.com",
                        "aud": "google-client",
                        "email_verified": "true",
                    }
                )
            ],
            calls=calls,
            **kwargs,
        ),
    )
    provider = GoogleOAuthProvider()

    payload = await provider.fetch_user(id_token="id-token", client_id="google-client")

    assert payload["sub"] == "google-sub"
    assert calls[0][0] == "get"


@pytest.mark.asyncio
async def test_google_fetch_user_rejects_invalid_claims(monkeypatch) -> None:
    monkeypatch.setattr(
        "platform.auth.services.oauth_providers.google.httpx.AsyncClient",
        lambda **kwargs: AsyncClientStub(
            get_responses=[ResponseStub({"aud": "other-client", "email_verified": "false"})],
            **kwargs,
        ),
    )
    provider = GoogleOAuthProvider()

    with pytest.raises(ValueError, match="google_token_audience_mismatch"):
        await provider.fetch_user(id_token="id-token", client_id="google-client")


@pytest.mark.asyncio
async def test_github_exchange_user_email_org_and_teams(monkeypatch) -> None:
    calls = []
    post_responses = [ResponseStub({"access_token": "token"})]
    get_responses = [
        ResponseStub({"id": 1, "login": "octocat", "name": "Octo"}),
        ResponseStub(
            [
                {"email": "other@example.com", "primary": False, "verified": True},
                {"email": "octocat@example.com", "primary": True, "verified": True},
            ]
        ),
        ResponseStub({"state": "active"}),
        ResponseStub(
            [
                {"organization": {"login": "musematic"}, "slug": "platform-admins"},
                {"organization": {"login": "other"}, "slug": "ignore-me"},
            ]
        ),
    ]
    monkeypatch.setattr(
        "platform.auth.services.oauth_providers.github.httpx.AsyncClient",
        lambda **kwargs: AsyncClientStub(
            post_responses=post_responses,
            get_responses=get_responses,
            calls=calls,
            **kwargs,
        ),
    )
    provider = GitHubOAuthProvider()

    token = await provider.exchange_code(
        client_id="github-client",
        client_secret="secret",
        redirect_uri="https://app.example.com/callback",
        code="code",
        code_verifier="verifier",
    )
    user = await provider.fetch_user(access_token="token")
    email = await provider.fetch_emails(access_token="token")
    is_member = await provider.check_org_membership(access_token="token", org="musematic")
    teams = await provider.fetch_teams(access_token="token", orgs=["musematic"])

    assert token["access_token"] == "token"
    assert user["login"] == "octocat"
    assert email == "octocat@example.com"
    assert is_member is True
    assert teams == ["platform-admins"]
    assert calls[0][0] == "post"


@pytest.mark.asyncio
async def test_github_org_membership_handles_404_and_missing_primary_email(monkeypatch) -> None:
    get_responses = [ResponseStub([], status_code=200), ResponseStub({}, status_code=404)]
    monkeypatch.setattr(
        "platform.auth.services.oauth_providers.github.httpx.AsyncClient",
        lambda **kwargs: AsyncClientStub(get_responses=get_responses, **kwargs),
    )
    provider = GitHubOAuthProvider()

    with pytest.raises(ValueError, match="github_primary_email_not_found"):
        await provider.fetch_emails(access_token="token")

    assert await provider.check_org_membership(access_token="token", org="missing") is False
