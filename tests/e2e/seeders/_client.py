from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import httpx

from seeders.base import SeedRunSummary


DEFAULT_ADMIN_EMAIL = "admin@e2e.test"
DEFAULT_ADMIN_PASSWORD = "e2e-test-password"
DEFAULT_WORKSPACE_NAME = "test-workspace-alpha"


@dataclass(frozen=True, slots=True)
class SeedItem:
    key: str
    path: str
    payload: dict[str, Any]


class E2ESeederClient:
    def __init__(self) -> None:
        self.base_url = os.environ.get("PLATFORM_API_URL", "http://localhost:8081")
        self.admin_email = os.environ.get("E2E_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL)
        self.admin_password = os.environ.get(
            "E2E_ADMIN_PASSWORD",
            DEFAULT_ADMIN_PASSWORD,
        )
        self.workspace_name = os.environ.get("E2E_WORKSPACE_NAME", DEFAULT_WORKSPACE_NAME)
        self._workspace_id: str | None = os.environ.get("E2E_WORKSPACE_ID")
        self.access_token = os.environ.get("E2E_ADMIN_TOKEN")
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    async def __aenter__(self) -> E2ESeederClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.client.aclose()

    async def login(self) -> None:
        if self.access_token:
            return
        response = await self.client.post(
            "/api/v1/auth/login",
            json={"email": self.admin_email, "password": self.admin_password},
        )
        response.raise_for_status()
        data = response.json()
        self.access_token = (
            data.get("access_token")
            or data.get("accessToken")
            or data.get("token")
            or data.get("access", {}).get("token")
        )

    async def workspace_id(self) -> str:
        if self._workspace_id:
            return self._workspace_id
        await self.login()
        headers = self._auth_headers()
        response = await self.client.get("/api/v1/workspaces", headers=headers)
        response.raise_for_status()
        for item in response.json().get("items", []):
            if item.get("name") == self.workspace_name:
                self._workspace_id = str(item["id"])
                return self._workspace_id

        response = await self.client.post(
            "/api/v1/workspaces",
            json={
                "name": self.workspace_name,
                "description": "E2E baseline workspace",
            },
            headers=headers,
        )
        if response.status_code == 409:
            self._workspace_id = None
            return await self.workspace_id()
        response.raise_for_status()
        self._workspace_id = str(response.json()["id"])
        return self._workspace_id

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    async def post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        authenticated: bool = True,
        workspace_scoped: bool = True,
    ) -> httpx.Response:
        headers: dict[str, str] = {}
        if authenticated:
            await self.login()
            headers.update(self._auth_headers())
            if workspace_scoped:
                headers["X-Workspace-ID"] = await self.workspace_id()
        response = await self.client.post(path, json=payload, headers=headers)
        if response.status_code not in {200, 201, 202, 204, 409}:
            response.raise_for_status()
        return response

    async def delete(
        self,
        path: str,
        *,
        authenticated: bool = True,
        workspace_scoped: bool = True,
    ) -> httpx.Response:
        headers: dict[str, str] = {}
        if authenticated:
            await self.login()
            headers.update(self._auth_headers())
            if workspace_scoped:
                headers["X-Workspace-ID"] = await self.workspace_id()
        response = await self.client.delete(path, headers=headers)
        if response.status_code not in {200, 202, 204, 404}:
            response.raise_for_status()
        return response


async def seed_items(
    name: str,
    items: Iterable[SeedItem],
    *,
    authenticated: bool = True,
) -> SeedRunSummary:
    seeded = 0
    skipped = 0
    async with E2ESeederClient() as client:
        for item in items:
            response = await client.post(
                item.path,
                item.payload,
                authenticated=authenticated,
            )
            if response.status_code == 409:
                skipped += 1
            else:
                seeded += 1
    return SeedRunSummary(seeded={name: seeded}, skipped={name: skipped})


async def delete_paths(name: str, paths: Iterable[str]) -> dict[str, int]:
    deleted = 0
    async with E2ESeederClient() as client:
        for path in paths:
            response = await client.delete(path)
            if response.status_code != 404:
                deleted += 1
    return {name: deleted}
