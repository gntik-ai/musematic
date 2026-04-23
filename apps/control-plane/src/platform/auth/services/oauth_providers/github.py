from __future__ import annotations

from urllib.parse import quote, urlencode

import httpx


class GitHubOAuthProvider:
    def __init__(
        self,
        *,
        auth_endpoint: str = "https://github.com/login/oauth/authorize",
        token_endpoint: str = "https://github.com/login/oauth/access_token",
        user_endpoint: str = "https://api.github.com/user",
        emails_endpoint: str = "https://api.github.com/user/emails",
        teams_endpoint: str = "https://api.github.com/user/teams",
        org_membership_endpoint_template: str = "https://api.github.com/user/memberships/orgs/{org}",
    ) -> None:
        self.auth_endpoint = auth_endpoint
        self.token_endpoint = token_endpoint
        self.user_endpoint = user_endpoint
        self.emails_endpoint = emails_endpoint
        self.teams_endpoint = teams_endpoint
        self.org_membership_endpoint_template = org_membership_endpoint_template

    def get_auth_url(
        self,
        *,
        client_id: str,
        redirect_uri: str,
        scopes: list[str],
        state: str,
        code_challenge: str,
    ) -> str:
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": " ".join(scopes or ["read:user", "user:email"]),
                "state": state,
                "allow_signup": "true",
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{self.auth_endpoint}?{query}"

    async def exchange_code(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code: str,
        code_verifier: str,
    ) -> dict[str, object]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                self.token_endpoint,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "code": code,
                    "code_verifier": code_verifier,
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return dict(response.json())

    async def fetch_user(self, *, access_token: str) -> dict[str, object]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                self.user_endpoint,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                },
            )
            response.raise_for_status()
            return dict(response.json())

    async def fetch_emails(self, *, access_token: str) -> str:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                self.emails_endpoint,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                },
            )
            response.raise_for_status()
            payload = response.json()
        for item in payload:
            if bool(item.get("primary")) and bool(item.get("verified")):
                return str(item.get("email"))
        raise ValueError("github_primary_email_not_found")

    async def check_org_membership(self, *, access_token: str, org: str) -> bool:
        endpoint = self.org_membership_endpoint_template.format(org=quote(org, safe=""))
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                endpoint,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                },
            )
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return str(response.json().get("state", "")) == "active"

    async def fetch_teams(self, *, access_token: str, orgs: list[str]) -> list[str]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                self.teams_endpoint,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                },
            )
            response.raise_for_status()
            payload = response.json()
        names: list[str] = []
        allowed_orgs = {item for item in orgs if item}
        for item in payload:
            org = str((item.get("organization") or {}).get("login") or "")
            if allowed_orgs and org not in allowed_orgs:
                continue
            slug = str(item.get("slug") or item.get("name") or "")
            if slug:
                names.append(slug)
        return names
