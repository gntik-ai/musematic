from __future__ import annotations

from urllib.parse import urlencode

import httpx


class GoogleOAuthProvider:
    def __init__(
        self,
        *,
        auth_endpoint: str = "https://accounts.google.com/o/oauth2/v2/auth",
        token_endpoint: str = "https://oauth2.googleapis.com/token",
        token_info_endpoint: str = "https://oauth2.googleapis.com/tokeninfo",
    ) -> None:
        self.auth_endpoint = auth_endpoint
        self.token_endpoint = token_endpoint
        self.token_info_endpoint = token_info_endpoint

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
                "response_type": "code",
                "scope": " ".join(scopes or ["openid", "email", "profile"]),
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "access_type": "offline",
                "include_granted_scopes": "true",
                "prompt": "consent",
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
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": code_verifier,
                },
            )
            response.raise_for_status()
            return dict(response.json())

    async def fetch_user(self, *, id_token: str, client_id: str) -> dict[str, object]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                self.token_info_endpoint,
                params={"id_token": id_token},
            )
            response.raise_for_status()
            payload = dict(response.json())
        if str(payload.get("aud")) != client_id:
            raise ValueError("google_token_audience_mismatch")
        if str(payload.get("email_verified", "false")).lower() != "true":
            raise ValueError("google_email_not_verified")
        return payload

    async def fetch_groups(self, *, access_token: str) -> list[str]:
        del access_token
        return []
