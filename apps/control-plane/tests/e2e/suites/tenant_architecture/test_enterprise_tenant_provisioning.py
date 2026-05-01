from __future__ import annotations

import asyncio
import os
import re
from collections.abc import AsyncIterator, Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.asyncio]

SETUP_LINK_PATTERN = re.compile(r"https?://[^\s\"'<>]+/setup\?token=[^\s\"'<>]+")


def _require_tenant_e2e() -> None:
    if os.environ.get("RUN_TENANT_ARCHITECTURE_E2E") != "true":
        pytest.skip("set RUN_TENANT_ARCHITECTURE_E2E=true to run tenant Journey J22")


@pytest.fixture
def platform_api_url() -> str:
    return os.environ.get("PLATFORM_API_URL", "http://localhost:8081")


@pytest.fixture
def smtp_api_url() -> str:
    value = os.environ.get("TENANT_E2E_SMTP_API_URL") or os.environ.get("DEV_SMTP_API_URL")
    if not value:
        pytest.skip("TENANT_E2E_SMTP_API_URL is required for Journey J22")
    return value.rstrip("/")


@pytest.fixture
async def admin_client(platform_api_url: str) -> AsyncIterator[httpx.AsyncClient]:
    _require_tenant_e2e()
    async with httpx.AsyncClient(base_url=platform_api_url, timeout=30.0) as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={
                "email": os.environ.get("TENANT_E2E_SUPERADMIN_EMAIL", "admin@e2e.test"),
                "password": os.environ.get(
                    "TENANT_E2E_SUPERADMIN_PASSWORD",
                    "e2e-test-password",
                ),
            },
        )
        assert login.status_code == 200, login.text
        token = login.json().get("access_token")
        assert isinstance(token, str)
        assert token
        client.headers.update({"Authorization": f"Bearer {token}"})
        yield client


@pytest.fixture
async def smtp_client(smtp_api_url: str) -> AsyncIterator[httpx.AsyncClient]:
    _require_tenant_e2e()
    async with httpx.AsyncClient(base_url=smtp_api_url, timeout=30.0) as client:
        yield client


async def _upload_dpa(client: httpx.AsyncClient) -> str:
    response = await client.post(
        "/api/v1/admin/tenants/dpa-upload",
        files={
            "file": (
                "acme-dpa.pdf",
                b"%PDF-1.4\n% tenant architecture e2e\n%%EOF\n",
                "application/pdf",
            )
        },
    )
    assert response.status_code == 200, response.text
    artifact_id = response.json().get("dpa_artifact_id")
    assert isinstance(artifact_id, str)
    assert artifact_id
    return artifact_id


async def _poll_setup_link(
    smtp_client: httpx.AsyncClient,
    *,
    recipient: str,
    tenant_slug: str,
) -> str:
    messages_path = os.environ.get("TENANT_E2E_SMTP_MESSAGES_PATH", "/api/v2/messages")
    expected_host = f"{tenant_slug}.localtest.me"
    for _ in range(60):
        response = await smtp_client.get(messages_path)
        assert response.status_code == 200, response.text
        for value in _iter_strings(response.json()):
            if recipient in value or expected_host in value:
                match = SETUP_LINK_PATTERN.search(value)
                if match and expected_host in match.group(0):
                    return match.group(0)
        await asyncio.sleep(2)
    raise AssertionError(f"setup invitation for {recipient} was not delivered")


def _iter_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for nested in value.values():
            yield from _iter_strings(nested)
        return
    if isinstance(value, list):
        for nested in value:
            yield from _iter_strings(nested)


def _token_from_setup_link(setup_link: str) -> str:
    parsed = httpx.URL(setup_link)
    token = parsed.params.get("token")
    assert token
    return token


async def test_j22_enterprise_tenant_provisioning(
    admin_client: httpx.AsyncClient,
    smtp_client: httpx.AsyncClient,
) -> None:
    slug = f"acme-{uuid4().hex[:8]}"
    first_admin_email = f"cto-{slug}@e2e.test"
    dpa_artifact_id = await _upload_dpa(admin_client)

    provision = await admin_client.post(
        "/api/v1/admin/tenants",
        json={
            "slug": slug,
            "display_name": "Acme Corp",
            "region": "eu-central",
            "first_admin_email": first_admin_email,
            "dpa_artifact_id": dpa_artifact_id,
            "dpa_version": "v3-2026-01",
            "contract_metadata": {
                "contract_number": f"ACME-{slug}",
                "signed_at": "2026-04-30",
                "signed_by": "Alice CTO",
            },
            "branding_config": {"accent_color_hex": "#0078d4"},
        },
    )
    assert provision.status_code == 201, provision.text
    tenant_id = provision.json()["id"]

    detail = await admin_client.get(f"/api/v1/admin/tenants/{tenant_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["slug"] == slug
    assert detail.json()["status"] == "active"

    setup_link = await _poll_setup_link(
        smtp_client,
        recipient=first_admin_email,
        tenant_slug=slug,
    )
    assert httpx.URL(setup_link).host == f"{slug}.localtest.me"

    setup = await admin_client.post(
        "/api/v1/auth/setup-tenant-admin",
        json={
            "token": _token_from_setup_link(setup_link),
            "display_name": "Acme Tenant Admin",
            "password": "TenantAdmin1!234",
        },
    )
    assert setup.status_code == 200, setup.text
    assert setup.json().get("access_token")
